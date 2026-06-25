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
import os

DEFAULT_INITIAL_URL = os.environ.get(
    "DEFAULT_INITIAL_URL", "https://www.google.com"
)
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gemini-3.5-flash")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "50"))


def verbose_reasoning() -> bool:
    val = os.environ.get("VERBOSE_REASONING")
    if val is None:
        return True
    return val.lower() in ("true", "1", "yes")
