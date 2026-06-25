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

import unittest
from unittest.mock import MagicMock, patch

from computers import EnvState
from computers.playwright.playwright import (
    EXTRACT_TEXT_MAX_CHARS,
    PlaywrightComputer,
    _github_blob_to_raw_url,
    _sanitize_url,
    _truncate_text,
)


class TestSanitizeUrl(unittest.TestCase):
    def test_strips_trailing_junk(self):
        self.assertEqual(
            _sanitize_url("https://example.com/path)"),
            "https://example.com/path",
        )
        self.assertEqual(
            _sanitize_url("https://example.com/path],"),
            "https://example.com/path",
        )


class TestGithubRawUrl(unittest.TestCase):
    def test_blob_to_raw(self):
        self.assertEqual(
            _github_blob_to_raw_url(
                "https://github.com/user/repo/blob/main/agent.py"
            ),
            "https://raw.githubusercontent.com/user/repo/main/agent.py",
        )

    def test_non_github_returns_none(self):
        self.assertIsNone(_github_blob_to_raw_url("https://example.com/file"))


class TestTruncateText(unittest.TestCase):
    def test_truncates_long_text(self):
        text = "x" * (EXTRACT_TEXT_MAX_CHARS + 100)
        result = _truncate_text(text)
        self.assertEqual(result[:EXTRACT_TEXT_MAX_CHARS], "x" * EXTRACT_TEXT_MAX_CHARS)
        self.assertIn("...[truncated,", result)
        self.assertIn(f"{len(text)} chars total]", result)


class TestPlaywrightNavigate(unittest.TestCase):
    def setUp(self):
        self.computer = PlaywrightComputer(screen_size=(800, 600))
        self.computer._page = MagicMock()
        self.computer._page.url = "https://example.com/current"
        self.computer._page.viewport_size = {"width": 800, "height": 600}
        self.computer._page.screenshot.return_value = b"png-bytes"

    def test_navigate_bad_url_returns_env_state(self):
        self.computer._page.goto.side_effect = Exception("Invalid URL")

        result = self.computer.navigate("https://bad.example.com)")

        self.assertIsInstance(result, EnvState)
        self.assertEqual(result.url, "https://example.com/current")
        self.assertEqual(result.screenshot, b"png-bytes")
        self.computer._page.goto.assert_called_once_with("https://bad.example.com")


class TestExtractText(unittest.TestCase):
    def setUp(self):
        self.computer = PlaywrightComputer(screen_size=(800, 600))
        self.computer._page = MagicMock()
        self.computer._page.url = "https://example.com/page"

    def test_extract_text_body(self):
        self.computer._page.inner_text.return_value = "Hello, world!"

        result = self.computer.extract_text()

        self.computer._page.inner_text.assert_called_once_with("body")
        self.assertEqual(result, {"text": "Hello, world!"})

    def test_extract_text_with_selector(self):
        self.computer._page.inner_text.return_value = "Title"

        result = self.computer.extract_text(selector="h1")

        self.computer._page.inner_text.assert_called_once_with("h1")
        self.assertEqual(result, {"text": "Title"})

    @patch("computers.playwright.playwright.urllib.request.urlopen")
    def test_extract_text_github_fetches_raw(self, mock_urlopen):
        self.computer._page.url = (
            "https://github.com/user/repo/blob/main/agent.py"
        )
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b"print('hello')"
        )

        result = self.computer.extract_text()

        mock_urlopen.assert_called_once_with(
            "https://raw.githubusercontent.com/user/repo/main/agent.py",
            timeout=30,
        )
        self.computer._page.inner_text.assert_not_called()
        self.assertEqual(result, {"text": "print('hello')"})


class TestGoBack(unittest.TestCase):
    def setUp(self):
        self.computer = PlaywrightComputer(screen_size=(800, 600))
        self.computer._page = MagicMock()
        self.computer._page.url = "https://example.com/current"
        self.computer._page.viewport_size = {"width": 800, "height": 600}
        self.computer._page.screenshot.return_value = b"png-bytes"

    def test_go_back_calls_page_go_back(self):
        result = self.computer.go_back()

        self.computer._page.go_back.assert_called_once()
        self.assertIsInstance(result, EnvState)
        self.assertEqual(result.url, "https://example.com/current")

    def test_go_back_failure_returns_env_state(self):
        self.computer._page.go_back.side_effect = Exception("No history")

        result = self.computer.go_back()

        self.assertIsInstance(result, EnvState)
        self.assertEqual(result.screenshot, b"png-bytes")


if __name__ == "__main__":
    unittest.main()
