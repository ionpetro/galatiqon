"""Live Pi health dashboard (power, temperature, clocks, load, network, Grok Bot link).

Stdlib only, so it runs with the system python3 before the venv exists:

    python3 galatiqon/dashboard.py [--host 0.0.0.0] [--port 8080]

Every endpoint sends `Access-Control-Allow-Origin: *`, so the Galatiqon web app (web/) can read
/api/stats and /events from another origin.

One background thread samples everything; HTTP clients only read the cached
snapshot (already serialised to JSON), so extra viewers cost almost nothing.
Fast things (power flags, temperature, clocks, CPU, network) are read once a
second, processes and audio every 5 s, and slow things (Wi-Fi details,
Bluetooth, services, logs) every 30 s. Device facts are read once at start.

  /             overview: power, temperature/CPU/memory, Grok Bot, Wi-Fi, Bluetooth
  /details      everything technical (flags, charts, network, services, processes, device)
                (both pages are inline HTML/CSS/JS, no external assets)
  /api/stats    current snapshot as JSON
  /api/history  last ~5 minutes of samples as JSON
  /events       Server-Sent Events, one snapshot per sample
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pwd
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SAMPLE_INTERVAL = 1.0
HISTORY_LEN = 300  # samples, about 5 minutes
PROC_INTERVAL = 5.0  # top processes, audio state
SLOW_INTERVAL = 30.0  # Wi-Fi details, Bluetooth, services, logs

# vcgencmd get_throttled bits
THROTTLE_BITS = {
    "under_voltage": 0,
    "freq_capped": 1,
    "throttled": 2,
    "soft_temp_limit": 3,
}
SINCE_BOOT_SHIFT = 16

VCGENCMD = shutil.which("vcgencmd") or "/usr/bin/vcgencmd"
CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
WIFI_IFACE = "wlan0"
MUSE_UNITS = ["galatiqon-gbd.service", "galatiqon-output.service", "galatiqon-ptt.service", "galatiqon-dashboard.service"]


def _run(cmd: list[str], timeout: float = 3.0) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _vc(*args: str) -> str | None:
    out = _run([VCGENCMD, *args])
    return out.strip() if out else None


# ---------------------------------------------------------------- fast (1 s)


def read_throttled() -> dict | None:
    out = _vc("get_throttled")
    m = re.search(r"0x([0-9a-fA-F]+)", out or "")
    if not m:
        return None
    raw = int(m.group(1), 16)
    return {
        "raw": f"0x{raw:x}",
        "now": {k: bool(raw >> b & 1) for k, b in THROTTLE_BITS.items()},
        "since_boot": {k: bool(raw >> (b + SINCE_BOOT_SHIFT) & 1) for k, b in THROTTLE_BITS.items()},
    }


def read_core_volts() -> float | None:
    m = re.search(r"volt=([\d.]+)", _vc("measure_volts", "core") or "")
    return float(m.group(1)) if m else None


def read_arm_mhz() -> float | None:
    # sysfs first: a file read instead of spawning vcgencmd every second
    khz = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    if khz and khz.strip().isdigit():
        return round(int(khz) / 1000)
    m = re.search(r"=(\d+)", _vc("measure_clock", "arm") or "")
    return round(int(m.group(1)) / 1e6) if m else None


def read_temp_c() -> float | None:
    raw = _read("/sys/class/thermal/thermal_zone0/temp")
    try:
        return round(int(raw) / 1000, 1) if raw else None
    except ValueError:
        return None


def read_undervolt_alarm() -> bool | None:
    """Live under-voltage alarm from the rpi_volt hwmon driver, if present."""
    base = "/sys/class/hwmon"
    try:
        for name in os.listdir(base):
            if (_read(f"{base}/{name}/name") or "").strip() == "rpi_volt":
                v = _read(f"{base}/{name}/in0_lcrit_alarm")
                return v.strip() == "1" if v else None
    except OSError:
        pass
    return None


def read_cpu_times() -> dict[str, tuple[int, int]]:
    """{"cpu": (total, idle), "cpu0": ..., ...} from /proc/stat."""
    out = {}
    for line in (_read("/proc/stat") or "").splitlines():
        if not line.startswith("cpu"):
            break
        parts = line.split()
        vals = [int(x) for x in parts[1:9]]  # user nice system idle iowait irq softirq steal
        out[parts[0]] = (sum(vals), vals[3] + vals[4])
    return out


def read_mem() -> dict | None:
    info = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        k, _, v = line.partition(":")
        info[k] = int(v.split()[0]) if v.split() else 0
    if "MemTotal" not in info:
        return None
    total = info["MemTotal"] * 1024
    avail = info.get("MemAvailable", info.get("MemFree", 0)) * 1024
    return {
        "total": total,
        "used": total - avail,
        "swap_total": info.get("SwapTotal", 0) * 1024,
        "swap_used": (info.get("SwapTotal", 0) - info.get("SwapFree", 0)) * 1024,
    }


def read_disk() -> dict | None:
    try:
        st = os.statvfs("/")
    except OSError:
        return None
    total = st.f_blocks * st.f_frsize
    return {"total": total, "used": total - st.f_bfree * st.f_frsize}


def read_wireless(iface: str = WIFI_IFACE) -> dict | None:
    for line in (_read("/proc/net/wireless") or "").splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() != iface:
            continue
        f = rest.split()
        try:
            quality = float(f[1].rstrip("."))
            level = float(f[2].rstrip("."))
        except (IndexError, ValueError):
            return None
        return {"quality_pct": round(quality / 70 * 100), "signal_dbm": level}
    return None


def read_net_dev() -> dict[str, tuple[int, int]]:
    out = {}
    for line in (_read("/proc/net/dev") or "").splitlines()[2:]:
        name, _, rest = line.partition(":")
        f = rest.split()
        if len(f) >= 9:
            out[name.strip()] = (int(f[0]), int(f[8]))
    return out


def read_uptime() -> float | None:
    raw = _read("/proc/uptime")
    try:
        return float(raw.split()[0]) if raw else None
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------- medium (5 s)

SCRIPT_HOSTS = {"python", "python3", "sh", "bash", "node", "perl"}


def read_proc_ticks() -> dict[int, tuple[str, int, int]]:
    """pid -> (comm, utime+stime ticks, rss bytes)."""
    out = {}
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return out
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat", "rb") as f:
                data = f.read()
        except OSError:
            continue
        r = data.rfind(b")")
        comm = data[data.find(b"(") + 1 : r].decode(errors="replace")
        f = data[r + 2 :].split()
        try:
            out[int(pid)] = (comm, int(f[11]) + int(f[12]), int(f[21]) * PAGE_SIZE)
        except (IndexError, ValueError):
            continue
    return out


def _proc_label(pid: int, comm: str) -> str:
    script = comm in SCRIPT_HOSTS or comm.startswith("python")
    if not script and len(comm) < 15:  # the kernel truncates comm to 15 chars
        return comm
    raw = _read(f"/proc/{pid}/cmdline") or ""
    args = [a for a in raw.split("\0") if a]
    if not script:
        for a in args[:3]:  # console scripts: argv0 is the interpreter, argv1 the script
            full = os.path.basename(a)
            if full.startswith(comm):
                return full
        return comm
    for i, a in enumerate(args[1:], 1):
        if a == "-c":
            return f"{comm} -c"
        if a == "-m" and i + 1 < len(args):
            return f"{comm} -m {args[i + 1]}"
        if not a.startswith("-"):
            return f"{comm} {os.path.basename(a)}"
    return comm


def _proc_user(pid: int) -> str | None:
    try:
        return pwd.getpwuid(os.stat(f"/proc/{pid}").st_uid).pw_name
    except (OSError, KeyError):
        return None


def read_audio() -> dict:
    """ALSA cards from /proc/asound, with playback state of each card."""
    cards = []
    for line in (_read("/proc/asound/cards") or "").splitlines():
        m = re.match(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s+(.*?)\s+-\s+(.*)$", line)
        if not m:
            continue
        idx, cid, driver, name = m.groups()
        base = f"/proc/asound/card{idx}"
        playback, state = False, "idle"
        try:
            for d in os.listdir(base):
                if re.match(r"pcm\d+p$", d):
                    playback = True
                    st = _read(f"{base}/{d}/sub0/status") or ""
                    if "RUNNING" in st:
                        state = "playing"
        except OSError:
            pass
        extra = None
        eld = _read(f"{base}/eld#0") or ""
        if eld:
            mp = re.search(r"monitor_present\s+(\d)", eld)
            mn = re.search(r"monitor_name\s+(.+)", eld)
            if mp:
                extra = ("display: " + (mn.group(1).strip() if mn else "connected")) if mp.group(1) == "1" else "no display"
        cards.append({"index": int(idx), "id": cid, "driver": driver, "name": name.strip(),
                      "playback": playback, "state": state, "extra": extra})
    return {"cards": cards, "headphones": any(c["id"].lower().startswith("headphone") for c in cards)}


# ------------------------------------------------------------- slow (30 s)


def read_wifi_details(iface: str = WIFI_IFACE) -> dict:
    out: dict = {"mac": (_read(f"/sys/class/net/{iface}/address") or "").strip() or None}
    if shutil.which("nmcli"):
        txt = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,CHAN,FREQ,RATE,SECURITY", "dev", "wifi", "list",
                    "ifname", iface, "--rescan", "no"]) or ""
        for line in txt.splitlines():
            f = [x.replace("\\:", ":") for x in re.split(r"(?<!\\):", line)]
            if len(f) >= 6 and f[0] == "yes":
                freq = re.search(r"\d+", f[3])
                mhz = int(freq.group()) if freq else None
                out.update({
                    "ssid": f[1] or None,
                    "channel": f[2] or None,
                    "freq_mhz": mhz,
                    "band": ("2.4 GHz" if mhz < 3000 else "5 GHz" if mhz < 5925 else "6 GHz") if mhz else None,
                    "rate": f[4] or None,
                    "security": f[5] or None,
                })
                break
    if not out.get("ssid") and shutil.which("iwgetid"):
        s = (_run(["iwgetid", "-r", iface]) or "").strip()
        out["ssid"] = s or None
    return out


def read_ip() -> str | None:
    # connect() on UDP sends nothing; it just picks the outgoing interface address
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            return s.getsockname()[0]
    except OSError:
        return None


def read_bluetooth() -> dict:
    """Adapter state. Read-only D-Bus query via busctl (no agent, unlike bluetoothctl)."""
    rf = None
    try:
        for r in os.listdir("/sys/class/rfkill"):
            if (_read(f"/sys/class/rfkill/{r}/type") or "").strip() == "bluetooth":
                rf = {"soft_blocked": (_read(f"/sys/class/rfkill/{r}/soft") or "").strip() == "1",
                      "hard_blocked": (_read(f"/sys/class/rfkill/{r}/hard") or "").strip() == "1"}
                break
    except OSError:
        pass
    out: dict = {"present": os.path.isdir("/sys/class/bluetooth/hci0"), "rfkill": rf}
    if not shutil.which("busctl"):
        return out
    txt = _run(["busctl", "--system", "--json=short", "call", "org.bluez", "/",
                "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"], timeout=3)
    if not txt:
        out["error"] = "bluetoothd not reachable"
        return out
    try:
        objs = json.loads(txt)["data"][0]
    except (ValueError, KeyError, IndexError):
        return out
    devices = []
    for path, ifs in objs.items():
        a = ifs.get("org.bluez.Adapter1")
        if a and "adapter" not in out:
            g = lambda k: (a.get(k) or {}).get("data")  # noqa: E731
            out["adapter"] = {"address": g("Address"), "alias": g("Alias"), "name": g("Name"),
                              "powered": g("Powered"), "discoverable": g("Discoverable"),
                              "pairable": g("Pairable")}
        d = ifs.get("org.bluez.Device1")
        if d:
            g = lambda k: (d.get(k) or {}).get("data")  # noqa: E731
            devices.append({"name": g("Alias") or g("Name") or g("Address"), "paired": bool(g("Paired")),
                            "connected": bool(g("Connected"))})
    out["devices"] = devices
    return out


def read_services(units: list[str] = MUSE_UNITS) -> list[dict]:
    txt = _run(["systemctl", "show", "--timestamp=unix", "-p", "Id,LoadState,ActiveState,SubState,ActiveEnterTimestamp",
                *units]) or ""
    out = []
    for block in txt.strip().split("\n\n"):
        p = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if not p.get("Id"):
            continue
        m = re.search(r"@(\d+)", p.get("ActiveEnterTimestamp", ""))
        out.append({
            "unit": p["Id"].removesuffix(".service"),
            "installed": p.get("LoadState") != "not-found",
            "active": p.get("ActiveState"),
            "sub": p.get("SubState"),
            "since": int(m.group(1)) if m and p.get("ActiveState") == "active" else None,
        })
    return out


MUSE_STATES = [  # (regex on message, state, label); last match wins. Lines come from gbd and galatiqon-ptt.
    (re.compile(r"not logged in|run `gb login`", re.I), "unpaired", "Not signed in"),
    (re.compile(r"box not ready|HIBERNATED|box asleep", re.I), "connecting", "Waking box"),
    (re.compile(r"listening on unix|events connected|initial roster: \d", re.I), "connected", "Connected"),
    (re.compile(r"disconnect|connection (lost|closed)|reconnect|stream ended", re.I), "connecting", "Reconnecting"),
    (re.compile(r"talking to bot|ready, push-to-talk|ready, keyboard", re.I), "paired", "Ready"),
    (re.compile(r"reply after", re.I), "connected", "Answering"),
]
PYLOG_RE = re.compile(r"^\d{4}-\d\d-\d\d [\d:,.]+ (\w+) ([\w.]+): (.*)$")


def read_muse_log(n: int = 150) -> dict:
    """Recent Grok Bot daemon and push-to-talk journal lines (read via the adm group) and a link state guess."""
    txt = _run(["journalctl", "-u", "galatiqon-gbd", "-u", "galatiqon-ptt", "-n", str(n), "--no-pager", "-q", "-o", "short-unix"], timeout=5)
    if txt is None:
        return {"error": "journal not readable (needs adm group)"}
    events = []
    for line in txt.splitlines():
        m = re.match(r"^([\d.]+)\s+\S+\s+([^\[:]+)(?:\[\d+\])?:\s(.*)$", line)
        if not m:
            continue
        ts, src, msg = float(m.group(1)), m.group(2), m.group(3)
        level = "INFO"
        pm = PYLOG_RE.match(msg)
        if pm:
            level, msg = pm.group(1), pm.group(3)
        if src == "systemd" and not re.match(r"(Started|Stopped|Stopping)\b", msg):
            continue
        if src == "systemd":
            msg = re.sub(r" - .*", "", msg).replace("galatiqon-gbd.service", "service").replace("galatiqon-ptt.service", "service").rstrip(".")
        events.append({"t": ts, "level": level, "msg": msg[:200], "sys": src == "systemd"})
    state, label, state_t = None, None, None
    for e in events:
        if e["sys"] and e["msg"].startswith("Started"):
            state, label, state_t = "starting", "Starting", e["t"]
        for rx, st, lb in MUSE_STATES:
            if rx.search(e["msg"]):
                state, label, state_t = st, lb, e["t"]
                break
    # collapse repeats ("not paired" every 30 s) into one line with a count
    collapsed: list[dict] = []
    for e in events:
        if collapsed and collapsed[-1]["msg"] == e["msg"]:
            collapsed[-1]["n"] = collapsed[-1].get("n", 1) + 1
            collapsed[-1]["t"] = e["t"]
        else:
            collapsed.append(dict(e))
    return {"state": state, "label": label, "state_t": state_t, "events": collapsed[-8:]}


VOLT_RE = re.compile(r"(under-?voltage|undervoltage|voltage normali[sz]ed)", re.I)
UV_ON_RE = re.compile(r"under-?voltage detected|undervoltage detected", re.I)


def read_kernel_voltage_events(boot_t: float | None, limit: int = 15) -> dict:
    """Under-voltage lines from this boot's kernel log.

    Uses monotonic stamps (seconds since boot) and converts with the boot time,
    because early-boot wall-clock times are wrong until NTP syncs (no RTC).
    """
    out = _run(["journalctl", "-k", "-b", "--no-pager", "-o", "short-monotonic", "-q", "-g", "oltage"], timeout=5)
    if out is None:
        out = _run(["dmesg"])
    if out is None:
        return {"events": [], "count": 0, "last_t": None, "error": "kernel log not readable (needs adm group or root)"}
    events = []
    for line in out.splitlines():
        if not VOLT_RE.search(line):
            continue
        m = re.match(r"^\[\s*([\d.]+)\]\s+(?:\S+\s+kernel:\s+)?(.*)$", line)
        mono = float(m.group(1)) if m else None
        text = m.group(2) if m else line
        events.append({"mono": mono, "t": boot_t + mono if (boot_t and mono is not None) else None,
                       "text": text, "uv": bool(UV_ON_RE.search(text))})
    uv = [e for e in events if e["uv"]]
    return {"events": events[-limit:], "count": len(uv), "last_t": uv[-1]["t"] if uv else None, "error": None}


# ------------------------------------------------------------- static (once)

REV_MEM = {0: "256 MB", 1: "512 MB", 2: "1 GB", 3: "2 GB", 4: "4 GB", 5: "8 GB", 6: "16 GB"}
REV_MAKER = {0: "Sony UK", 1: "Egoman", 2: "Embest", 3: "Sony Japan", 4: "Embest", 5: "Stadium"}
REV_SOC = {0: "BCM2835", 1: "BCM2836", 2: "BCM2837", 3: "BCM2711", 4: "BCM2712"}


def read_static() -> dict:
    cpuinfo = _read("/proc/cpuinfo") or ""
    get = lambda k: (re.search(rf"^{k}\s*:\s*(.+)$", cpuinfo, re.M) or [None, None])[1]  # noqa: E731
    rev = get("Revision")
    board = None
    if rev:
        try:
            r = int(rev, 16)
            if r & (1 << 23):
                board = {"memory": REV_MEM.get(r >> 20 & 7), "maker": REV_MAKER.get(r >> 16 & 15),
                         "soc": REV_SOC.get(r >> 12 & 15), "pcb": f"1.{r & 15}"}
        except ValueError:
            pass
    pretty = re.search(r'^PRETTY_NAME="?([^"\n]+)', _read("/etc/os-release") or "", re.M)
    fw = _vc("version")
    serial = (get("Serial") or "").lstrip("0") or None
    mem = read_mem()
    gov_max = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
    gov_min = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq")
    u = os.uname()
    return {
        "model": (_read("/proc/device-tree/model") or get("Model") or "").replace("\0", "").strip() or None,
        "os": pretty.group(1) if pretty else None,
        "kernel": u.release,
        "arch": u.machine,
        "hostname": socket.gethostname(),
        "revision": rev,
        "board": board,
        "serial": serial,
        "firmware": fw.splitlines()[0].strip() if fw else None,
        "python": sys.version.split()[0],
        "ram_total": mem["total"] if mem else None,
        "ncpu": os.cpu_count(),
        "max_mhz": int(gov_max) // 1000 if gov_max and gov_max.strip().isdigit() else None,
        "min_mhz": int(gov_min) // 1000 if gov_min and gov_min.strip().isdigit() else None,
    }


# ------------------------------------------------------------------ sampler


class Sampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="sampler")
        self.cond = threading.Condition()
        self.snapshot_json = b"{}"
        self.seq = 0
        self.history: collections.deque = collections.deque(maxlen=HISTORY_LEN)
        self.transitions: collections.deque = collections.deque(maxlen=30)
        self._prev_cpu = read_cpu_times()
        self._prev_net = (time.monotonic(), read_net_dev())
        self._prev_now: dict | None = None
        self._prev_raw: str | None = None
        self._prev_procs: tuple[float, dict] | None = None
        self._static: dict = {}
        self._medium: dict = {}
        self._medium_at = 0.0
        self._slow: dict = {}
        self._slow_at = 0.0
        self._kernel: dict = {}

    def _boot_t(self) -> float | None:
        up = read_uptime()
        return time.time() - up if up is not None else None

    def _slow_refresh(self) -> None:
        self._slow = {
            "ip": read_ip(),
            "wifi_info": read_wifi_details(),
            "bluetooth": read_bluetooth(),
            "services": read_services(),
            "muse": read_muse_log(),
            "governor": (_read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") or "").strip() or None,
        }
        self._kernel = read_kernel_voltage_events(self._boot_t())
        self._slow_at = time.monotonic()

    def _medium_refresh(self) -> None:
        now = time.monotonic()
        cur = read_proc_ticks()
        top = []
        if self._prev_procs:
            t0, prev = self._prev_procs
            dt = max(now - t0, 1e-3) * CLK_TCK
            rows = []
            for pid, (comm, ticks, rss) in cur.items():
                p = prev.get(pid)
                d = ticks - p[1] if p else 0
                rows.append((d / dt * 100, rss, pid, comm))
            rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
            top = [{"pid": pid, "name": _proc_label(pid, comm), "user": _proc_user(pid),
                    "cpu": round(pct, 1), "rss": rss} for pct, rss, pid, comm in rows[:5]]
        self._prev_procs = (now, cur)
        self._medium = {"procs": top, "nprocs": len(cur), "audio": read_audio()}
        self._medium_at = now

    def _cpu(self) -> tuple[float | None, list[float]]:
        cur = read_cpu_times()
        prev, self._prev_cpu = self._prev_cpu, cur

        def pct(k: str) -> float | None:
            a, b = cur.get(k), prev.get(k)
            if not a or not b or a[0] == b[0]:
                return None
            return round(100 * (1 - (a[1] - b[1]) / (a[0] - b[0])), 1)

        cores = [pct(k) for k in sorted(cur) if k != "cpu"]
        return pct("cpu"), [c if c is not None else 0.0 for c in cores]

    def _net(self) -> dict | None:
        now, cur = time.monotonic(), read_net_dev()
        t0, prev = self._prev_net
        self._prev_net = (now, cur)
        iface = WIFI_IFACE if WIFI_IFACE in cur else next((k for k in cur if k != "lo"), None)
        if not iface or iface not in prev:
            return None
        dt = max(now - t0, 1e-3)
        rx, tx = cur[iface]
        return {"iface": iface, "rx_bps": max(0, round((rx - prev[iface][0]) / dt)),
                "tx_bps": max(0, round((tx - prev[iface][1]) / dt)), "rx_total": rx, "tx_total": tx}

    def _note_transitions(self, thr: dict | None, ts: float) -> None:
        if not thr:
            return
        now = thr["now"]
        if self._prev_now is not None:
            for k, v in now.items():
                if v != self._prev_now.get(k):
                    self.transitions.append({"t": ts, "flag": k, "on": v})
        self._prev_now = now

    def sample(self) -> dict:
        ts = time.time()
        mono = time.monotonic()
        thr = read_throttled()
        self._note_transitions(thr, ts)
        if mono - self._slow_at > SLOW_INTERVAL:
            self._slow_refresh()
        elif thr and self._prev_raw and thr["raw"] != self._prev_raw:
            self._kernel = read_kernel_voltage_events(self._boot_t())  # flags changed: pick up the kernel line now
        self._prev_raw = thr["raw"] if thr else None
        if mono - self._medium_at > PROC_INTERVAL:
            self._medium_refresh()
        la = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
        cpu, cores = self._cpu()
        uptime = read_uptime()
        wifi = read_wireless()
        info = self._slow.get("wifi_info") or {}
        return {
            "t": ts,
            "throttled": thr,
            "undervolt_alarm": read_undervolt_alarm(),
            "core_volts": read_core_volts(),
            "temp_c": read_temp_c(),
            "arm_mhz": read_arm_mhz(),
            "cpu_pct": cpu,
            "cores": cores,
            "load": [round(x, 2) for x in la] if la[0] is not None else None,
            "ncpu": os.cpu_count(),
            "mem": read_mem(),
            "disk": read_disk(),
            "wifi": wifi,
            "net": self._net(),
            "uptime_s": uptime,
            "boot_t": ts - uptime if uptime is not None else None,
            "hostname": self._static.get("hostname") or socket.gethostname(),
            "ssid": info.get("ssid"),
            "transitions": list(self.transitions),
            "kernel_events": [e["text"] for e in self._kernel.get("events", [])],  # kept for older clients
            "kernel_events_error": self._kernel.get("error"),
            "uv_log": self._kernel,
            "device": self._static,
            **self._medium,
            **self._slow,
        }

    def run(self) -> None:
        self._static = read_static()
        self._slow_refresh()
        self._medium_refresh()
        next_at = time.monotonic()
        while True:
            try:
                snap = self.sample()
            except Exception as e:  # never let the sampler die
                snap = {"t": time.time(), "error": repr(e)}
            thr = snap.get("throttled") or {}
            net = snap.get("net") or {}
            mem = snap.get("mem") or {}
            point = {k: snap.get(k) for k in ("t", "temp_c", "cpu_pct", "arm_mhz", "core_volts")}
            point["uv"] = bool((thr.get("now") or {}).get("under_voltage"))
            point["mem_pct"] = round(100 * mem["used"] / mem["total"], 1) if mem.get("total") else None
            point["rx"] = net.get("rx_bps")
            point["tx"] = net.get("tx_bps")
            body = json.dumps(snap, separators=(",", ":")).encode()
            with self.cond:
                self.snapshot_json = body
                self.history.append(point)
                self.seq += 1
                self.cond.notify_all()
            next_at += SAMPLE_INTERVAL
            delay = next_at - time.monotonic()
            if delay < 0:
                next_at = time.monotonic()
                delay = 0
            time.sleep(delay)


SAMPLER = Sampler()


class Handler(BaseHTTPRequestHandler):
    server_version = "galatiqon-dashboard"

    def log_message(self, fmt, *args):  # keep the journal quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, MAIN_PAGE, "text/html; charset=utf-8")
        elif path in ("/details", "/specs"):
            self._send(200, DETAILS_PAGE, "text/html; charset=utf-8")
        elif path == "/api/stats":
            with SAMPLER.cond:
                body = SAMPLER.snapshot_json
            self._send(200, body, "application/json")
        elif path == "/api/history":
            with SAMPLER.cond:
                hist = list(SAMPLER.history)
            self._send(200, json.dumps(hist, separators=(",", ":")).encode(), "application/json")
        elif path == "/events":
            self._events()
        else:
            self._send(404, b"not found\n", "text/plain")

    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        seen = -1
        try:
            self.wfile.write(b"retry: 3000\n\n")
            while True:
                with SAMPLER.cond:
                    SAMPLER.cond.wait_for(lambda: SAMPLER.seq != seen, timeout=15)
                    if SAMPLER.seq == seen:
                        body = None
                    else:
                        seen, body = SAMPLER.seq, SAMPLER.snapshot_json
                self.wfile.write(b": ping\n\n" if body is None else b"data: " + body + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


# ---------------------------------------------------------------- the pages
# Two pages share one stylesheet, one JS core (formatting, history, SSE/polling)
# and the same endpoints; each adds its own body and render().

HEAD = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#F0F2F5" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0F0F10" media="(prefers-color-scheme: dark)">
<title>@TITLE@</title>
<style>
:root{
 --bg:#F0F2F5;--card:#FFFFFF;--card2:#F5F6F8;--fg:#1C2B33;--mute:#5D6C7B;--faint:#8A97A3;--track:#E8EBEF;
 --accent:#0064E0;--accent2:#7A5AF8;--accentbg:#E7F0FD;
 --ok:#1E8E3E;--okbg:#E4F4E8;--bad:#D21F3C;--badbg:#FCE8EB;--warn:#A15C00;--warnbg:#FFF2DB;--neutralbg:#EEF0F3;
 --shadow:0 1px 2px rgba(16,24,40,.04),0 2px 8px rgba(16,24,40,.05);--r:18px;--maxw:560px;
}
@media (prefers-color-scheme:dark){:root{
 --bg:#0F0F10;--card:#1B1B1E;--card2:#242428;--fg:#E8EAED;--mute:#A4A9B0;--faint:#7D828A;--track:#2C2C30;
 --accent:#4A97FF;--accent2:#A08BFF;--accentbg:#14243D;
 --ok:#4CC26B;--okbg:#142A1B;--bad:#FF6B7F;--badbg:#3A1820;--warn:#F5B640;--warnbg:#36290F;--neutralbg:#28282C;
 --shadow:none;
}}
body.wide{--maxw:1080px}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
 font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
p{margin:0}
.num{font-variant-numeric:tabular-nums}
.muted{color:var(--faint)}
.ic{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
header{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 85%,transparent);
 -webkit-backdrop-filter:saturate(180%) blur(16px);backdrop-filter:saturate(180%) blur(16px)}
.hwrap{max-width:var(--maxw);margin:0 auto;padding:12px 16px;padding-top:max(12px,env(safe-area-inset-top));display:flex;align-items:center;gap:12px}
.logo{width:44px;height:44px;border-radius:50%;flex:none;overflow:hidden;background:#000;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}
.mascot{display:block;width:44px;height:44px;transform-origin:50% 100%;will-change:transform;animation:breathe 4s ease-in-out infinite}
.mascot .eyes{fill:#1E1A17;transform-origin:50px 47px;animation:blink 5s infinite}
.mascot .shut{fill:none;stroke:#1E1A17;stroke-width:1.4;stroke-linecap:round;opacity:0}
.mascot .mouth{fill:none;stroke:#3B2A22;stroke-width:1.2;stroke-linecap:round}
@keyframes blink{0%,94%,100%{transform:scaleY(1)}97%{transform:scaleY(.1)}}
@keyframes breathe{50%{transform:scale(1.03,1.045)}}
@keyframes sway{25%{transform:rotate(-3deg) scale(1.02)}75%{transform:rotate(3deg) scale(1.02)}}
.logo.work .mascot{animation:sway 3s ease-in-out infinite}
.logo.sleep .eyes{opacity:0;animation:none}.logo.sleep .shut{opacity:1}.logo.sleep .mascot{animation-duration:7s}
.back{width:36px;height:36px;border-radius:50%;flex:none;display:grid;place-items:center;background:var(--card);box-shadow:var(--shadow);color:var(--fg)}
.htxt{min-width:0;flex:1}
.htxt h1{font-size:17px;font-weight:700;margin:0;letter-spacing:-.01em}
.htxt div{font-size:13px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
main{max-width:var(--maxw);margin:0 auto;padding:4px 16px 24px}
.stack{display:grid;gap:12px}
footer{max-width:var(--maxw);margin:0 auto;padding:0 16px 28px;font-size:12px;color:var(--faint);text-align:center}
footer a{color:var(--accent)}
.chip{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 11px;border-radius:999px;font-size:13px;font-weight:600;white-space:nowrap;
 background:var(--neutralbg);color:var(--mute)}
.chip.ok{background:var(--okbg);color:var(--ok)}.chip.bad{background:var(--badbg);color:var(--bad)}
.chip.warn{background:var(--warnbg);color:var(--warn)}.chip.info{background:var(--accentbg);color:var(--accent)}
.chip.sm{height:22px;padding:0 9px;font-size:12px}
.dot{width:7px;height:7px;border-radius:50%;background:currentColor;flex:none}
.chip.ok .dot.live{animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,currentColor 50%,transparent)}70%{box-shadow:0 0 0 6px transparent}100%{box-shadow:0 0 0 0 transparent}}
.spin{width:11px;height:11px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:rot .8s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}
.card{background:var(--card);border-radius:var(--r);box-shadow:var(--shadow);padding:16px;min-width:0;transition:opacity .3s}
body.offline .card{opacity:.55}
.ctitle{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;color:var(--mute);margin:0 0 10px}
.ctitle .ic{width:18px;height:18px}
.ctitle .r{margin-left:auto;font-weight:500}
.ok-t{color:var(--ok)}.warn-t{color:var(--warn)}.bad-t{color:var(--bad)}.info-t{color:var(--accent)}
/* sparklines */
.spark{position:relative;height:56px;margin-top:8px;touch-action:pan-y}
.spark svg{display:block;width:100%;height:100%;overflow:visible}
.spark .ln{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke;stroke-linejoin:round}
.spark .ln2{fill:none;stroke:var(--accent2);stroke-width:1.6;vector-effect:non-scaling-stroke;stroke-linejoin:round}
.spark .ar{fill:var(--accent);opacity:.09}
.spark .uv{fill:var(--bad);opacity:.22}
.spark .lim{stroke:var(--bad);stroke-width:1;stroke-dasharray:3 3;vector-effect:non-scaling-stroke;opacity:.5}
.spark .cur{position:absolute;top:0;bottom:0;width:1px;background:var(--faint);opacity:0;pointer-events:none}
.spark .pt{position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;background:var(--card);border:2.5px solid var(--accent);opacity:0;pointer-events:none}
.spark.on .cur,.spark.on .pt{opacity:1}
.spark .empty{position:absolute;inset:0;display:grid;place-items:center;font-size:12px;color:var(--faint)}
/* motion: transform/opacity only, one ease, short durations */
:root{--ease:cubic-bezier(.22,1,.36,1)}
@view-transition{navigation:auto}
::view-transition-old(root){animation:vt-out .22s var(--ease) both}
::view-transition-new(root){animation:vt-in .34s var(--ease) both}
@keyframes vt-out{to{opacity:0;transform:translateX(calc(var(--dir) * -28px))}}
@keyframes vt-in{from{opacity:0;transform:translateX(calc(var(--dir) * 40px))}}
body.ready .card{animation:rise .5s var(--ease) backwards;animation-delay:calc(var(--i,0) * 45ms)}
@keyframes rise{from{opacity:0;transform:translateY(10px) scale(.985)}}
.pop{animation:pop .36s var(--ease)}
@keyframes pop{from{opacity:0;transform:translateY(4px);filter:blur(3px)}}
a.card,.back{transition:transform .18s var(--ease),box-shadow .18s var(--ease)}
a.card:active,.back:active{transform:scale(.98)}
@media (hover:hover){a.card:hover,.back:hover{transform:translateY(-1px)}}
@media (prefers-reduced-motion:reduce){*,::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important;transition:none!important}}
@@PAGECSS@@
</style></head>"""

MAIN_CSS = r"""
:root{--dir:-1}
/* power hero */
.hero{display:grid;grid-template-columns:auto 1fr;gap:0 14px;align-items:center;padding:18px}
.badge{width:48px;height:48px;border-radius:50%;display:grid;place-items:center;background:var(--neutralbg);color:var(--mute)}
.badge .ic{width:24px;height:24px}
.hero.ok .badge{background:var(--okbg);color:var(--ok)}.hero.warn .badge{background:var(--warnbg);color:var(--warn)}
.hero.bad .badge{background:var(--badbg);color:var(--bad)}
.htitle{font-size:20px;font-weight:700;letter-spacing:-.02em;line-height:1.25}
.hdesc{color:var(--mute);font-size:14px;margin-top:2px}
.tip{grid-column:1/-1;margin-top:14px;padding:10px 12px;border-radius:12px;background:var(--card2);font-size:14px}
.hero.warn .tip{background:var(--warnbg)}.hero.bad .tip{background:var(--badbg)}
/* tiles */
.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.tiles.two{grid-template-columns:repeat(2,minmax(0,1fr))}
.tile{padding:14px 14px 12px}
.tl{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--mute)}
.tl .ic{width:16px;height:16px}
.tv{font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.2;margin-top:4px;white-space:nowrap}
.tv small{font-size:14px;font-weight:600;color:var(--mute);margin-left:1px}
.tv.warn{color:var(--warn)}.tv.bad{color:var(--bad)}
.tile .spark{height:24px;margin-top:6px}
.ts{font-size:17px;font-weight:700;margin-top:4px}
.tsub{font-size:13px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* muse */
.mdesc{font-size:14px;color:var(--mute);margin:-4px 0 10px}
.rows{display:grid;gap:8px;font-size:14px}
.rows>div{display:flex;justify-content:space-between;align-items:center;gap:12px}
.st{display:inline-flex;align-items:center;gap:6px;color:var(--mute);font-weight:500}
.st.ok{color:var(--ok)}.st.bad{color:var(--bad)}.st.warn{color:var(--warn)}
/* details link */
.nav{display:flex;align-items:center;gap:12px;padding:14px 16px}
.nav .t{flex:1;min-width:0}
.nav b{display:block;font-size:15px}
.nav span{display:block;font-size:13px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav .ic{color:var(--faint)}
@media (max-width:360px){.tv{font-size:22px}.tile{padding:12px}}
"""

DETAILS_CSS = r"""
:root{--dir:1}
h2.sec{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);margin:24px 4px 10px}
h2.sec:first-child{margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
@media (min-width:760px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
.grid2{display:grid;grid-template-columns:1fr;gap:12px;align-items:start}
@media (min-width:760px){.grid2{grid-template-columns:repeat(2,minmax(0,1fr))}}
.metric{padding:14px 14px 10px}
.metric .ctitle{margin-bottom:4px;font-size:13px}
.val{font-size:22px;font-weight:700;letter-spacing:-.02em;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.val small{font-size:13px;font-weight:600;color:var(--mute);margin-left:2px}
.metric.hov .val{color:var(--accent)}
.sub{font-size:12px;color:var(--mute);min-height:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.metric .spark{cursor:crosshair}
.cores{display:flex;gap:4px;margin-top:6px;height:16px}
.cores i{flex:1;background:var(--track);border-radius:4px;position:relative;overflow:hidden}
.cores i b{position:absolute;left:0;right:0;bottom:0;background:var(--accent);transition:height .4s ease}
.legend{display:flex;gap:10px;font-size:12px;color:var(--mute)}
.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:7px 16px;font-size:14px}
.kv>div:nth-child(odd){color:var(--mute)}
.kv>div:nth-child(even){text-align:right;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.kv+.kv,.kv+.list{margin-top:12px}
.flags{display:grid;grid-template-columns:1fr auto auto;gap:7px 10px;align-items:center;font-size:14px;margin-bottom:14px}
.flags .h{font-size:12px;color:var(--faint);font-weight:600}
.flags .c{text-align:center}
.list{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.list li{display:flex;align-items:center;gap:10px;font-size:14px;min-width:0}
.list .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.list .nm small{display:block;color:var(--faint);font-size:12px}
.list .rt{text-align:right;font-variant-numeric:tabular-nums;flex:none}
.mini{width:48px;height:6px;background:var(--track);border-radius:99px;overflow:hidden;flex:none}
.mini b{display:block;height:100%;background:var(--accent);border-radius:99px}
.tl li{align-items:flex-start}
.tl .when{flex:none;color:var(--faint);font-size:12px;padding-top:2px;font-variant-numeric:tabular-nums}
.tl .msg{flex:1;min-width:0;overflow-wrap:anywhere}
.ldot{width:8px;height:8px;border-radius:50%;margin-top:6px;flex:none;background:var(--faint)}
.ldot.bad{background:var(--bad)}.ldot.ok{background:var(--ok)}.ldot.warn{background:var(--warn)}.ldot.info{background:var(--accent)}
.bar{height:6px;background:var(--track);border-radius:99px;overflow:hidden;margin:6px 0 2px}
.bar b{display:block;height:100%;background:var(--accent);border-radius:99px;transition:width .5s ease}
.bar b.warn{background:var(--warn)}.bar b.bad{background:var(--bad)}
.bars>div+div{margin-top:12px}
.bars .l{display:flex;justify-content:space-between;font-size:14px;gap:8px}
.big2{font-size:17px;font-weight:700;margin:-2px 0 12px;overflow-wrap:anywhere}
"""

MASCOT_SVG = '<svg viewBox="4 4 92 92" class="mascot" aria-hidden="true"><defs><radialGradient id="mBg" cx="50%" cy="40%" r="70%"><stop offset="0" stop-color="#1C1C1E"/><stop offset="1" stop-color="#000000"/></radialGradient><radialGradient id="mFur" gradientUnits="userSpaceOnUse" cx="44" cy="30" r="62"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".5" stop-color="#F4F1EC"/><stop offset="1" stop-color="#CBC4B8"/></radialGradient><radialGradient id="mFace" gradientUnits="userSpaceOnUse" cx="48" cy="40" r="26"><stop offset="0" stop-color="#F3E6D6"/><stop offset=".75" stop-color="#E6D3BD"/><stop offset="1" stop-color="#CDB59B"/></radialGradient><filter id="mFuzz" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".75" numOctaves="2" seed="3"/><feDisplacementMap in="SourceGraphic" scale="5" xChannelSelector="R" yChannelSelector="G"/></filter><filter id="mSoft"><feGaussianBlur stdDeviation="1.6"/></filter></defs><circle cx="50" cy="50" r="50" fill="url(#mBg)"/><g filter="url(#mFuzz)"><path d="M50 8C30 8 20 23 19 42C18 58 12 72 9 108H91C88 72 82 58 81 42C80 23 70 8 50 8Z" fill="url(#mFur)"/></g><g fill="none" stroke-linecap="round" opacity=".8"><path d="M39.2 28.9q-0.1 1.7 -0.7 3.5" stroke="#F1EDE6" stroke-width="0.66"/><path d="M70.6 42.7q-0.0 1.8 1.6 3.6" stroke="#E2DDD4" stroke-width="0.44"/><path d="M56.7 11.0q-0.6 2.3 0.8 4.7" stroke="#E2DDD4" stroke-width="0.44"/><path d="M29.4 29.2q-0.5 1.4 -2.0 2.9" stroke="#F1EDE6" stroke-width="0.66"/><path d="M60.7 29.9q-0.5 1.7 1.1 3.5" stroke="#FFFFFF" stroke-width="0.66"/><path d="M59.4 20.8q0.2 2.5 1.0 5.0" stroke="#E2DDD4" stroke-width="0.57"/><path d="M35.1 32.1q-0.7 1.7 -0.9 3.4" stroke="#E2DDD4" stroke-width="0.79"/><path d="M64.9 29.4q0.3 1.2 1.7 2.5" stroke="#F1EDE6" stroke-width="0.48"/><path d="M49.3 27.3q0.2 2.6 0.3 5.2" stroke="#F1EDE6" stroke-width="0.56"/><path d="M38.3 22.1q-0.9 1.8 -0.3 3.6" stroke="#F1EDE6" stroke-width="0.62"/><path d="M59.4 29.9q1.5 2.2 1.6 4.3" stroke="#E2DDD4" stroke-width="0.54"/><path d="M40.0 17.6q-1.1 1.9 -1.6 3.7" stroke="#FFFFFF" stroke-width="0.63"/><path d="M32.5 32.7q0.5 2.0 -1.3 3.9" stroke="#E2DDD4" stroke-width="0.45"/><path d="M45.8 18.1q0.9 2.6 0.6 5.3" stroke="#F1EDE6" stroke-width="0.72"/><path d="M78.7 48.5q-0.3 1.1 1.9 2.2" stroke="#FBF9F5" stroke-width="0.52"/><path d="M30.9 29.2q-1.4 1.7 -1.3 3.5" stroke="#E2DDD4" stroke-width="0.64"/><path d="M57.8 23.7q0.9 2.7 -0.1 5.4" stroke="#FFFFFF" stroke-width="0.61"/><path d="M80.2 34.3q0.5 1.4 2.2 2.8" stroke="#E2DDD4" stroke-width="0.46"/><path d="M57.8 28.9q-0.7 2.0 -0.0 3.9" stroke="#F1EDE6" stroke-width="0.67"/><path d="M24.4 39.7q-0.5 1.9 -2.5 3.7" stroke="#FFFFFF" stroke-width="0.79"/><path d="M57.2 26.8q-0.2 2.1 0.2 4.2" stroke="#FFFFFF" stroke-width="0.47"/><path d="M48.8 9.6q-0.7 2.1 -0.1 4.2" stroke="#F1EDE6" stroke-width="0.73"/><path d="M48.1 15.1q0.9 2.0 -0.1 3.9" stroke="#F1EDE6" stroke-width="0.48"/><path d="M52.5 27.7q0.9 2.8 0.4 5.7" stroke="#F1EDE6" stroke-width="0.64"/><path d="M72.7 41.8q0.6 1.8 1.9 3.6" stroke="#FBF9F5" stroke-width="0.68"/><path d="M73.5 27.6q0.1 1.8 1.1 3.6" stroke="#FBF9F5" stroke-width="0.50"/><path d="M49.3 14.3q0.3 2.5 1.1 5.0" stroke="#FBF9F5" stroke-width="0.71"/><path d="M74.9 45.9q1.7 1.8 2.6 3.6" stroke="#F1EDE6" stroke-width="0.45"/><path d="M25.9 40.3q0.3 1.3 -2.2 2.6" stroke="#FFFFFF" stroke-width="0.62"/><path d="M64.1 17.2q0.9 2.5 0.2 5.0" stroke="#FBF9F5" stroke-width="0.62"/><path d="M24.3 30.4q0.2 1.8 -2.3 3.6" stroke="#E2DDD4" stroke-width="0.61"/><path d="M63.5 33.0q-0.6 2.7 1.1 5.5" stroke="#E2DDD4" stroke-width="0.76"/><path d="M22.2 33.4q-0.7 2.2 -1.4 4.5" stroke="#FBF9F5" stroke-width="0.43"/><path d="M73.8 29.0q-0.3 2.4 1.3 4.8" stroke="#FBF9F5" stroke-width="0.77"/><path d="M32.6 33.5q-0.3 1.4 -1.7 2.8" stroke="#F1EDE6" stroke-width="0.65"/><path d="M66.6 38.5q1.1 1.7 2.5 3.4" stroke="#E2DDD4" stroke-width="0.77"/><path d="M68.7 40.9q1.2 1.9 1.6 3.8" stroke="#FBF9F5" stroke-width="0.68"/><path d="M65.6 33.9q-0.4 2.3 1.1 4.6" stroke="#FFFFFF" stroke-width="0.56"/><path d="M51.5 17.6q0.3 1.8 0.6 3.6" stroke="#FBF9F5" stroke-width="0.50"/><path d="M30.5 46.8q0.3 0.9 -1.7 1.8" stroke="#FFFFFF" stroke-width="0.61"/><path d="M59.0 20.4q0.2 2.4 0.9 4.9" stroke="#E2DDD4" stroke-width="0.63"/><path d="M31.3 27.7q0.5 2.7 -1.1 5.3" stroke="#FBF9F5" stroke-width="0.77"/><path d="M31.8 39.9q-1.0 1.2 -1.6 2.4" stroke="#FFFFFF" stroke-width="0.51"/><path d="M38.4 30.2q0.0 2.7 -0.9 5.4" stroke="#F1EDE6" stroke-width="0.48"/><path d="M80.9 35.5q0.4 2.2 2.2 4.5" stroke="#E2DDD4" stroke-width="0.49"/><path d="M60.9 27.4q0.4 2.5 1.8 5.0" stroke="#E2DDD4" stroke-width="0.50"/><path d="M34.2 20.1q-0.7 1.7 -2.0 3.5" stroke="#FFFFFF" stroke-width="0.58"/><path d="M51.2 22.5q1.1 1.7 0.9 3.5" stroke="#FBF9F5" stroke-width="0.83"/><path d="M28.9 41.3q-1.2 1.4 -2.5 2.9" stroke="#FBF9F5" stroke-width="0.76"/><path d="M75.5 34.2q0.7 1.1 2.1 2.2" stroke="#E2DDD4" stroke-width="0.71"/><path d="M31.7 43.6q-1.4 1.6 -1.9 3.2" stroke="#FFFFFF" stroke-width="0.69"/><path d="M65.8 36.2q1.2 1.1 1.7 2.2" stroke="#E2DDD4" stroke-width="0.42"/><path d="M74.6 49.5q-0.3 1.7 2.2 3.3" stroke="#FBF9F5" stroke-width="0.81"/><path d="M72.1 47.4q1.0 1.9 2.4 3.9" stroke="#FBF9F5" stroke-width="0.54"/><path d="M50.0 24.7q-0.6 1.7 -0.3 3.5" stroke="#FFFFFF" stroke-width="0.43"/><path d="M50.6 9.6q-0.1 2.0 0.1 4.0" stroke="#E2DDD4" stroke-width="0.70"/><path d="M54.6 11.7q-0.2 1.9 1.1 3.8" stroke="#FBF9F5" stroke-width="0.56"/><path d="M75.2 32.3q0.3 1.5 1.9 3.0" stroke="#FFFFFF" stroke-width="0.77"/><path d="M22.2 48.5q-1.5 1.5 -1.9 3.1" stroke="#E2DDD4" stroke-width="0.79"/><path d="M61.5 26.5q0.1 2.0 0.5 4.0" stroke="#FBF9F5" stroke-width="0.53"/><path d="M26.2 49.7q-1.2 1.6 -2.7 3.2" stroke="#FFFFFF" stroke-width="0.83"/><path d="M36.7 26.3q-0.6 1.5 -1.8 3.1" stroke="#FBF9F5" stroke-width="0.52"/><path d="M64.9 34.7q0.7 1.3 1.7 2.6" stroke="#E2DDD4" stroke-width="0.43"/><path d="M37.4 28.5q0.2 2.2 -1.1 4.3" stroke="#E2DDD4" stroke-width="0.74"/><path d="M66.5 25.9q-0.4 2.3 1.1 4.6" stroke="#E2DDD4" stroke-width="0.73"/><path d="M66.9 36.3q1.2 1.7 1.9 3.5" stroke="#FFFFFF" stroke-width="0.77"/><path d="M58.4 12.6q-0.2 2.4 1.0 4.8" stroke="#FFFFFF" stroke-width="0.44"/><path d="M63.8 13.6q-0.7 2.2 0.6 4.4" stroke="#FFFFFF" stroke-width="0.68"/><path d="M63.8 23.7q0.6 2.6 0.2 5.3" stroke="#FFFFFF" stroke-width="0.70"/><path d="M21.1 42.6q-1.0 0.9 -1.7 1.8" stroke="#FBF9F5" stroke-width="0.52"/><path d="M61.5 22.7q1.2 1.5 1.3 3.0" stroke="#F1EDE6" stroke-width="0.74"/><path d="M60.1 18.2q-0.5 1.9 -0.1 3.8" stroke="#F1EDE6" stroke-width="0.68"/><path d="M26.6 37.4q-1.6 1.9 -2.5 3.9" stroke="#FBF9F5" stroke-width="0.70"/><path d="M34.0 24.9q-1.2 2.0 -1.4 4.0" stroke="#FBF9F5" stroke-width="0.55"/><path d="M25.4 41.8q-0.5 0.9 -1.7 1.8" stroke="#E2DDD4" stroke-width="0.84"/><path d="M38.7 13.2q-0.8 1.8 0.1 3.6" stroke="#F1EDE6" stroke-width="0.82"/><path d="M21.8 34.9q-0.3 1.9 -2.4 3.8" stroke="#FBF9F5" stroke-width="0.63"/><path d="M72.4 38.8q1.0 2.3 2.0 4.7" stroke="#E2DDD4" stroke-width="0.55"/><path d="M28.8 37.8q-1.7 1.6 -2.5 3.3" stroke="#F1EDE6" stroke-width="0.77"/><path d="M19.8 35.5q-1.1 2.1 -2.2 4.2" stroke="#F1EDE6" stroke-width="0.45"/><path d="M39.3 13.9q-0.0 2.4 -1.9 4.8" stroke="#FFFFFF" stroke-width="0.54"/><path d="M22.0 44.4q0.4 1.2 -1.7 2.4" stroke="#E2DDD4" stroke-width="0.63"/><path d="M30.2 33.7q0.2 2.6 -1.3 5.1" stroke="#E2DDD4" stroke-width="0.80"/><path d="M76.2 44.0q1.0 0.9 1.7 1.8" stroke="#E2DDD4" stroke-width="0.68"/><path d="M21.3 33.8q-0.6 1.9 -2.4 3.8" stroke="#FBF9F5" stroke-width="0.62"/><path d="M39.3 25.7q-0.7 2.8 -0.7 5.6" stroke="#FBF9F5" stroke-width="0.55"/><path d="M54.3 21.1q-0.7 1.9 -0.3 3.8" stroke="#E2DDD4" stroke-width="0.65"/><path d="M46.6 22.1q0.2 2.2 0.2 4.4" stroke="#FBF9F5" stroke-width="0.46"/><path d="M40.7 29.2q-0.3 1.7 -1.3 3.5" stroke="#FFFFFF" stroke-width="0.73"/><path d="M43.4 21.3q-0.5 2.1 -0.5 4.2" stroke="#FFFFFF" stroke-width="0.63"/><path d="M55.5 22.0q0.9 2.2 0.9 4.5" stroke="#FBF9F5" stroke-width="0.46"/><path d="M72.9 40.7q0.3 1.3 2.1 2.5" stroke="#FFFFFF" stroke-width="0.47"/><path d="M43.0 14.6q0.0 2.8 0.2 5.7" stroke="#FFFFFF" stroke-width="0.58"/><path d="M80.1 41.5q0.3 1.5 2.7 3.1" stroke="#FFFFFF" stroke-width="0.51"/><path d="M20.5 31.5q-0.4 1.4 -2.5 2.8" stroke="#E2DDD4" stroke-width="0.46"/><path d="M63.9 35.8q-0.6 2.2 1.1 4.5" stroke="#F1EDE6" stroke-width="0.82"/><path d="M60.2 20.6q-0.6 2.5 0.8 5.1" stroke="#F1EDE6" stroke-width="0.64"/><path d="M56.2 21.7q-1.0 2.4 -0.0 4.8" stroke="#F1EDE6" stroke-width="0.84"/><path d="M35.2 28.5q-0.1 1.9 -0.7 3.9" stroke="#FBF9F5" stroke-width="0.43"/><path d="M42.3 17.1q0.4 1.7 -1.2 3.4" stroke="#E2DDD4" stroke-width="0.45"/><path d="M31.3 30.3q-0.2 1.8 -1.8 3.5" stroke="#E2DDD4" stroke-width="0.57"/><path d="M44.2 29.0q-1.3 2.5 -1.3 5.0" stroke="#E2DDD4" stroke-width="0.83"/><path d="M32.8 18.9q0.1 1.6 -1.4 3.2" stroke="#F1EDE6" stroke-width="0.47"/><path d="M60.5 19.0q1.3 1.9 1.5 3.9" stroke="#FFFFFF" stroke-width="0.82"/><path d="M28.3 37.0q-1.5 1.6 -2.7 3.2" stroke="#FFFFFF" stroke-width="0.72"/><path d="M29.0 33.4q-1.2 1.8 -1.4 3.5" stroke="#FFFFFF" stroke-width="0.81"/><path d="M39.3 28.1q-1.0 2.6 -0.2 5.2" stroke="#E2DDD4" stroke-width="0.77"/><path d="M75.0 48.6q-0.4 1.3 1.6 2.5" stroke="#E2DDD4" stroke-width="0.82"/><path d="M19.4 34.8q0.0 1.1 -2.0 2.3" stroke="#E2DDD4" stroke-width="0.46"/><path d="M62.7 29.5q0.1 2.0 1.4 3.9" stroke="#E2DDD4" stroke-width="0.43"/><path d="M20.0 93.9q-1.5 1.2 -1.8 2.5" stroke="#E2DDD4" stroke-width="0.81"/><path d="M72.6 87.8q0.5 1.3 2.5 2.7" stroke="#ECE7DF" stroke-width="0.88"/><path d="M31.0 71.2q-0.8 2.1 -1.3 4.2" stroke="#E2DDD4" stroke-width="0.77"/><path d="M20.9 69.4q0.4 1.8 -0.9 3.7" stroke="#E2DDD4" stroke-width="0.66"/><path d="M86.5 75.6q0.4 1.5 2.0 3.0" stroke="#FFFFFF" stroke-width="0.51"/><path d="M28.9 82.3q-0.2 1.6 -2.0 3.1" stroke="#D8D2C7" stroke-width="0.72"/><path d="M37.5 96.8q-1.1 2.8 -0.9 5.6" stroke="#D8D2C7" stroke-width="0.63"/><path d="M65.1 97.0q0.4 2.4 1.0 4.8" stroke="#D8D2C7" stroke-width="0.89"/><path d="M78.7 65.7q-0.5 1.8 1.1 3.6" stroke="#FFFFFF" stroke-width="0.89"/><path d="M73.6 79.4q1.4 1.9 2.0 3.7" stroke="#D8D2C7" stroke-width="0.79"/><path d="M68.8 65.0q-0.2 2.9 0.6 5.8" stroke="#FBF9F5" stroke-width="0.57"/><path d="M49.3 98.1q-0.5 2.1 0.1 4.3" stroke="#ECE7DF" stroke-width="0.85"/><path d="M26.4 74.0q-0.8 2.1 -2.8 4.3" stroke="#D8D2C7" stroke-width="0.74"/><path d="M73.6 92.9q1.3 1.1 1.8 2.2" stroke="#D8D2C7" stroke-width="0.83"/><path d="M68.6 75.0q-0.2 1.7 1.4 3.4" stroke="#FBF9F5" stroke-width="0.54"/><path d="M76.8 90.6q1.3 1.5 2.5 3.0" stroke="#F1EDE6" stroke-width="0.88"/><path d="M74.8 94.3q0.2 1.8 1.5 3.7" stroke="#D8D2C7" stroke-width="0.47"/><path d="M71.6 82.0q1.5 1.8 2.8 3.7" stroke="#ECE7DF" stroke-width="0.63"/><path d="M27.8 96.6q-0.2 1.9 -0.6 3.8" stroke="#FFFFFF" stroke-width="0.48"/><path d="M72.5 92.5q-0.2 2.2 2.0 4.4" stroke="#D8D2C7" stroke-width="0.63"/><path d="M44.9 106.1q-1.1 2.4 -0.7 4.7" stroke="#F1EDE6" stroke-width="0.70"/><path d="M32.3 96.0q-1.1 2.3 -2.6 4.7" stroke="#D8D2C7" stroke-width="0.63"/><path d="M18.8 95.4q-1.2 1.7 -1.6 3.4" stroke="#E2DDD4" stroke-width="0.63"/><path d="M71.6 69.6q0.4 1.8 0.9 3.6" stroke="#F1EDE6" stroke-width="0.81"/><path d="M25.2 93.9q-1.4 1.7 -2.6 3.4" stroke="#ECE7DF" stroke-width="0.58"/><path d="M12.9 78.9q-0.1 1.5 -2.3 3.1" stroke="#D8D2C7" stroke-width="0.59"/><path d="M61.3 70.3q0.8 1.8 1.8 3.6" stroke="#F1EDE6" stroke-width="0.62"/><path d="M76.4 70.6q1.2 1.3 1.9 2.6" stroke="#D8D2C7" stroke-width="0.73"/><path d="M31.7 71.8q-1.5 2.1 -1.9 4.2" stroke="#FBF9F5" stroke-width="0.52"/><path d="M35.1 93.5q-1.4 2.0 -2.6 4.0" stroke="#FBF9F5" stroke-width="0.83"/><path d="M34.6 63.7q-0.5 2.1 -1.4 4.3" stroke="#F1EDE6" stroke-width="0.80"/><path d="M34.3 68.6q-0.8 1.9 -1.8 3.9" stroke="#FBF9F5" stroke-width="0.65"/><path d="M81.6 85.0q1.2 1.2 2.1 2.4" stroke="#FFFFFF" stroke-width="0.83"/><path d="M60.4 65.5q-0.3 2.3 -0.1 4.7" stroke="#FFFFFF" stroke-width="0.68"/><path d="M38.1 70.6q-1.1 2.4 -2.4 4.8" stroke="#F1EDE6" stroke-width="0.68"/><path d="M78.2 88.3q0.1 1.8 2.9 3.7" stroke="#E2DDD4" stroke-width="0.90"/><path d="M46.0 59.7q-0.4 3.0 -1.2 6.0" stroke="#D8D2C7" stroke-width="0.76"/><path d="M45.5 66.6q-0.4 2.7 0.4 5.3" stroke="#ECE7DF" stroke-width="0.85"/><path d="M44.5 104.1q1.0 2.5 0.5 5.0" stroke="#D8D2C7" stroke-width="0.72"/><path d="M31.2 71.4q-0.7 1.7 -1.7 3.3" stroke="#F1EDE6" stroke-width="0.87"/><path d="M34.2 60.9q-1.3 2.5 -1.9 4.9" stroke="#FBF9F5" stroke-width="0.47"/><path d="M74.0 63.3q0.8 2.3 1.4 4.6" stroke="#E2DDD4" stroke-width="0.56"/><path d="M14.7 76.9q-0.9 1.7 -2.0 3.4" stroke="#ECE7DF" stroke-width="0.71"/><path d="M27.9 98.8q0.1 1.9 -1.2 3.8" stroke="#E2DDD4" stroke-width="0.58"/><path d="M23.7 80.3q0.1 2.3 -2.4 4.5" stroke="#ECE7DF" stroke-width="0.78"/><path d="M49.6 66.3q-0.3 2.7 -0.6 5.3" stroke="#ECE7DF" stroke-width="0.85"/><path d="M66.9 93.6q-0.7 1.8 1.0 3.5" stroke="#ECE7DF" stroke-width="0.59"/><path d="M19.9 79.2q-1.4 1.2 -2.2 2.3" stroke="#ECE7DF" stroke-width="0.73"/><path d="M27.0 84.3q-1.3 1.4 -2.0 2.7" stroke="#E2DDD4" stroke-width="0.48"/><path d="M70.1 98.3q1.6 2.4 2.2 4.7" stroke="#E2DDD4" stroke-width="0.74"/><path d="M24.9 75.5q0.3 1.8 -2.0 3.7" stroke="#F1EDE6" stroke-width="0.67"/><path d="M60.6 93.4q-0.2 1.5 1.5 3.0" stroke="#D8D2C7" stroke-width="0.48"/><path d="M53.8 68.9q-0.5 3.0 0.7 6.1" stroke="#D8D2C7" stroke-width="0.68"/><path d="M29.7 66.0q-0.5 2.3 -1.8 4.6" stroke="#E2DDD4" stroke-width="0.59"/><path d="M85.1 89.0q-0.3 2.2 2.2 4.3" stroke="#FFFFFF" stroke-width="0.79"/><path d="M16.7 86.7q-1.4 1.3 -2.0 2.7" stroke="#D8D2C7" stroke-width="0.74"/><path d="M76.3 98.3q-0.2 3.0 1.1 6.0" stroke="#E2DDD4" stroke-width="0.57"/><path d="M22.9 76.0q-1.1 2.0 -2.0 4.0" stroke="#F1EDE6" stroke-width="0.87"/><path d="M67.6 73.3q1.3 1.7 1.6 3.4" stroke="#F1EDE6" stroke-width="0.54"/><path d="M70.1 101.8q0.7 1.9 1.8 3.9" stroke="#FFFFFF" stroke-width="0.86"/><path d="M27.3 66.6q-0.6 2.9 -1.7 5.7" stroke="#FBF9F5" stroke-width="0.76"/><path d="M68.0 67.9q0.2 2.1 2.0 4.2" stroke="#D8D2C7" stroke-width="0.63"/><path d="M23.4 72.0q-1.3 1.1 -1.8 2.3" stroke="#FBF9F5" stroke-width="0.87"/><path d="M36.8 94.2q0.3 1.9 -0.2 3.9" stroke="#F1EDE6" stroke-width="0.47"/><path d="M69.8 87.7q-0.0 2.4 1.9 4.8" stroke="#FBF9F5" stroke-width="0.85"/><path d="M83.3 91.3q-0.2 2.7 2.0 5.3" stroke="#D8D2C7" stroke-width="0.54"/><path d="M87.0 87.0q-0.2 2.2 2.2 4.5" stroke="#F1EDE6" stroke-width="0.73"/><path d="M27.0 84.1q-1.2 1.5 -2.6 3.0" stroke="#ECE7DF" stroke-width="0.64"/><path d="M75.3 84.1q0.5 1.5 2.7 2.9" stroke="#ECE7DF" stroke-width="0.80"/><path d="M26.4 70.9q-0.2 2.0 -2.5 3.9" stroke="#E2DDD4" stroke-width="0.65"/><path d="M53.9 65.1q-0.3 2.5 0.8 5.0" stroke="#E2DDD4" stroke-width="0.71"/><path d="M43.4 99.6q0.3 2.2 -0.5 4.4" stroke="#E2DDD4" stroke-width="0.45"/><path d="M20.4 83.1q-0.6 1.3 -2.0 2.6" stroke="#ECE7DF" stroke-width="0.88"/><path d="M18.9 80.1q0.1 1.8 -2.7 3.5" stroke="#D8D2C7" stroke-width="0.67"/><path d="M74.9 95.0q1.2 1.8 2.7 3.6" stroke="#E2DDD4" stroke-width="0.73"/><path d="M32.7 96.0q-1.3 2.8 -1.5 5.6" stroke="#F1EDE6" stroke-width="0.46"/><path d="M57.0 97.6q-0.3 2.5 -0.3 5.0" stroke="#F1EDE6" stroke-width="0.56"/><path d="M20.5 86.7q-0.5 1.4 -2.7 2.8" stroke="#ECE7DF" stroke-width="0.71"/><path d="M13.9 78.9q-1.1 1.4 -2.5 2.7" stroke="#FFFFFF" stroke-width="0.65"/><path d="M54.6 62.5q0.6 2.4 -0.5 4.9" stroke="#D8D2C7" stroke-width="0.68"/><path d="M46.2 103.6q0.1 2.5 -1.1 5.1" stroke="#D8D2C7" stroke-width="0.78"/><path d="M28.3 71.7q-1.3 2.1 -2.8 4.2" stroke="#F1EDE6" stroke-width="0.90"/><path d="M66.7 99.7q-0.3 1.7 1.5 3.5" stroke="#ECE7DF" stroke-width="0.78"/><path d="M27.6 88.1q-1.1 1.3 -1.9 2.5" stroke="#FFFFFF" stroke-width="0.66"/><path d="M86.0 83.8q1.6 1.1 2.1 2.1" stroke="#ECE7DF" stroke-width="0.66"/><path d="M69.9 97.6q1.4 2.4 1.9 4.8" stroke="#FFFFFF" stroke-width="0.77"/><path d="M22.3 71.3q-0.2 2.4 -1.6 4.9" stroke="#F1EDE6" stroke-width="0.77"/><path d="M69.8 65.3q0.1 2.1 1.7 4.2" stroke="#F1EDE6" stroke-width="0.77"/><path d="M69.9 72.2q-0.1 2.3 1.9 4.7" stroke="#FFFFFF" stroke-width="0.67"/><path d="M86.0 84.8q1.5 1.5 2.6 3.0" stroke="#F1EDE6" stroke-width="0.60"/><path d="M85.7 83.5q0.0 1.5 1.7 2.9" stroke="#D8D2C7" stroke-width="0.52"/><path d="M57.5 58.7q0.3 2.0 0.4 4.0" stroke="#FBF9F5" stroke-width="0.54"/><path d="M29.1 84.0q-1.0 1.3 -2.2 2.6" stroke="#F1EDE6" stroke-width="0.88"/><path d="M58.2 102.3q-0.5 2.8 1.0 5.5" stroke="#FBF9F5" stroke-width="0.61"/><path d="M74.2 87.7q0.4 1.2 1.8 2.3" stroke="#FFFFFF" stroke-width="0.73"/><path d="M35.8 64.4q-0.7 1.9 -1.7 3.7" stroke="#FBF9F5" stroke-width="0.89"/><path d="M88.0 81.1q1.5 1.1 2.0 2.2" stroke="#E2DDD4" stroke-width="0.81"/><path d="M30.5 68.2q0.5 1.9 -1.3 3.9" stroke="#ECE7DF" stroke-width="0.75"/><path d="M67.0 62.6q0.9 3.0 1.2 6.0" stroke="#F1EDE6" stroke-width="0.51"/><path d="M63.7 67.1q0.2 1.8 1.6 3.6" stroke="#ECE7DF" stroke-width="0.89"/><path d="M37.2 65.2q-0.4 2.9 -0.4 5.8" stroke="#F1EDE6" stroke-width="0.59"/><path d="M21.7 84.3q-1.1 1.3 -2.6 2.6" stroke="#ECE7DF" stroke-width="0.83"/><path d="M83.4 89.9q-0.1 2.4 2.0 4.9" stroke="#ECE7DF" stroke-width="0.73"/><path d="M71.0 83.3q0.2 2.0 2.2 4.1" stroke="#E2DDD4" stroke-width="0.71"/><path d="M64.7 69.9q-0.1 2.6 1.6 5.2" stroke="#FFFFFF" stroke-width="0.81"/><path d="M68.2 102.2q0.7 2.8 1.1 5.5" stroke="#FBF9F5" stroke-width="0.80"/><path d="M62.9 68.9q1.0 2.2 1.7 4.4" stroke="#FFFFFF" stroke-width="0.75"/><path d="M67.1 91.7q0.6 2.3 2.2 4.7" stroke="#FBF9F5" stroke-width="0.48"/><path d="M27.0 85.0q-0.6 1.5 -2.4 3.0" stroke="#F1EDE6" stroke-width="0.45"/><path d="M65.8 66.4q1.1 2.5 1.5 4.9" stroke="#ECE7DF" stroke-width="0.64"/><path d="M83.0 82.0q0.9 1.5 2.1 3.0" stroke="#E2DDD4" stroke-width="0.72"/><path d="M34.6 60.4q-0.5 2.9 -1.7 5.7" stroke="#FFFFFF" stroke-width="0.79"/><path d="M65.2 94.3q-0.4 1.8 1.3 3.5" stroke="#F1EDE6" stroke-width="0.61"/><path d="M20.1 85.0q-0.7 1.2 -2.1 2.3" stroke="#FFFFFF" stroke-width="0.56"/><path d="M74.6 87.4q0.4 1.5 2.4 2.9" stroke="#ECE7DF" stroke-width="0.84"/><path d="M36.2 94.8q-0.9 1.9 -1.1 3.7" stroke="#F1EDE6" stroke-width="0.58"/><path d="M22.4 71.5q0.1 1.7 -1.3 3.4" stroke="#FFFFFF" stroke-width="0.70"/><path d="M75.0 87.1q1.4 1.2 2.0 2.4" stroke="#FBF9F5" stroke-width="0.79"/><path d="M77.7 89.0q-0.1 1.6 2.1 3.3" stroke="#F1EDE6" stroke-width="0.76"/><path d="M22.8 70.1q-0.8 1.8 -2.5 3.5" stroke="#D8D2C7" stroke-width="0.50"/></g><rect x="29" y="30" width="42" height="33" rx="16" fill="url(#mFace)"/><g filter="url(#mFuzz)"><rect x="29" y="30" width="42" height="33" rx="16" fill="none" stroke="#F7F4EE" stroke-width="5"/></g><g fill="none" stroke-linecap="round" opacity=".8"><path d="M40.3 40.2q0.0 1.8 -1.0 3.6" stroke="#FBF9F5" stroke-width="0.79"/><path d="M37.0 39.8q-1.0 1.6 -1.2 3.3" stroke="#FFFFFF" stroke-width="0.55"/><path d="M46.4 31.9q0.2 1.2 0.3 2.5" stroke="#FFFFFF" stroke-width="0.77"/><path d="M61.4 36.9q-0.5 1.2 1.2 2.4" stroke="#F1EDE6" stroke-width="0.58"/><path d="M55.5 29.7q0.1 1.4 1.0 2.8" stroke="#FFFFFF" stroke-width="0.45"/><path d="M48.4 29.6q-1.0 1.6 0.1 3.1" stroke="#F1EDE6" stroke-width="0.47"/><path d="M62.8 43.4q-0.6 0.6 1.3 1.3" stroke="#F1EDE6" stroke-width="0.66"/><path d="M47.3 30.9q0.6 1.5 0.4 2.9" stroke="#F1EDE6" stroke-width="0.78"/><path d="M57.7 38.3q0.3 1.5 1.1 3.1" stroke="#FBF9F5" stroke-width="0.80"/><path d="M38.0 43.1q-0.2 1.0 -1.8 1.9" stroke="#F1EDE6" stroke-width="0.45"/><path d="M40.2 32.9q-0.4 1.6 -1.3 3.2" stroke="#FFFFFF" stroke-width="0.55"/><path d="M69.0 40.9q1.3 0.9 1.2 1.8" stroke="#FFFFFF" stroke-width="0.57"/><path d="M57.3 32.9q0.7 1.5 0.4 3.0" stroke="#FBF9F5" stroke-width="0.75"/><path d="M52.8 34.8q0.3 2.0 -0.5 3.9" stroke="#F1EDE6" stroke-width="0.56"/><path d="M56.4 29.5q-0.1 1.5 0.9 3.1" stroke="#FBF9F5" stroke-width="0.83"/><path d="M39.5 36.7q-0.9 1.5 -1.2 3.1" stroke="#FBF9F5" stroke-width="0.54"/><path d="M35.0 43.9q0.2 1.0 -1.6 1.9" stroke="#FFFFFF" stroke-width="0.54"/><path d="M31.9 36.8q0.8 1.3 -0.6 2.5" stroke="#F1EDE6" stroke-width="0.71"/><path d="M64.6 41.1q0.9 1.5 1.0 2.9" stroke="#FFFFFF" stroke-width="0.75"/><path d="M62.9 31.8q-0.1 1.2 0.5 2.4" stroke="#F1EDE6" stroke-width="0.51"/><path d="M37.5 34.0q-1.0 1.5 -0.5 3.1" stroke="#FBF9F5" stroke-width="0.74"/><path d="M37.7 35.7q-0.1 1.9 -0.6 3.7" stroke="#FBF9F5" stroke-width="0.63"/><path d="M39.4 38.7q-0.9 1.2 -1.7 2.5" stroke="#F1EDE6" stroke-width="0.66"/><path d="M45.4 33.2q0.8 1.1 -0.7 2.3" stroke="#FBF9F5" stroke-width="0.78"/><path d="M44.1 34.0q-1.2 1.3 -1.0 2.5" stroke="#FBF9F5" stroke-width="0.64"/><path d="M37.6 43.9q-0.4 1.6 -1.3 3.2" stroke="#F1EDE6" stroke-width="0.51"/><path d="M64.1 41.7q0.5 1.4 1.0 2.7" stroke="#F1EDE6" stroke-width="0.82"/><path d="M42.1 38.9q-1.1 1.1 -1.1 2.1" stroke="#FFFFFF" stroke-width="0.43"/><path d="M43.2 32.1q0.6 1.8 -0.6 3.7" stroke="#F1EDE6" stroke-width="0.69"/><path d="M68.2 40.0q-0.3 1.3 0.9 2.6" stroke="#FFFFFF" stroke-width="0.82"/><path d="M57.3 35.1q1.1 1.3 0.5 2.6" stroke="#F1EDE6" stroke-width="0.51"/><path d="M35.5 42.8q0.3 1.1 -1.8 2.3" stroke="#FFFFFF" stroke-width="0.53"/><path d="M50.7 30.9q-0.7 1.6 0.4 3.1" stroke="#FBF9F5" stroke-width="0.74"/><path d="M68.3 40.8q0.9 1.3 1.3 2.6" stroke="#FFFFFF" stroke-width="0.62"/><path d="M44.4 34.5q-0.3 1.4 -0.6 2.9" stroke="#FFFFFF" stroke-width="0.80"/><path d="M65.2 39.9q-0.2 1.0 1.8 2.0" stroke="#FFFFFF" stroke-width="0.45"/><path d="M55.1 34.6q1.2 1.7 0.9 3.4" stroke="#FBF9F5" stroke-width="0.77"/><path d="M55.8 34.1q0.1 1.9 0.3 3.7" stroke="#F1EDE6" stroke-width="0.57"/><path d="M41.2 32.4q0.5 1.3 -1.0 2.7" stroke="#FBF9F5" stroke-width="0.79"/><path d="M40.1 36.1q0.3 1.1 -1.1 2.2" stroke="#FBF9F5" stroke-width="0.76"/></g><g class="cheeks" filter="url(#mSoft)"><ellipse cx="37.5" cy="53" rx="4" ry="2.6" fill="#F09A9A" opacity=".55"/><ellipse cx="62.5" cy="53" rx="4" ry="2.6" fill="#F09A9A" opacity=".55"/></g><g class="eyes"><circle cx="41" cy="47" r="2.6"/><circle cx="59" cy="47" r="2.6"/><circle cx="41.8" cy="46.1" r=".8" fill="#fff"/><circle cx="59.8" cy="46.1" r=".8" fill="#fff"/></g><path class="shut" d="M38.5 47.5q2.5 1.8 5 0M56.5 47.5q2.5 1.8 5 0"/><path class="mouth" d="M47.6 52.6q2.4 2 4.8 0"/></svg>'  # original drawing of the Muse character (inline, no external assets)
CONN_CHIP = '<span class="chip" id="conn"><span class="spin"></span>Connecting</span>'

MAIN_BODY = r"""<body>
<header><div class="hwrap">
 <div class="logo" id="logo" title="Galatiqon">@MASCOT@</div>
 <div class="htxt"><h1>Bike Gadget</h1><div id="sub">Connecting to your Pi…</div></div>
 @CONN@
</div></header>
<main class="stack">
<section class="card hero" id="pwr" aria-live="polite">
 <div class="badge" id="pic"></div>
 <div><p class="htitle" id="ptitle">Checking power…</p><p class="hdesc" id="pdesc">Reading the power sensor.</p></div>
 <p class="tip" id="ptip" hidden></p>
</section>
<div class="tiles" id="vitals"></div>
<section class="card">
 <div class="ctitle" id="mtitle">Grok Bot<span class="r" id="mchip"></span></div>
 <p class="mdesc" id="mdesc" hidden></p>
 <div class="rows" id="msvc"></div>
</section>
<div class="tiles two">
 <div class="card tile"><div class="tl" id="wtl">Wi-Fi</div><div class="ts" id="wst">–</div><div class="tsub" id="wsub">&nbsp;</div></div>
 <div class="card tile"><div class="tl" id="btl">Bluetooth</div><div class="ts" id="bst">–</div><div class="tsub" id="bsub">&nbsp;</div></div>
</div>
<a class="card nav" href="/details"><div class="t"><b>Details</b><span>Power flags, network, services, processes, device</span></div><span id="chev"></span></a>
</main>
<footer id="foot">Waiting for data…</footer>
"""

DETAILS_BODY = r"""<body class="wide">
<header><div class="hwrap">
 <a class="back" href="/" aria-label="Back to overview" id="back"></a>
 <div class="htxt"><h1>Details</h1><div id="sub">Connecting to your Pi…</div></div>
 @CONN@
</div></header>
<main>
<h2 class="sec">Power</h2>
<div class="grid2">
 <div class="card"><div class="ctitle" id="t_flags">Throttle flags<span class="r num muted" id="raw"></span></div>
  <div class="flags" id="flags"></div><div class="kv" id="pkv"></div></div>
 <div class="card"><div class="ctitle" id="t_events">Power events<span class="r" id="echip"></span></div>
  <ul class="list tl" id="events"></ul></div>
</div>
<h2 class="sec">Performance · last 5 min</h2>
<div class="grid" id="charts"></div>
<h2 class="sec">Network</h2>
<div class="grid2">
 <div class="card"><div class="ctitle" id="t_wifi">Wi-Fi<span class="r" id="wchip"></span></div><div class="big2" id="wssid">–</div><div class="kv" id="wkv"></div></div>
 <div class="card"><div class="ctitle" id="t_bt">Bluetooth<span class="r" id="bchip"></span></div><div class="big2" id="bname">–</div><div class="kv" id="bkv"></div></div>
</div>
<h2 class="sec">Grok Bot</h2>
<div class="grid2">
 <div class="card"><div class="ctitle" id="t_svc">Services</div><ul class="list" id="svcs"></ul></div>
 <div class="card"><div class="ctitle" id="t_log">Recent Grok Bot log<span class="r muted" id="mlast"></span></div><ul class="list tl" id="mlog"></ul></div>
</div>
<h2 class="sec">System</h2>
<div class="grid2">
 <div class="card"><div class="ctitle" id="t_procs">Top processes<span class="r muted num" id="pcount"></span></div><ul class="list" id="procs"></ul></div>
 <div class="card"><div class="ctitle" id="t_store">Storage &amp; memory</div><div class="bars" id="store"></div></div>
 <div class="card"><div class="ctitle" id="t_audio">Audio<span class="r" id="achip"></span></div><ul class="list" id="audio"></ul></div>
 <div class="card"><div class="ctitle" id="t_dev">Device</div><div class="big2" id="dmodel">–</div><div class="kv" id="dkv"></div></div>
</div>
</main>
<footer><span id="foot">Waiting for data…</span> · <a href="/api/stats">JSON</a></footer>
"""

CORE_JS = r"""
"use strict";
const $=id=>document.getElementById(id);
const N=300;let hist=[],last=null,lastT=0;
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmtB=b=>b==null?"–":b>=1e9?(b/1e9).toFixed(1)+" GB":b>=1e6?(b/1e6).toFixed(0)+" MB":(b/1e3).toFixed(0)+" KB";
const fmtR=b=>b==null?"–":b>=1e6?(b/1e6).toFixed(1)+" MB/s":b>=1e3?(b/1e3).toFixed(b>=1e4?0:1)+" KB/s":Math.round(b)+" B/s";
const tm=t=>new Date(t*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
function ago(t){if(!t)return"–";const s=Math.max(0,Date.now()/1000-t);return s<60?Math.floor(s)+"s ago":s<3600?Math.floor(s/60)+" min ago":s<86400?Math.floor(s/3600)+" h ago":Math.floor(s/86400)+" d ago"}
function dur(s){s=Math.floor(s);const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?d+"d "+h+"h":h?h+"h "+m+"m":m+"m "+(s%60)+"s"}
function when(t){if(!t)return"–";const d=new Date(t*1000),n=new Date();return d.toDateString()===n.toDateString()?tm(t):d.toLocaleDateString([],{month:"short",day:"numeric"})+" "+tm(t)}
const chip=(cls,txt,dot)=>`<span class="chip sm ${cls||""}">${dot?'<span class="dot"></span>':""}${esc(txt)}</span>`;
const IC={temp:'<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>',
 cpu:'<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
 clock:'<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',bolt:'<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
 mem:'<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10v4M11 10v4M15 10v4"/>',net:'<path d="M7 17V3M3 7l4-4 4 4M17 7v14M21 17l-4 4-4-4"/>',
 check:'<path d="M20 6 9 17l-5-5"/>',alert:'<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01"/>',
 help:'<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
 wifi:'<path d="M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01"/>',
 bt:'<path d="m6.5 6.5 11 11L12 23V1l5.5 5.5-11 11"/>',
 chat:'<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/>',
 list:'<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
 disk:'<path d="M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11zM6 16h.01M10 16h.01"/>',
 spk:'<path d="M11 5 6 9H2v6h4l5 4V5zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
 board:'<rect x="2" y="4" width="20" height="16" rx="3"/><path d="M6 8h4v4H6zM14 8h4M14 12h4M6 16h12"/>',
 flag:'<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7"/>',
 gear:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
 right:'<path d="m9 18 6-6-6-6"/>',left:'<path d="m15 18-6-6 6-6"/>'};
const ICON=k=>`<svg class="ic" viewBox="0 0 24 24">${IC[k]}</svg>`;
function withIcon(id,k){const el=$(id);if(el)el.insertAdjacentHTML("afterbegin",ICON(k))}
const sigWord=dbm=>dbm==null?"":dbm>=-55?"Excellent":dbm>=-67?"Good":dbm>=-75?"Fair":"Weak";
const sigCls=dbm=>dbm>=-67?"ok":dbm>=-75?"warn":"bad";
function shortModel(d){return d&&d.model?d.model.replace(/^Raspberry Pi /,"Pi ").replace(/ Model /," ").replace(/ Plus/,"+").replace(/ Rev [\d.]+$/,""):null}
function push(s){const th=s.throttled||{},m=s.mem,n=s.net||{};
 hist.push({t:s.t,temp_c:s.temp_c,cpu_pct:s.cpu_pct,arm_mhz:s.arm_mhz,core_volts:s.core_volts,uv:!!(th.now&&th.now.under_voltage),
  mem_pct:m&&m.total?Math.round(1000*m.used/m.total)/10:null,rx:n.rx_bps,tx:n.tx_bps});
 if(hist.length>N)hist.splice(0,hist.length-N)}
/* sparkline into box (.spark with an <svg>); o: {k2,rng,span,lim,uv} */
function spark(box,k,o){
 const svg=box.querySelector("svg"),H=Math.max(20,box.clientHeight||52),em=box.querySelector(".empty");
 const pts=hist.filter(p=>p[k]!=null);
 if(em)em.style.display=pts.length<2?"grid":"none";
 if(pts.length<2){svg.innerHTML="";box._sc=null;return}
 const keys=o.k2?[k,o.k2]:[k],vals=[];pts.forEach(p=>keys.forEach(q=>{if(p[q]!=null)vals.push(p[q])}));
 let lo=Math.min(...vals),hi=Math.max(...vals);
 if(o.rng){lo=Math.min(lo,o.rng[0]);hi=Math.max(hi,o.rng[1])}
 if(o.span&&hi-lo<o.span){const c=(hi+lo)/2;lo=c-o.span/2;hi=c+o.span/2}
 if(hi-lo<1e-6){hi+=.5;lo-=.5}
 const t1=hist[hist.length-1].t,span=Math.max(30,Math.min(N,t1-hist[0].t)),t0=t1-span;
 const x=t=>(t-t0)/span*300,y=v=>H-2-(v-lo)/(hi-lo)*(H-4);
 box._sc={t0,span,x,y,H};
 let out="";
 if(o.uv)hist.forEach(p=>{if(p.uv&&p.t>=t0)out+=`<rect class="uv" x="${(x(p.t)-.5).toFixed(1)}" y="0" width="1.6" height="${H}"/>`});
 if(o.lim&&o.lim<hi){const ly=y(o.lim).toFixed(1);out+=`<line class="lim" x1="0" x2="300" y1="${ly}" y2="${ly}"/>`}
 const line=q=>pts.filter(p=>p[q]!=null).map((p,i)=>(i?"L":"M")+x(p.t).toFixed(1)+","+y(p[q]).toFixed(1)).join("");
 const l1=line(k);
 out+=`<path class="ar" d="${l1}L${x(pts[pts.length-1].t).toFixed(1)},${H}L${x(pts[0].t).toFixed(1)},${H}Z"/><path class="ln" d="${l1}"/>`;
 if(o.k2)out+=`<path class="ln2" d="${line(o.k2)}"/>`;
 svg.setAttribute("viewBox","0 0 300 "+H);svg.setAttribute("preserveAspectRatio","none");svg.innerHTML=out;
}
/* swap text/html with a short pop-in, only when it actually changes */
function swap(el,v,html,cls){if(!el)return;
 if(cls!=null&&el.dataset.c!==cls){el.dataset.c=cls;el.className=cls}
 if(el._v===v)return;const first=el._v===undefined;el._v=v;  // compare with what we set, not re-serialised DOM
 if(html)el.innerHTML=v;else el.textContent=v;
 if(!first){el.classList.remove("pop");void el.offsetWidth;el.classList.add("pop");
  el.addEventListener("animationend",()=>el.classList.remove("pop"),{once:true})}}
function headerSub(s,model){const d=s.device||{};
 $("sub").textContent=[s.hostname,model?shortModel(d):null,s.uptime_s!=null?"up "+dur(s.uptime_s):null].filter(Boolean).join(" · ")}
"""

BOOT_JS = r"""
let lastAt=0,es=null,poll=null,mode="";
function setConn(m){if(m===mode)return;mode=m;const c=$("conn");
 const S={live:["ok",'<span class="dot live"></span>Live'],reconnecting:["warn",'<span class="spin"></span>Reconnecting'],
  polling:["warn",'<span class="dot"></span>Polling'],stale:["warn",'<span class="dot"></span>Stale'],offline:["bad",'<span class="dot"></span>Offline']}[m];
 c.className="chip "+S[0];c.innerHTML=S[1];document.body.classList.toggle("offline",m==="offline")}
function ready(){if(document.body.classList.contains("ready"))return;document.querySelectorAll(".card").forEach((c,i)=>c.style.setProperty("--i",Math.min(i,10)));document.body.classList.add("ready")}
function onSnap(s){if(!s||!s.t||s.t===lastT)return;lastT=s.t;push(s);last=s;render(s);ready();charts();lastAt=Date.now();if(mode!=="polling")setConn("live")}
function startPoll(){if(poll)return;poll=setInterval(()=>fetch("/api/stats",{cache:"no-store"}).then(r=>r.json()).then(s=>{onSnap(s);setConn(es&&es.readyState===1?"live":"polling")}).catch(()=>setConn("offline")),2000)}
function startSSE(){
 if(!window.EventSource){startPoll();return}
 es=new EventSource("/events");
 es.onopen=()=>{clearInterval(poll);poll=null;setConn("live")};
 es.onmessage=e=>{try{onSnap(JSON.parse(e.data))}catch(_){}};
 es.onerror=()=>{setConn("reconnecting");startPoll()};
}
fetch("/api/history").then(r=>r.json()).then(h=>{if(h.length>hist.length)hist=h.slice(-N);charts();if(last)render(last)}).catch(()=>{});
startSSE();
setInterval(()=>{const age=Date.now()-lastAt;if(lastAt&&age>20000)setConn("offline");else if(lastAt&&age>5000&&mode==="live")setConn("stale")},2000);
addEventListener("resize",()=>charts(),{passive:true});
"""

MAIN_JS = r"""
withIcon("mtitle","chat");withIcon("wtl","wifi");withIcon("btl","bt");$("chev").innerHTML=ICON("right");
const V=[
 {k:"temp_c",t:"Temp",i:"temp",f:v=>[v.toFixed(0),"°C"],rng:[30,85],lvl:v=>v>=80?"bad":v>=70?"warn":""},
 {k:"cpu_pct",t:"CPU",i:"cpu",f:v=>[v.toFixed(0),"%"],rng:[0,100],lvl:v=>v>=90?"warn":""},
 {k:"mem_pct",t:"Memory",i:"mem",f:v=>[v.toFixed(0),"%"],rng:[0,100],lvl:v=>v>=92?"bad":v>=80?"warn":""},
];
$("vitals").innerHTML=V.map(m=>`<div class="card tile"><div class="tl">${ICON(m.i)}${m.t}</div><div class="tv num" id="v_${m.k}">–</div><div class="spark" id="g_${m.k}"><svg></svg></div></div>`).join("");
const SUPPLY="Use a 5 V 2.5 A supply and a short, thick USB cable.";
const RECENT=600;  // a since-boot flag only warns if it was seen in the last 10 min
function power(s){
 const th=s.throttled,u=s.uv_log||{},now=Date.now()/1000;let c,i,t,d,tip="";
 const recentOn=f=>(s.transitions||[]).some(x=>x.on&&x.flag===f&&now-x.t<RECENT);
 const uvRecent=(u.last_t&&now-u.last_t<RECENT)||recentOn("under_voltage");
 if(!th){c="";i="help";t="Power status unknown";d="Can't read the power sensor."}
 else{const n=th.now;
  if(n.under_voltage){c="bad";i="alert";t="Power is too low";d="The supply is dipping right now, so the Pi slows down and may crash.";tip=SUPPLY}
  else if(n.throttled||n.freq_capped){c="bad";i="alert";t=n.soft_temp_limit?"Slowing down to cool off":"CPU is being throttled";d="The Pi is running slower than normal right now.";tip="Give it airflow and keep it out of direct sun."}
  else if(uvRecent){c="warn";i="alert";t="Power dipped a moment ago";d="Fine now. If it keeps happening, use a stronger supply."}
  else if(recentOn("throttled")||recentOn("freq_capped")){c="warn";i="alert";t="Slowed down a moment ago";d="Fine now, usually from heat."}
  else{c="ok";i="check";t="Power is healthy";d="Running normally."}}
 $("pwr").classList.remove("ok","warn","bad");if(c)$("pwr").classList.add(c);swap($("pic"),ICON(i),1);swap($("ptitle"),t);swap($("pdesc"),d);
 const tp=$("ptip");tp.hidden=!tip;tp.textContent=tip;
}
function vitals(s){V.forEach(m=>{const v=m.k==="mem_pct"?(s.mem&&s.mem.total?100*s.mem.used/s.mem.total:null):s[m.k],el=$("v_"+m.k);
 if(v==null){el.textContent="–";el.className="tv num";return}
 const[a,u]=m.f(v);el.innerHTML=esc(a)+`<small>${esc(u)}</small>`;el.className="tv num "+m.lvl(v)})}
function svcRow(label,v){let c="",t="Not installed";
 if(v&&v.installed)[c,t]=v.active==="active"?["ok","Running"]:v.active==="failed"?["bad","Failed"]:v.active==="activating"?["warn","Starting"]:["","Stopped"];
 return`<div><span>${label}</span><span class="st ${c}"><span class="dot"></span>${t}</span></div>`}
function muse(s){
 const sv=s.services||[],by=u=>sv.find(x=>x.unit===u),g=by("galatiqon-gbd"),m=s.muse||{};let c="",t="–",d="";
 if(sv.length){
  if(!g||!g.installed){t="Not installed"}
  else if(g.active==="failed"){c="bad";t="Error";d="The gadget service crashed. See Details for the log."}
  else if(g.active==="activating"){c="warn";t="Starting"}
  else if(g.active!=="active"){t="Paused";d="The gadget service is stopped, so the glasses can't connect."}
  else{const st={connected:["ok","Connected"],paired:["ok","Paired"],connecting:["warn","Connecting"],starting:["warn","Starting"],unpaired:["warn","Not paired"]}[m.state];
   [c,t]=st||["info","Running"];if(m.state==="unpaired")d="Waiting to be paired with the glasses.";else if(m.state==="connecting")d="Trying to reach the glasses.";}}
 swap($("mchip"),chip(c,t,1),1);
 const lg=$("logo"),on=!!g&&g.active==="active";lg.classList.toggle("sleep",!!sv.length&&!on);lg.classList.toggle("work",on&&m.state==="connected");const md=$("mdesc");md.hidden=!d;md.textContent=d;
 $("msvc").innerHTML=svcRow("Speech output",by("galatiqon-output"))+svcRow("Push-to-talk",by("galatiqon-ptt"));
}
function links(s){
 const w=s.wifi,i=s.wifi_info||{},ws=$("wst");
 if(w)swap(ws,sigWord(w.signal_dbm),0,"ts "+sigCls(w.signal_dbm)+"-t");else swap(ws,"Offline",0,"ts bad-t");
 $("wsub").textContent=i.ssid||s.ssid||"Not connected";
 const b=s.bluetooth||{},a=b.adapter,rf=b.rfkill||{},bs=$("bst"),dev=(b.devices||[]).filter(x=>x.connected);
 let c,t;if(!b.present){c="";t="No adapter"}else if(rf.hard_blocked||rf.soft_blocked){c="bad";t="Blocked"}
 else if(a?a.powered:true){c="ok";t="On"}else{c="";t="Off"}
 swap(bs,t,0,"ts "+(c?c+"-t":""));
 $("bsub").textContent=!b.present?"–":dev.length?dev.map(x=>x.name).join(", "):"Nothing connected";
}
function render(s){headerSub(s,false);power(s);vitals(s);muse(s);links(s);$("foot").textContent="Updated "+tm(s.t)}
function charts(){V.forEach(m=>spark($("g_"+m.k),m.k,{rng:m.rng}))}
"""

DETAILS_JS = r"""
$("back").innerHTML=ICON("left");
[["t_flags","flag"],["t_events","bolt"],["t_wifi","wifi"],["t_bt","bt"],["t_svc","gear"],["t_log","chat"],["t_procs","list"],["t_store","disk"],["t_audio","spk"],["t_dev","board"]].forEach(a=>withIcon(...a));
const LABELS={under_voltage:"Under-voltage",freq_capped:"Frequency capped",throttled:"Throttled",soft_temp_limit:"Soft temp limit"};
const kv=rows=>rows.filter(r=>r&&r[1]!=null&&r[1]!=="").map(r=>`<div>${esc(r[0])}</div><div>${r[2]?r[1]:esc(r[1])}</div>`).join("");
const C=[
 {k:"temp_c",t:"Temperature",i:"temp",f:v=>[v.toFixed(1),"°C"],rng:[30,85],lim:80,sub:s=>s.temp_c==null?"":s.temp_c<80?(80-s.temp_c).toFixed(0)+"° below throttle":"At the throttle point"},
 {k:"cpu_pct",t:"CPU",i:"cpu",f:v=>[v.toFixed(0),"%"],rng:[0,100],cores:1,sub:s=>s.load?"Load "+s.load.join(" · "):""},
 {k:"arm_mhz",t:"ARM clock",i:"clock",f:v=>[Math.round(v),"MHz"],rng:[600,1400],sub:s=>{const d=s.device||{};return[s.governor,d.min_mhz&&d.max_mhz?d.min_mhz+"–"+d.max_mhz+" MHz":null].filter(Boolean).join(" · ")}},
 {k:"core_volts",t:"Core voltage",i:"bolt",f:v=>[v.toFixed(3),"V"],span:.05,sub:()=>"SoC core rail"},
 {k:"mem_pct",t:"Memory",i:"mem",f:v=>[v.toFixed(0),"%"],rng:[0,100],sub:s=>s.mem?fmtB(s.mem.used)+" of "+fmtB(s.mem.total):""},
 {k:"rx",k2:"tx",t:"Network",i:"net",f:v=>[fmtR(v),""],rng:[0,2048],net:1,sub:s=>s.net?"↑ "+fmtR(s.net.tx_bps):"No network"},
];
$("charts").innerHTML=C.map(m=>`<div class="card metric" id="m_${m.k}"><div class="ctitle">${ICON(m.i)}${m.t}</div>
 <div class="val num" id="v_${m.k}">–</div><div class="sub num" id="s_${m.k}"></div>
 ${m.cores?'<div class="cores" id="cores"></div>':""}${m.net?'<div class="legend"><span><i style="background:var(--accent)"></i>down</span><span><i style="background:var(--accent2)"></i>up</span></div>':""}
 <div class="spark" id="g_${m.k}"><svg></svg><div class="cur"></div><div class="pt"></div><div class="empty">Collecting…</div></div></div>`).join("");
const hov={};
function setVal(m,v,sub){const el=$("v_"+m.k);
 if(v==null)el.textContent="–";else{const[a,u]=m.f(v);el.innerHTML=esc(a)+(u?`<small>${esc(u)}</small>`:"")}
 $("s_"+m.k).textContent=sub||""}
function liveVal(m,s){setVal(m,m.net?(s.net?s.net.rx_bps:null):m.k==="mem_pct"?(s.mem&&s.mem.total?100*s.mem.used/s.mem.total:null):s[m.k],m.sub(s))}
function showHover(m,frac){
 const box=$("g_"+m.k),sc=box._sc;if(!sc)return;
 const tt=sc.t0+frac*sc.span;let best=null,bd=1e9;
 for(const p of hist){if(p[m.k]==null)continue;const d=Math.abs(p.t-tt);if(d<bd){bd=d;best=p}}
 if(!best)return;
 const xp=sc.x(best.t)/300*100,yp=sc.y(best[m.k])/sc.H*100;
 box.querySelector(".cur").style.left=xp+"%";const pt=box.querySelector(".pt");pt.style.left=xp+"%";pt.style.top=yp+"%";
 box.classList.add("on");$("m_"+m.k).classList.add("hov");
 setVal(m,best[m.k],(m.net?"↑ "+fmtR(best.tx)+" · ":best.uv?"under-voltage · ":"")+tm(best.t));
}
function clearHover(m){delete hov[m.k];$("g_"+m.k).classList.remove("on");$("m_"+m.k).classList.remove("hov");if(last)liveVal(m,last)}
C.forEach(m=>{const box=$("g_"+m.k);
 const mv=e=>{const r=box.getBoundingClientRect();hov[m.k]=Math.min(1,Math.max(0,(e.clientX-r.left)/r.width));showHover(m,hov[m.k])};
 box.addEventListener("pointermove",mv);box.addEventListener("pointerdown",mv);
 box.addEventListener("pointerleave",()=>clearHover(m));box.addEventListener("pointercancel",()=>clearHover(m));
 box.addEventListener("pointerup",e=>{if(e.pointerType!=="mouse")setTimeout(()=>clearHover(m),1500)});
});
function charts(){C.forEach(m=>{spark($("g_"+m.k),m.k,{k2:m.k2,rng:m.rng,span:m.span,lim:m.lim,uv:1});if(hov[m.k]!=null)showHover(m,hov[m.k])})}

function power(s){
 const th=s.throttled,u=s.uv_log||{};
 $("raw").textContent=th?"get_throttled "+th.raw:"";
 $("flags").innerHTML=th?'<div class="h">Flag</div><div class="h c">Now</div><div class="h c">Since boot</div>'+
  Object.keys(LABELS).map(k=>`<div>${LABELS[k]}</div><div class="c">${th.now[k]?chip("bad","Active"):chip("ok","Clear")}</div><div class="c">${th.since_boot[k]?chip("warn","Happened"):chip("","Never")}</div>`).join("")
  :'<div class="muted" style="grid-column:1/-1">Can\'t read vcgencmd (dashboard user needs the video group).</div>';
 $("pkv").innerHTML=kv([["Core voltage",s.core_volts!=null?s.core_volts.toFixed(3)+" V":null],
  ["hwmon alarm",s.undervolt_alarm!=null?(s.undervolt_alarm?"On":"Off"):null],
  ["Under-voltage this boot",String(u.count||0)],["Last under-voltage",u.last_t?when(u.last_t):null]]);
 const ev=[];
 (s.transitions||[]).forEach(x=>ev.push({t:x.t,c:x.on?(x.flag==="under_voltage"?"bad":"warn"):"ok",m:(LABELS[x.flag]||x.flag)+(x.on?" started":" cleared")+" (seen live)"}));
 (u.events||[]).forEach(e=>ev.push({t:e.t,c:e.uv?"bad":"ok",m:e.text.replace(/^hwmon hwmon\d+: /,"")}));
 ev.sort((a,b)=>(b.t||0)-(a.t||0));
 $("echip").innerHTML=u.count?chip("bad",u.count+" under-voltage"):chip("ok","None this boot");
 $("events").innerHTML=u.error&&!ev.length?`<li class="muted">${esc(u.error)}</li>`:ev.length?ev.slice(0,10).map(e=>`<li><span class="ldot ${e.c}"></span><span class="msg">${esc(e.m)}</span><span class="when">${esc(e.t?when(e.t):"")}</span></li>`).join("")
  :`<li class="muted">No under-voltage events in the kernel log this boot.</li>`;
}
function cores(s){const c=$("cores");if(!c||!s.cores)return;if(c.children.length!==s.cores.length)c.innerHTML=s.cores.map(()=>"<i><b></b></i>").join("");
 s.cores.forEach((v,i)=>{c.children[i].firstChild.style.height=Math.max(6,v)+"%";c.children[i].title="core "+i+": "+v.toFixed(0)+"%"})}
function wifi(s){
 const w=s.wifi,i=s.wifi_info||{};
 $("wssid").textContent=i.ssid||s.ssid||"Not connected";
 $("wchip").innerHTML=w?chip(sigCls(w.signal_dbm),sigWord(w.signal_dbm),1):chip("bad","Offline",1);
 $("wkv").innerHTML=kv([["Signal",w?w.signal_dbm+" dBm · "+w.quality_pct+"%":null],["Band",i.band?i.band+(i.channel?" · ch "+i.channel:""):null],
  ["Link rate",i.rate],["IP address",s.ip],["Security",i.security],["MAC",i.mac],
  ["Traffic",s.net?"↓ "+fmtB(s.net.rx_total)+" · ↑ "+fmtB(s.net.tx_total):null]]);
}
function bt(s){
 const b=s.bluetooth||{},a=b.adapter,rf=b.rfkill||{};
 if(!b.present){$("bname").textContent="No adapter";$("bchip").innerHTML=chip("","Unavailable");$("bkv").innerHTML="";return}
 const on=a?a.powered:!(rf.soft_blocked||rf.hard_blocked),dev=b.devices||[],conn=dev.filter(d=>d.connected);
 $("bname").textContent=a?(a.alias||a.name||"Adapter"):"Adapter";
 $("bchip").innerHTML=rf.hard_blocked||rf.soft_blocked?chip("bad","Blocked",1):on?chip("ok","On",1):chip("","Off",1);
 const yn=v=>v==null?null:v?"Yes":"No";
 $("bkv").innerHTML=kv([["Address",a&&a.address],["Discoverable",a&&yn(a.discoverable)],["Pairable",a&&yn(a.pairable)],
  ["Paired devices",a?String(dev.filter(d=>d.paired).length):null],["Connected",a?(conn.length?conn.map(d=>d.name).join(", "):"None"):null],["Status",b.error]]);
}
const SVC={"galatiqon-gbd":"Grok Bot daemon","galatiqon-output":"Speech output","galatiqon-ptt":"Push-to-talk","galatiqon-dashboard":"Dashboard"};
function svcChip(v){if(!v.installed)return chip("","Not installed");
 return v.active==="active"?chip("ok","Running",1):v.active==="failed"?chip("bad","Failed",1):v.active==="activating"?chip("warn","Starting",1):chip("","Stopped",1)}
function services(s){
 const sv=s.services||[],m=s.muse||{};
 $("svcs").innerHTML=sv.length?sv.map(v=>`<li><span class="nm">${esc(SVC[v.unit]||v.unit)}<small>${esc(v.unit)}${v.since?" · up "+esc(ago(v.since).replace(" ago","")):""}</small></span>${svcChip(v)}</li>`).join(""):`<li class="muted">Reading…</li>`;
 $("mlast").textContent=m.state_t?m.label+" · "+ago(m.state_t):"";
 const ev=(m.events||[]).slice(-6).reverse();
 $("mlog").innerHTML=m.error?`<li class="muted">${esc(m.error)}</li>`:ev.length?ev.map(e=>{
  const c=/ERROR|CRITICAL/.test(e.level)?"bad":e.level==="WARNING"?"warn":/registered|established/i.test(e.msg)?"ok":e.sys?"":"info";
  return`<li><span class="ldot ${c}"></span><span class="msg">${esc(e.msg)}${e.n>1?` <span class="muted">×${e.n}</span>`:""}</span><span class="when">${esc(ago(e.t))}</span></li>`}).join(""):`<li class="muted">No log lines yet</li>`;
}
function procs(s){
 const p=s.procs||[];$("pcount").textContent=s.nprocs?s.nprocs+" running":"";
 $("procs").innerHTML=p.length?p.map(x=>`<li><span class="nm">${esc(x.name)}<small>${esc(x.user||"")} · pid ${x.pid}</small></span>
  <span class="mini"><b style="width:${Math.min(100,x.cpu)}%"></b></span><span class="rt num" style="width:46px">${x.cpu.toFixed(1)}%</span><span class="rt num muted" style="width:54px">${fmtB(x.rss)}</span></li>`).join("")
  :`<li class="muted">Measuring…</li>`;
}
function audio(s){
 const a=s.audio||{},c=a.cards||[];
 $("achip").innerHTML=c.some(x=>x.state==="playing")?chip("info","Playing",1):a.headphones?chip("ok","Jack ready",1):c.length?chip("","Idle"):chip("warn","No devices");
 $("audio").innerHTML=c.length?c.map(x=>`<li><span class="nm">${esc(x.name)}<small>card ${x.index} · ${esc(x.id)}${x.extra?" · "+esc(x.extra):""}</small></span>${x.playback?(x.state==="playing"?chip("info","Playing"):chip("","Idle")):chip("","Capture")}</li>`).join("")
  :`<li class="muted">No ALSA cards found</li>`;
}
function bar(label,used,total){const p=total?100*used/total:0,c=p>90?"bad":p>75?"warn":"";
 return`<div><div class="l"><span>${label}</span><span class="num muted">${fmtB(used)} / ${fmtB(total)} · ${p.toFixed(0)}%</span></div><div class="bar"><b class="${c}" style="width:${p.toFixed(1)}%"></b></div></div>`}
function store(s){let h="";if(s.disk)h+=bar("SD card",s.disk.used,s.disk.total);if(s.mem)h+=bar("Memory",s.mem.used,s.mem.total);
 if(s.mem&&s.mem.swap_total)h+=bar("Swap",s.mem.swap_used,s.mem.swap_total);$("store").innerHTML=h||'<span class="muted">–</span>'}
function device(s){
 const d=s.device||{},b=d.board||{};
 $("dmodel").textContent=d.model||"Raspberry Pi";
 $("dkv").innerHTML=kv([["Hostname",d.hostname||s.hostname],["OS",d.os],["Kernel",d.kernel&&d.kernel+(d.arch?" ("+d.arch+")":"")],
  ["Board",b.soc?[b.soc,b.memory,"PCB "+b.pcb,b.maker].filter(Boolean).join(" · "):null],["Revision",d.revision],
  ["Serial",d.serial?"…"+d.serial.slice(-8):null],["CPU",d.ncpu?d.ncpu+" cores"+(d.max_mhz?" · up to "+d.max_mhz+" MHz":""):null],
  ["Firmware",d.firmware],["Python",d.python],["Booted",s.boot_t?when(s.boot_t):null],["Uptime",s.uptime_s!=null?dur(s.uptime_s):null]]);
}
function render(s){headerSub(s,true);C.forEach(m=>{if(hov[m.k]==null)liveVal(m,s)});cores(s);
 power(s);wifi(s);bt(s);services(s);procs(s);audio(s);store(s);device(s);$("foot").textContent="Updated "+tm(s.t)}
"""


def _page(title: str, css: str, body: str, js: str) -> bytes:
    head = HEAD.replace("@TITLE@", title).replace("@@PAGECSS@@", css)
    body = body.replace("@MASCOT@", MASCOT_SVG).replace("@CONN@", CONN_CHIP)
    return (head + body + "<script>" + CORE_JS + js + BOOT_JS + "</script></body></html>\n").encode()


MAIN_PAGE = _page("Bike Gadget", MAIN_CSS, MAIN_BODY, MAIN_JS)
DETAILS_PAGE = _page("Bike Gadget Details", DETAILS_CSS, DETAILS_BODY, DETAILS_JS)


def main() -> None:
    ap = argparse.ArgumentParser(description="Galatiqon Pi health dashboard")
    ap.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "8080")))
    args = ap.parse_args()
    SAMPLER.start()
    ThreadingHTTPServer.daemon_threads = True
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard on http://{args.host}:{args.port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
