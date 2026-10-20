from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from galatiqon import config, grokbot
from tests.fake_gbd import BOT, FakeGbd

TURN = [
    ("prompt", {"text": "hi", "ref": "x"}),
    ("activity", {"running": True}),
    ("message", {"text": "Galatiq builds Grok agents for companies.", "fromBot": True, "entryId": "e1"}),
    ("message", {"text": "Want the details?", "fromBot": True, "entryId": "e2"}),
    ("activity", {"running": False}),
    ("turn.done", {}),
]


class GbdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sock = os.path.join(self.tmp.name, "gbd.sock")
        self.fake = FakeGbd(self.sock).start()
        self.fake.script = list(TURN)
        self.client = grokbot.GbdClient(socket_path=self.sock)

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def test_health_and_agents(self):
        self.assertTrue(self.client.health()["ok"])
        self.assertEqual(self.client.agents()[0]["name"], BOT["name"])

    def test_ask_blocking(self):
        turn = self.client.ask(BOT["name"], "what does Galatiq do?", timeout_s=5)
        self.assertTrue(turn.done)
        self.assertEqual(turn.messages, ["Galatiq builds Grok agents for companies.", "Want the details?"])
        self.assertEqual(self.fake.sent[-1]["timeoutSec"], 5)

    def test_ask_streaming_delivers_messages_as_they_arrive(self):
        got, activity = [], []
        turn = self.client.ask_streaming(BOT["name"], "what does Galatiq do?", got.append, activity.append, timeout_s=5)
        self.assertTrue(turn.done)
        self.assertEqual(got, ["Galatiq builds Grok agents for companies.", "Want the details?"])
        self.assertEqual(activity, [True, False])
        self.assertEqual(self.fake.sent[-1]["text"], "what does Galatiq do?")
        self.assertTrue(self.fake.sent[-1]["ref"])

    def test_streaming_ignores_other_turns(self):
        self.fake.script = [("message", {"text": "old answer", "fromBot": True, "refs": ["someone-else"]}),
                            ("turn.done", {"refs": ["someone-else"]})] + list(TURN)
        got = []
        turn = self.client.ask_streaming(BOT["name"], "q", got.append, timeout_s=5)
        self.assertEqual(got, ["Galatiq builds Grok agents for companies.", "Want the details?"])
        self.assertTrue(turn.done)

    def test_streaming_falls_back_to_ask_when_events_unavailable(self):
        self.fake.events_status = 500
        got = []
        turn = self.client.ask_streaming(BOT["name"], "q", got.append, timeout_s=5)
        self.assertEqual(got, ["Galatiq builds Grok agents for companies.", "Want the details?"])
        self.assertTrue(turn.done)

    def test_streaming_timeout(self):
        self.fake.script = [("activity", {"running": True})]  # never finishes
        with self.assertRaises(grokbot.ReplyTimeout) as cm:
            self.client.ask_streaming(BOT["name"], "q", lambda m: None, timeout_s=1)
        self.assertIn("too long", cm.exception.spoken)

    def test_ask_timeout_504(self):
        self.fake.ask_status = 504
        with self.assertRaises(grokbot.ReplyTimeout):
            self.client.ask(BOT["name"], "q", timeout_s=2)

    def test_unknown_bot_is_spoken_nicely(self):
        self.fake.send_status = 404
        with self.assertRaises(grokbot.GrokBotError) as cm:
            self.client.ask_streaming("Nobody", "q", lambda m: None, timeout_s=2)
        self.assertIn("can't find your bot", cm.exception.spoken)

    def test_daemon_down(self):
        client = grokbot.GbdClient(socket_path=os.path.join(self.tmp.name, "missing.sock"))
        with self.assertRaises(grokbot.GrokBotError) as cm:
            client.health()
        self.assertEqual(cm.exception.spoken, "I couldn't reach your bot.")


class SseParserTests(unittest.TestCase):
    def test_parses_multiline_and_comments(self):
        import io

        class R(io.BytesIO):
            pass

        raw = b": hi\n\nid: 1\nevent: message\ndata: {\"a\": 1,\ndata:  \"b\": 2}\n\nevent: turn.done\ndata: {}\n\n"
        events = list(grokbot._sse(R(raw)))
        self.assertEqual(events, [("message", {"a": 1, "b": 2}), ("turn.done", {})])


class ConfigTests(unittest.TestCase):
    def test_defaults_and_bot_name(self):
        cfg = config.Config()
        self.assertEqual(cfg.bot, "Galatiqon")
        cfg.owner.name = "Scott"
        self.assertEqual(cfg.bot, "Galatiqon · Scott")
        cfg.grokbot.bot = "Custom"
        self.assertEqual(cfg.bot, "Custom")

    def test_load_example(self):
        example = Path(__file__).resolve().parent.parent / "config.example.toml"
        cfg = config.load(example)
        self.assertEqual(cfg.grokbot.transport, "gbd")
        self.assertEqual(cfg.tts.pronunciations["Galatiq"], "Galatick")
        self.assertEqual(cfg.button.mode, "gpio")

    def test_unknown_key_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("[grokbot]\nbogus = 1\n")
        with self.assertRaises(ValueError):
            config.load(Path(f.name))
        os.unlink(f.name)

    def test_socket_path_env(self):
        os.environ["GB_HOME"] = "/tmp/gbhome"
        os.environ["GB_PROFILE"] = "work"
        try:
            self.assertEqual(str(config.GrokBotConfig().socket_path()), "/tmp/gbhome/work/gbd.sock")
        finally:
            del os.environ["GB_HOME"], os.environ["GB_PROFILE"]


class GbCliTests(unittest.TestCase):
    def test_parses_json_output(self):
        import json
        import stat

        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "gb"
            out = json.dumps({"send": {}, "entries": [{"kind": "message", "text": "Hello there."},
                                                     {"kind": "tool-call", "text": "x"}], "reply": "Hello there.", "done": True})
            fake.write_text("#!/bin/sh\necho '→ waiting' >&2\necho '" + out + "'\n")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            turn = grokbot.GbCli(str(fake)).ask("Bot", "hi", timeout_s=5)
            self.assertEqual(turn.messages, ["Hello there."])
            got = []
            grokbot.GbCli(str(fake)).ask_streaming("Bot", "hi", got.append, timeout_s=5)
            self.assertEqual(got, ["Hello there."])

    def test_missing_binary(self):
        with self.assertRaises(grokbot.GrokBotError) as cm:
            grokbot.GbCli("/nonexistent/gb").ask("Bot", "hi", timeout_s=1)
        self.assertIn("isn't installed", cm.exception.spoken)


if __name__ == "__main__":
    unittest.main()


class WakeTests(unittest.TestCase):
    def test_asleep_box_is_woken_then_retried(self):
        import stat

        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            sock = os.path.join(d, "gbd.sock")
            fake = FakeGbd(sock).start()
            fake.script = list(TURN)
            fake.events_status = 404  # "box not ready" until woken
            fake.events_error = "box not ready (runState=SAND_BOX_RUN_STATE_HIBERNATED); try `gb box wake`"
            wake = Path(d) / "gb"
            marker = Path(d) / "woken"
            wake.write_text(f"#!/bin/sh\ntouch {marker}\n")
            wake.chmod(wake.stat().st_mode | stat.S_IEXEC)
            woke_said = []
            client = grokbot.GbdClient(socket_path=sock, gb_binary=str(wake), on_wake=lambda: woke_said.append(1))
            # the fake flips to healthy once the wake script has run
            orig = fake.server.RequestHandlerClass.do_GET

            def do_get(h):
                if marker.exists():
                    fake.events_status = 200
                return orig(h)

            fake.server.RequestHandlerClass.do_GET = do_get
            got = []
            try:
                turn = client.ask_streaming(BOT["name"], "q", got.append, timeout_s=5)
            finally:
                fake.stop()
            self.assertTrue(marker.exists())
            self.assertEqual(woke_said, [1])
            self.assertTrue(turn.done)
            self.assertEqual(got, ["Galatiq builds Grok agents for companies.", "Want the details?"])
