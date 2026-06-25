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

from prompts import (
    CONCISE_SYSTEM_INSTRUCTION,
    build_initial_user_message,
    get_system_instruction,
)


class TestPrompts(unittest.TestCase):
    def test_get_system_instruction_default(self):
        self.assertIsNone(get_system_instruction(False))

    def test_get_system_instruction_concise(self):
        instruction = get_system_instruction(True)
        self.assertEqual(instruction, CONCISE_SYSTEM_INSTRUCTION)
        self.assertIn(
            "Output at most one short sentence of reasoning per step.",
            instruction,
        )
        self.assertIn(
            "do not re-scroll to re-verify it — answer from what you've seen.",
            instruction,
        )

    def test_build_initial_user_message_default(self):
        self.assertEqual(
            build_initial_user_message("go to example.com", False),
            "go to example.com",
        )

    def test_build_initial_user_message_concise(self):
        self.assertEqual(
            build_initial_user_message("go to example.com", True),
            f"{CONCISE_SYSTEM_INSTRUCTION}\n\ngo to example.com",
        )


if __name__ == "__main__":
    unittest.main()
