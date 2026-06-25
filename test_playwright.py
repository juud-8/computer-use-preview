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
from unittest.mock import MagicMock

from computers import EnvState
from computers.playwright.playwright import PlaywrightComputer, _sanitize_url


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


if __name__ == "__main__":
    unittest.main()
