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
"""Shared URL helpers used by both the skills registry and the browser computers."""
import re

_GITHUB_FILE_URL = re.compile(
    r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/(?:blob|raw)/([^/]+)/(.+)"
)


def github_to_raw_url(url: str) -> str:
    """Rewrite a github.com blob/raw file URL to raw.githubusercontent.com.

    Returns the URL unchanged when it is not a rewritable GitHub file URL
    (including URLs that already point at raw.githubusercontent.com).
    """
    if "raw.githubusercontent.com" in url:
        return url
    match = _GITHUB_FILE_URL.match(url)
    if not match:
        return url
    owner, repo, ref, path = match.groups()
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
