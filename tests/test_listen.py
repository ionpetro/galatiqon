from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest

from galatiqon import config, grokbot, listen
from tests.fake_gbd import BOT, FakeGbd


def typed_turn(text: str, entry: str = "e1", request: str = "req-typed") -> list[tuple[str, dict]]:
    """What gbd emits when the owner types to the bot in the app. (Stale refs from earlier
    /v1/send calls can show up on such a reply; they must not mute it.)"""
    return [
        ("prompt", {"text": "what's up?", "author": "you", "entryId": "u1", "entry": {"requestId": request}}),
        ("message", {"text": text, "fromBot": True, "entryId": entry, "author": BOT["name"],
                     "refs": ["stale-ref"], "entry": {"requestId": request}}),
        ("turn.done", {}),
    ]


def device_turn(text: str, entry: str = "d1", request: str = "req-device") -> list[tuple[str, dict]]:
    """A turn galatiqon-ptt started: its prompt carries the device prefix."""
    return [
        ("prompt", {"text": config.DEFAULT_PROMPT + "\n\nhello", "author": "you", "entryId": "u2",
                    "entry": {"requestId": request}}),
        ("message", {"text": text, "fromBot": True, "entryId": entry, "refs": ["ptt-ref"],
                     "entry": {"requestId": request}}),
        ("turn.done", {"refs": ["ptt-ref"]}),
    ]


class ListenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sock = os.path.join(self.tmp.name, "gbd.sock")
        self.fake = FakeGbd(self.sock).start()
        self.cfg = config.Config()
        self.cfg.grokbot.bot = BOT["name"]
        self.spoken: list[str] = []
        self.shown: list[str] = []
        self.listener = listen.Listener(self.cfg, grokbot.GbdClient(socket_path=self.sock),
                                        self.spoken.append, self.shown.append)
        self.thread = threading.Thread(target=self.listener.run, daemon=True)

    def tearDown(self):
        self.listener.stop()
        if self.thread.is_alive():
            self.thread.join(timeout=5)
        self.fake.stop()
        self.tmp.cleanup()

    def start(self):
        self.thread.start()
        self.wait(lambda: self.fake.event_queries)

    def wait(self, cond, timeout=5.0):
        deadline = time.monotonic() + timeout
        while not cond() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(cond(), "timed out waiting")

    def test_typed_message_is_spoken_and_prompt_shown(self):
        self.start()
        self.fake.push(typed_turn("Nothing much, you?"))
        self.wait(lambda: self.spoken)
        self.assertEqual(self.spoken, ["Nothing much, you?"])
        self.assertEqual(self.shown, ["what's up?"])
        q = self.fake.event_queries[0]
        self.assertEqual(q["bots"], BOT["name"])
        self.assertEqual(q["types"], "prompt,message,turn.done")
        self.assertNotIn("since", q)

    def test_device_turns_are_skipped_by_default(self):
        self.start()
        self.fake.push(device_turn("spoken by ptt already"))
        self.fake.push(typed_turn("but this one is mine", entry="e9"))
        self.wait(lambda: self.spoken)
        time.sleep(0.1)
        self.assertEqual(self.spoken, ["but this one is mine"])
        self.assertEqual(self.shown, ["what's up?"])  # the device prompt is not shown either

    def test_device_turns_spoken_when_asked(self):
        self.cfg.listen.speak_device_turns = True
        self.start()
        self.fake.push(device_turn("now I say it"))
        self.wait(lambda: self.spoken)
        self.assertEqual(self.spoken, ["now I say it"])

    def test_replayed_entries_are_not_spoken_twice(self):
        self.start()
        self.fake.push(typed_turn("once", entry="same"))
        self.fake.push(typed_turn("once", entry="same"))
        self.fake.push(typed_turn("twice", entry="other"))
        self.wait(lambda: len(self.spoken) >= 2)
        time.sleep(0.1)
        self.assertEqual(self.spoken, ["once", "twice"])

    def test_reply_without_a_seen_prompt_is_spoken(self):
        """Started mid-turn, or the prompt event was lost: better to speak once too often than never."""
        h = self.listener.handle
        self.assertEqual(h("message", {"id": 3, "text": "late", "fromBot": True, "entryId": "l",
                                       "refs": ["ptt-ref"], "entry": {"requestId": "never-seen"}}), "late")
        self.assertEqual(self.spoken, ["late"])

    def test_handle_ignores_other_bots_and_user_messages(self):
        h = self.listener.handle
        self.assertIsNone(h("message", {"id": 5, "text": "x", "fromBot": True, "agentName": "Someone else"}))
        self.assertIsNone(h("message", {"id": 6, "text": "x", "fromBot": False}))
        self.assertIsNone(h("message", {"id": 7, "text": "   ", "fromBot": True}))
        self.assertIsNone(h("activity", {"id": 8, "running": True}))
        self.assertEqual(h("message", {"id": 9, "text": "hi", "fromBot": True, "entryId": "z"}), "hi")
        self.assertEqual(self.listener.last_id, 9)

    def test_reconnect_resumes_since_last_event(self):
        self.start()
        self.fake.push([("message", {"id": 41, "text": "first", "fromBot": True, "entryId": "a"})])
        self.wait(lambda: self.spoken)
        # drop the stream from the server side; the listener reconnects from the last id it saw
        self.fake.stop()
        self.fake = FakeGbd(self.sock).start()
        self.wait(lambda: self.fake.event_queries, timeout=10)
        self.assertEqual(self.fake.event_queries[0].get("since"), "41")
        self.fake.push([("message", {"id": 42, "text": "second", "fromBot": True, "entryId": "b"})])
        self.wait(lambda: len(self.spoken) == 2)
        self.assertEqual(self.spoken, ["first", "second"])


class CommandSpeakerTests(unittest.TestCase):
    def test_text_is_the_last_argument(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.txt")
            speak = listen.command_speaker(f"sh -c 'printf \"%s|%s\\n\" \"$1\" \"$2\" >> {out}' sh first")
            speak("hello there")
            with open(out) as f:
                self.assertEqual(f.read(), "first|hello there\n")

    def test_empty_command_rejected(self):
        with self.assertRaises(ValueError):
            listen.command_speaker("   ")


if __name__ == "__main__":
    unittest.main()
