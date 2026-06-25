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
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from google.genai import types
from agent import BrowserAgent, multiply_numbers, extract_text, save_to_file
from computers import EnvState
from prompts import CONCISE_SYSTEM_INSTRUCTION

class TestBrowserAgent(unittest.TestCase):
    def setUp(self):
        os.environ["GEMINI_API_KEY"] = "test_api_key"
        self.mock_browser_computer = MagicMock()
        self.mock_browser_computer.screen_size.return_value = (1000, 1000)
        self.agent = BrowserAgent(
            browser_computer=self.mock_browser_computer,
            query="test query",
            model_name="test_model"
        )
        # Mock the genai client
        self.agent._client = MagicMock()

    def test_multiply_numbers(self):
        self.assertEqual(multiply_numbers(2, 3), {"result": 6})

    def test_handle_action_open_web_browser(self):
        action = types.FunctionCall(name="open_web_browser", args={})
        self.agent.handle_action(action, use_legacy_actions=True)
        self.mock_browser_computer.open_web_browser.assert_called_once()

    def test_handle_action_click_at(self):
        action = types.FunctionCall(name="click_at", args={"x": 100, "y": 200})
        self.agent.handle_action(action, use_legacy_actions=True)
        self.mock_browser_computer.click_at.assert_called_once_with(x=100, y=200)

    def test_handle_action_type_text_at(self):
        action = types.FunctionCall(name="type_text_at", args={"x": 100, "y": 200, "text": "hello"})
        self.agent.handle_action(action, use_legacy_actions=True)
        self.mock_browser_computer.type_text_at.assert_called_once_with(
            x=100, y=200, text="hello", press_enter=False, clear_before_typing=True
        )

    def test_handle_action_scroll_document(self):
        action = types.FunctionCall(name="scroll_document", args={"direction": "down"})
        self.agent.handle_action(action, use_legacy_actions=True)
        self.mock_browser_computer.scroll_document.assert_called_once_with("down")

    def test_handle_action_navigate(self):
        action = types.FunctionCall(name="navigate", args={"url": "https://example.com"})
        self.agent.handle_action(action, use_legacy_actions=True)
        self.mock_browser_computer.navigate.assert_called_once_with("https://example.com")

    def test_handle_action_unknown_function(self):
        action = types.FunctionCall(name="unknown_function", args={})
        with self.assertRaises(ValueError):
            self.agent.handle_action(action, use_legacy_actions=True)

    def test_denormalize_x(self):
        self.assertEqual(self.agent.denormalize_x(500), 500)

    def test_denormalize_y(self):
        self.assertEqual(self.agent.denormalize_y(500), 500)

    @patch('agent.BrowserAgent.get_model_response')
    def test_run_one_iteration_no_function_calls(self, mock_get_model_response):
        mock_response = MagicMock()
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [types.Part(text="some reasoning")]
        mock_response.candidates = [mock_candidate]
        mock_get_model_response.return_value = mock_response

        result = self.agent.run_one_iteration()

        self.assertEqual(result, "COMPLETE")
        self.assertEqual(len(self.agent._contents), 2)
        self.assertEqual(self.agent._contents[1], mock_candidate.content)

    @patch('agent.BrowserAgent.get_model_response')
    @patch('agent.BrowserAgent.handle_action')
    def test_run_one_iteration_with_function_call(self, mock_handle_action, mock_get_model_response):
        mock_response = MagicMock()
        mock_candidate = MagicMock()
        function_call = types.FunctionCall(name="navigate", args={"url": "https://example.com"})
        mock_candidate.content.parts = [types.Part(function_call=function_call)]
        mock_response.candidates = [mock_candidate]
        mock_get_model_response.return_value = mock_response

        mock_env_state = EnvState(screenshot=b"screenshot", url="https://example.com")
        mock_handle_action.return_value = mock_env_state

        result = self.agent.run_one_iteration()

        self.assertEqual(result, "CONTINUE")
        mock_handle_action.assert_called_once_with(function_call, False)
        self.assertEqual(len(self.agent._contents), 3)

    @patch("agent.BrowserAgent.get_model_response")
    def test_run_one_iteration_safety_block_no_attribute_error(
        self, mock_get_model_response
    ):
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = types.BlockedReason.SAFETY
        mock_get_model_response.return_value = mock_response

        with self.assertRaises(ValueError) as ctx:
            self.agent.run_one_iteration()

        self.assertIn("safety", str(ctx.exception).lower())

    @patch("agent.BrowserAgent.get_model_response")
    def test_run_one_iteration_other_block_reason_no_attribute_error(
        self, mock_get_model_response
    ):
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = types.BlockedReason.OTHER
        mock_get_model_response.return_value = mock_response

        with self.assertRaises(ValueError) as ctx:
            self.agent.run_one_iteration()

        self.assertIn("Empty response", str(ctx.exception))

    def test_agent_loop_max_steps(self):
        with patch.object(
            self.agent, "run_one_iteration", return_value="CONTINUE"
        ) as mock_iter:
            self.agent.agent_loop(max_steps=3)
        self.assertEqual(mock_iter.call_count, 3)

    def test_default_no_system_instruction(self):
        self.assertIsNone(self.agent._generate_content_config.system_instruction)
        self.assertEqual(
            self.agent._contents[0].parts[0].text,
            "test query",
        )

    def test_concise_mode_injects_instruction_into_first_user_message(self):
        agent = BrowserAgent(
            browser_computer=self.mock_browser_computer,
            query="test query",
            model_name="test_model",
            concise_mode=True,
        )
        agent._client = MagicMock()
        self.assertIsNone(agent._generate_content_config.system_instruction)
        self.assertEqual(
            agent._contents[0].parts[0].text,
            f"{CONCISE_SYSTEM_INSTRUCTION}\n\ntest query",
        )
        self.assertFalse(
            agent._generate_content_config.thinking_config.include_thoughts
        )

    def test_handle_action_extract_text(self):
        self.mock_browser_computer.extract_text.return_value = {"text": "hello"}
        action = types.FunctionCall(name="extract_text", args={})

        result = self.agent.handle_action(action, use_legacy_actions=False)

        self.mock_browser_computer.extract_text.assert_called_once_with(None)
        self.assertEqual(result, {"text": "hello"})

    def test_save_to_file_writes_under_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                result = save_to_file("foo.txt", "hello content")
                self.assertIn("Saved to", result["result"])
                with open(os.path.join("outputs", "foo.txt"), encoding="utf-8") as f:
                    self.assertEqual(f.read(), "hello content")
            finally:
                os.chdir(original_cwd)

    def test_save_to_file_rejects_traversal(self):
        result = save_to_file("../outside.txt", "bad")
        self.assertIn("error", result)
        self.assertIn("escapes", result["error"])


if __name__ == "__main__":
    unittest.main()
