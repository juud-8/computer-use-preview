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

from urls import github_to_raw_url


class TestGithubToRawUrl(unittest.TestCase):
    def test_blob_url(self):
        self.assertEqual(
            github_to_raw_url("https://github.com/o/r/blob/main/a/b.py"),
            "https://raw.githubusercontent.com/o/r/main/a/b.py",
        )

    def test_raw_url_form(self):
        self.assertEqual(
            github_to_raw_url("https://github.com/o/r/raw/main/a/b.py"),
            "https://raw.githubusercontent.com/o/r/main/a/b.py",
        )

    def test_www_prefix(self):
        self.assertEqual(
            github_to_raw_url("https://www.github.com/o/r/blob/main/b.py"),
            "https://raw.githubusercontent.com/o/r/main/b.py",
        )

    def test_already_raw_is_idempotent(self):
        url = "https://raw.githubusercontent.com/o/r/main/b.py"
        self.assertEqual(github_to_raw_url(url), url)

    def test_non_github_unchanged(self):
        url = "https://example.com/o/r/blob/main/b.py"
        self.assertEqual(github_to_raw_url(url), url)

    def test_repo_root_unchanged(self):
        url = "https://github.com/o/r"
        self.assertEqual(github_to_raw_url(url), url)


if __name__ == "__main__":
    unittest.main()
