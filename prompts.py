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

CONCISE_SYSTEM_INSTRUCTION = """You are a browser automation agent. Be direct and efficient.

Reasoning rules:
- At most one short sentence of reasoning per step.
- No theatrical narration, no meta-commentary, no deliberation — act immediately.
- Prefer the next concrete browser action over explaining what you might do.

Navigation rules:
- If you have already seen the relevant content, do not re-scroll to re-verify it — answer from what you've seen."""


def get_system_instruction(concise_mode: bool) -> str | None:
    if concise_mode:
        return CONCISE_SYSTEM_INSTRUCTION
    return None
