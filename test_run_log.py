# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from run_log import (
    RunLogger,
    format_replay_line,
    replay_log,
    sanitize_for_log,
)


class TestRunLog(unittest.TestCase):
    def test_run_logger_writes_meta_and_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "run.jsonl")
            logger = RunLogger(path)
            logger.write_meta(
                query="find pricing",
                initial_url="https://example.com",
                model="test-model",
                concise_mode=True,
                max_steps=10,
            )
            logger.write_step(
                action_name="navigate",
                action_args={"url": "https://example.com/pricing"},
                reasoning_text="Opening pricing page",
                resulting_url="https://example.com/pricing",
            )
            logger.write_step(
                action_name="click",
                action_args={"x": 100, "y": 200},
                reasoning_text="Clicking sign in",
                resulting_url="https://example.com/login",
            )
            logger.close()

            with open(path, encoding="utf-8") as f:
                lines = f.readlines()

            self.assertEqual(len(lines), 3)
            meta = json.loads(lines[0])
            step1 = json.loads(lines[1])
            step2 = json.loads(lines[2])

            self.assertEqual(meta["type"], "meta")
            self.assertEqual(meta["query"], "find pricing")
            self.assertEqual(meta["initial_url"], "https://example.com")
            self.assertEqual(meta["model"], "test-model")
            self.assertTrue(meta["concise_mode"])
            self.assertEqual(meta["max_steps"], 10)

            self.assertEqual(step1["type"], "step")
            self.assertEqual(step1["step_number"], 1)
            self.assertEqual(step1["action_name"], "navigate")
            self.assertEqual(step1["action_args"]["url"], "https://example.com/pricing")
            self.assertEqual(step1["reasoning_text"], "Opening pricing page")
            self.assertEqual(step1["resulting_url"], "https://example.com/pricing")

            self.assertEqual(step2["step_number"], 2)
            self.assertEqual(step2["action_name"], "click")

    def test_sanitize_strips_screenshot_and_bytes(self):
        raw = {
            "screenshot": b"\x89PNGfake-image-data",
            "data": b"base64-bytes",
            "inline_data": {"mime_type": "image/png", "data": b"more-bytes"},
            "url": "https://example.com",
            "nested": {"image": b"nested-bytes", "text": "keep me"},
        }
        cleaned = sanitize_for_log(raw)
        self.assertEqual(cleaned, {"url": "https://example.com", "nested": {"text": "keep me"}})

        serialized = json.dumps(cleaned)
        self.assertNotIn("screenshot", serialized)
        self.assertNotIn("PNG", serialized)
        self.assertNotIn("base64", serialized.lower())

    def test_replay_log_prints_summary(self):
        fixture_lines = [
            {
                "type": "meta",
                "query": "Find pricing",
                "initial_url": "https://www.google.com",
                "model": "gemini-3.5-flash",
                "concise_mode": False,
                "max_steps": 50,
            },
            {
                "type": "step",
                "step_number": 1,
                "action_name": "navigate",
                "action_args": {"url": "https://example.com"},
                "reasoning_text": "Opening the target site",
                "resulting_url": "https://example.com",
            },
            {
                "type": "step",
                "step_number": 2,
                "action_name": "click",
                "action_args": {"x": 500, "y": 300},
                "reasoning_text": "Clicking the sign-in button",
                "resulting_url": "https://example.com/login",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "fixture.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for record in fixture_lines:
                    f.write(json.dumps(record) + "\n")

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = replay_log(path)

            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("query='Find pricing'", output)
            self.assertIn("initial_url=https://www.google.com", output)
            self.assertIn("model=gemini-3.5-flash", output)
            self.assertIn(
                format_replay_line(fixture_lines[1]),
                output,
            )
            self.assertIn(
                format_replay_line(fixture_lines[2]),
                output,
            )


if __name__ == "__main__":
    unittest.main()
