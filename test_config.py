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
from unittest.mock import patch

import config
from config import RunSettings, resolve_run_settings
from skills import SkillConfig


class TestEnvBools(unittest.TestCase):
    def test_verbose_reasoning_defaults_true(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(config.verbose_reasoning())

    def test_verbose_reasoning_false(self):
        with patch.dict("os.environ", {"VERBOSE_REASONING": "false"}):
            self.assertFalse(config.verbose_reasoning())

    def test_concise_mode_defaults_false(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(config.concise_mode())

    def test_concise_mode_truthy_variants(self):
        for val in ("true", "1", "yes", "TRUE", "Yes"):
            with patch.dict("os.environ", {"CONCISE_MODE": val}):
                self.assertTrue(config.concise_mode(), val)

    def test_concise_mode_falsy_variants(self):
        for val in ("false", "0", "no", "banana", ""):
            with patch.dict("os.environ", {"CONCISE_MODE": val}):
                self.assertFalse(config.concise_mode(), val)


class TestResolveRunSettings(unittest.TestCase):
    def _skill(self, **overrides):
        base = dict(
            name="s",
            query="skill query",
            initial_url="https://skill.example",
            concise_mode=True,
            model="skill-model",
        )
        base.update(overrides)
        return SkillConfig(**base)

    def test_requires_query(self):
        with self.assertRaises(ValueError):
            resolve_run_settings()

    def test_cli_only(self):
        settings = resolve_run_settings(cli_query="q")
        self.assertEqual(settings.query, "q")
        self.assertEqual(settings.initial_url, config.DEFAULT_INITIAL_URL)
        self.assertEqual(settings.model, config.DEFAULT_MODEL)
        self.assertEqual(settings.max_steps, config.MAX_STEPS)

    def test_cli_overrides_skill(self):
        settings = resolve_run_settings(
            cli_query="cli q",
            cli_initial_url="https://cli.example",
            cli_model="cli-model",
            skill=self._skill(),
        )
        self.assertEqual(settings.query, "cli q")
        self.assertEqual(settings.initial_url, "https://cli.example")
        self.assertEqual(settings.model, "cli-model")

    def test_skill_fills_missing_cli_values(self):
        settings = resolve_run_settings(skill=self._skill())
        self.assertEqual(settings.query, "skill query")
        self.assertEqual(settings.initial_url, "https://skill.example")
        self.assertEqual(settings.model, "skill-model")
        self.assertTrue(settings.concise_mode)

    def test_skill_none_fields_fall_back_to_defaults(self):
        skill = self._skill(initial_url=None, model=None, concise_mode=None)
        with patch.dict("os.environ", {"CONCISE_MODE": "false"}):
            settings = resolve_run_settings(skill=skill)
        self.assertEqual(settings.initial_url, config.DEFAULT_INITIAL_URL)
        self.assertEqual(settings.model, config.DEFAULT_MODEL)
        self.assertFalse(settings.concise_mode)

    def test_skill_concise_false_beats_env_true(self):
        skill = self._skill(concise_mode=False)
        with patch.dict("os.environ", {"CONCISE_MODE": "true"}):
            settings = resolve_run_settings(skill=skill)
        self.assertFalse(settings.concise_mode)

    def test_settings_are_frozen(self):
        settings = resolve_run_settings(cli_query="q")
        self.assertIsInstance(settings, RunSettings)
        with self.assertRaises(Exception):
            settings.query = "other"


if __name__ == "__main__":
    unittest.main()
