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
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

import config
import main
from run_log import format_replay_line, replay_log

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "test", "fixtures", "sample_run.jsonl"
)


def _base_args(**overrides):
    defaults = {
        "query": "test_query",
        "replay": None,
        "env": "playwright",
        "initial_url": "test_url",
        "highlight_mouse": False,
        "model": "test_model",
        "skill": None,
        "skill_arg": None,
        "list_skills": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


class TestMain(unittest.TestCase):

    @patch("main.replay_log")
    @patch("main.argparse.ArgumentParser")
    def test_replay_skips_browser_and_agent(self, mock_arg_parser, mock_replay_log):
        mock_arg_parser.return_value.parse_args.return_value = _base_args(
            replay=FIXTURE_PATH,
            query=None,
        )
        mock_replay_log.return_value = 0

        with patch("main.PlaywrightComputer") as mock_playwright, patch(
            "main.BrowserAgent"
        ) as mock_browser_agent:
            result = main.main()

        mock_replay_log.assert_called_once_with(FIXTURE_PATH)
        mock_playwright.assert_not_called()
        mock_browser_agent.assert_not_called()
        self.assertEqual(result, 0)

    @patch("builtins.print")
    @patch("main.replay_log")
    @patch("main.argparse.ArgumentParser")
    def test_replay_wins_over_query(self, mock_arg_parser, mock_replay_log, mock_print):
        mock_arg_parser.return_value.parse_args.return_value = _base_args(
            replay=FIXTURE_PATH,
            query="ignored query",
        )
        mock_replay_log.return_value = 0

        main.main()

        mock_print.assert_any_call(
            "Note: --replay takes precedence; ignoring --query."
        )
        mock_replay_log.assert_called_once_with(FIXTURE_PATH)

    def test_replay_prints_expected_summary(self):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]

        buf = io.StringIO()
        with redirect_stdout(buf):
            replay_log(FIXTURE_PATH)

        output = buf.getvalue()
        self.assertIn("query='Go to example.com'", output)
        self.assertIn(format_replay_line(records[1]), output)
        self.assertIn(format_replay_line(records[2]), output)

    @patch("main.RunLogger")
    @patch("main.make_log_path")
    @patch("main.argparse.ArgumentParser")
    @patch("main.PlaywrightComputer")
    @patch("main.BrowserAgent")
    def test_main_playwright(
        self,
        mock_browser_agent,
        mock_playwright_computer,
        mock_arg_parser,
        mock_make_log_path,
        mock_run_logger_cls,
    ):
        mock_arg_parser.return_value.parse_args.return_value = _base_args(
            env="playwright",
            initial_url="test_url",
            highlight_mouse=True,
            query="test_query",
            model="test_model",
        )
        mock_make_log_path.return_value = "logs/test.jsonl"
        mock_run_logger = MagicMock()
        mock_run_logger_cls.return_value = mock_run_logger

        main.main()

        mock_playwright_computer.assert_called_once_with(
            screen_size=main.PLAYWRIGHT_SCREEN_SIZE,
            initial_url="test_url",
            highlight_mouse=True,
        )
        mock_run_logger.write_meta.assert_called_once()
        mock_browser_agent.assert_called_once()
        mock_browser_agent.return_value.agent_loop.assert_called_once_with(
            max_steps=config.MAX_STEPS,
        )

    @patch("main.RunLogger")
    @patch("main.make_log_path")
    @patch("main.argparse.ArgumentParser")
    @patch("main.BrowserbaseComputer")
    @patch("main.BrowserAgent")
    def test_main_browserbase(
        self,
        mock_browser_agent,
        mock_browserbase_computer,
        mock_arg_parser,
        mock_make_log_path,
        mock_run_logger_cls,
    ):
        mock_arg_parser.return_value.parse_args.return_value = _base_args(
            env="browserbase",
            query="test_query",
            model="test_model",
            initial_url="test_url",
        )
        mock_make_log_path.return_value = "logs/test.jsonl"
        mock_run_logger = MagicMock()
        mock_run_logger_cls.return_value = mock_run_logger

        main.main()

        mock_browserbase_computer.assert_called_once_with(
            screen_size=main.PLAYWRIGHT_SCREEN_SIZE,
            initial_url="test_url",
        )
        mock_run_logger.write_meta.assert_called_once()
        mock_browser_agent.assert_called_once()
        mock_browser_agent.return_value.agent_loop.assert_called_once_with(
            max_steps=config.MAX_STEPS,
        )


if __name__ == "__main__":
    unittest.main()
