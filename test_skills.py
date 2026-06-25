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
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch

import skills


REPO_ROOT = Path(__file__).resolve().parent
SKILLS_PATH = REPO_ROOT / "skills.yaml"


class TestSkillsModule(unittest.TestCase):
    def test_list_skills_includes_seed_names(self):
        listing = skills.format_skills_list(SKILLS_PATH)
        for name in ("repo_summary", "competitor_scan", "price_check"):
            self.assertIn(name, listing)

    def test_repo_summary_resolves_github_blob_to_raw(self):
        github_url = (
            "https://github.com/google/computer-use-preview/blob/main/agent.py"
        )
        config = skills.resolve_skill(
            "repo_summary",
            skill_arg=github_url,
            path=SKILLS_PATH,
        )
        self.assertEqual(
            config.initial_url,
            "https://raw.githubusercontent.com/google/computer-use-preview/main/agent.py",
        )
        self.assertEqual(
            config.query,
            "Summarize how the main functions in this file work, based only on its contents.",
        )
        self.assertTrue(config.concise_mode)

    def test_unknown_skill_raises_key_error_with_available_names(self):
        with self.assertRaises(KeyError) as ctx:
            skills.resolve_skill("does_not_exist", path=SKILLS_PATH)
        message = str(ctx.exception)
        self.assertIn("does_not_exist", message)
        self.assertIn("repo_summary", message)
        self.assertIn("competitor_scan", message)
        self.assertIn("price_check", message)


class TestSkillsCli(unittest.TestCase):
    @patch("main.argparse.ArgumentParser")
    def test_list_skills_exits_without_running(self, mock_arg_parser):
        import main

        mock_args = type(
            "Args",
            (),
            {
                "list_skills": True,
                "replay": None,
                "skill": None,
                "skill_arg": None,
            },
        )()
        mock_arg_parser.return_value.parse_args.return_value = mock_args

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = main.main()

        output = buffer.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("repo_summary", output)
        self.assertIn("competitor_scan", output)
        self.assertIn("price_check", output)

    @patch("main.argparse.ArgumentParser")
    def test_unknown_skill_exits_cleanly(self, mock_arg_parser):
        import main

        mock_args = type(
            "Args",
            (),
            {
                "list_skills": False,
                "replay": None,
                "skill": "missing_skill",
                "skill_arg": None,
            },
        )()
        mock_arg_parser.return_value.parse_args.return_value = mock_args

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            result = main.main()

        output = buffer.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("missing_skill", output)
        self.assertIn("repo_summary", output)

    @patch("main.RunLogger")
    @patch("main.make_log_path")
    @patch("main.PlaywrightComputer")
    @patch("main.BrowserAgent")
    @patch("main.argparse.ArgumentParser")
    def test_skill_repo_summary_uses_resolved_config(
        self,
        mock_arg_parser,
        mock_browser_agent,
        mock_playwright,
        mock_make_log_path,
        mock_run_logger_cls,
    ):
        import main

        mock_make_log_path.return_value = "logs/test.jsonl"
        mock_run_logger_cls.return_value = MagicMock()

        github_url = (
            "https://github.com/google/computer-use-preview/blob/main/agent.py"
        )
        mock_args = type(
            "Args",
            (),
            {
                "list_skills": False,
                "replay": None,
                "skill": "repo_summary",
                "skill_arg": github_url,
                "env": "playwright",
                "highlight_mouse": False,
            },
        )()
        mock_arg_parser.return_value.parse_args.return_value = mock_args

        main.main()

        mock_playwright.assert_called_once()
        _, kwargs = mock_playwright.call_args
        self.assertEqual(
            kwargs["initial_url"],
            "https://raw.githubusercontent.com/google/computer-use-preview/main/agent.py",
        )

        mock_browser_agent.assert_called_once()
        _, agent_kwargs = mock_browser_agent.call_args
        self.assertEqual(
            agent_kwargs["query"],
            "Summarize how the main functions in this file work, based only on its contents.",
        )
        self.assertTrue(agent_kwargs["concise_mode"])


if __name__ == "__main__":
    unittest.main()
