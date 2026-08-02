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
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from google.genai import errors as genai_errors
from google.genai import types
from agent import (
    AUTH_BILLING_ERROR_MESSAGE,
    BrowserAgent,
    SAFETY_BLOCK_MESSAGE,
    extract_text,
    multiply_numbers,
    save_to_file,
)
from computers import EnvState
from prompts import CONCISE_SYSTEM_INSTRUCTION
from run_log import RunLogger

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

    @patch("termcolor.cprint")
    @patch("agent.BrowserAgent.get_model_response")
    def test_run_one_iteration_safety_block_no_attribute_error(
        self, mock_get_model_response, mock_cprint
    ):
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = types.BlockedReason.SAFETY
        mock_get_model_response.return_value = mock_response

        result = self.agent.run_one_iteration()

        self.assertEqual(result, "COMPLETE")
        mock_cprint.assert_called_once_with(
            SAFETY_BLOCK_MESSAGE, color="yellow", attrs=["bold"]
        )

    @patch("agent.BrowserAgent.get_model_response")
    def test_agent_loop_safety_block_exits_gracefully(self, mock_get_model_response):
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = types.BlockedReason.SAFETY
        mock_get_model_response.return_value = mock_response

        self.agent.agent_loop()

        mock_get_model_response.assert_called_once()

    @patch("agent.time.sleep")
    def test_get_model_response_401_fails_fast(self, mock_sleep):
        auth_error = genai_errors.ClientError(
            401, {"error": {"message": "Unauthorized"}}
        )
        self.agent._client.models.generate_content.side_effect = auth_error

        with self.assertRaises(genai_errors.ClientError):
            self.agent.get_model_response()

        self.agent._client.models.generate_content.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("agent.time.sleep")
    def test_get_model_response_403_fails_fast(self, mock_sleep):
        billing_error = genai_errors.ClientError(
            403, {"error": {"message": "Forbidden"}}
        )
        self.agent._client.models.generate_content.side_effect = billing_error

        with self.assertRaises(genai_errors.ClientError):
            self.agent.get_model_response()

        self.agent._client.models.generate_content.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("termcolor.cprint")
    @patch("agent.time.sleep")
    def test_get_model_response_401_prints_auth_message(self, mock_sleep, mock_cprint):
        auth_error = genai_errors.ClientError(
            401, {"error": {"message": "Unauthorized"}}
        )
        self.agent._client.models.generate_content.side_effect = auth_error

        with self.assertRaises(genai_errors.ClientError):
            self.agent.get_model_response()

        mock_cprint.assert_called_once_with(
            AUTH_BILLING_ERROR_MESSAGE, color="red", attrs=["bold"]
        )

    @patch("agent.time.sleep")
    def test_get_model_response_500_retries(self, mock_sleep):
        server_error = genai_errors.ServerError(
            500, {"error": {"message": "Internal Server Error"}}
        )
        mock_response = MagicMock()
        self.agent._client.models.generate_content.side_effect = [
            server_error,
            mock_response,
        ]

        result = self.agent.get_model_response()

        self.assertEqual(result, mock_response)
        self.assertEqual(self.agent._client.models.generate_content.call_count, 2)
        mock_sleep.assert_called_once_with(1)

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

    @patch("agent.BrowserAgent.handle_action")
    @patch("agent.BrowserAgent.get_model_response")
    def test_agent_loop_writes_jsonl_meta_and_steps(
        self, mock_get_model_response, mock_handle_action
    ):
        fc_response = MagicMock()
        fc_candidate = MagicMock()
        function_call = types.FunctionCall(
            name="navigate", args={"url": "https://example.com"}
        )
        fc_candidate.content.parts = [
            types.Part(text="Opening the page"),
            types.Part(function_call=function_call),
        ]
        fc_response.candidates = [fc_candidate]

        complete_response = MagicMock()
        complete_candidate = MagicMock()
        complete_candidate.content.parts = [
            types.Part(text="Done navigating")
        ]
        complete_response.candidates = [complete_candidate]

        mock_get_model_response.side_effect = [fc_response, complete_response]
        mock_handle_action.return_value = EnvState(
            screenshot=b"screenshot-bytes", url="https://example.com"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "run.jsonl")
            run_logger = RunLogger(log_path)
            run_logger.write_meta(
                query="test query",
                initial_url="https://start.example",
                model="test_model",
                concise_mode=False,
                max_steps=5,
            )
            self.agent._run_logger = run_logger

            self.agent.agent_loop(max_steps=5)

            with open(log_path, encoding="utf-8") as f:
                records = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(records), 2)
        meta = records[0]
        self.assertEqual(meta["type"], "meta")
        self.assertEqual(meta["query"], "test query")
        self.assertEqual(meta["initial_url"], "https://start.example")
        self.assertEqual(meta["model"], "test_model")
        self.assertFalse(meta["concise_mode"])
        self.assertEqual(meta["max_steps"], 5)

        step = records[1]
        self.assertEqual(step["type"], "step")
        self.assertEqual(step["step_number"], 1)
        self.assertEqual(step["action_name"], "navigate")
        self.assertEqual(step["action_args"], {"url": "https://example.com"})
        self.assertEqual(step["reasoning_text"], "Opening the page")
        self.assertEqual(step["resulting_url"], "https://example.com")

    @patch("agent.BrowserAgent.handle_action")
    @patch("agent.BrowserAgent.get_model_response")
    def test_jsonl_never_contains_screenshot_data(
        self, mock_get_model_response, mock_handle_action
    ):
        fc_response = MagicMock()
        fc_candidate = MagicMock()
        function_call = types.FunctionCall(name="click", args={"x": 100, "y": 200})
        fc_candidate.content.parts = [
            types.Part(text="Clicking"),
            types.Part(function_call=function_call),
        ]
        fc_response.candidates = [fc_candidate]

        complete_response = MagicMock()
        complete_candidate = MagicMock()
        complete_candidate.content.parts = [types.Part(text="Done")]
        complete_response.candidates = [complete_candidate]

        mock_get_model_response.side_effect = [fc_response, complete_response]
        screenshot_bytes = b"\x89PNGfakebytes"
        mock_handle_action.return_value = EnvState(
            screenshot=screenshot_bytes, url="https://x.com"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "run.jsonl")
            run_logger = RunLogger(log_path)
            run_logger.write_meta(
                query="test query",
                initial_url="https://example.com",
                model="test_model",
                concise_mode=False,
                max_steps=5,
            )
            self.agent._run_logger = run_logger

            self.agent.agent_loop(max_steps=5)

            with open(log_path, encoding="utf-8") as f:
                raw = f.read()
                records = [json.loads(line) for line in raw.splitlines() if line]

        self.assertNotIn("screenshot", raw)
        self.assertNotIn("inline_data", raw)
        self.assertNotIn("image/png", raw)
        self.assertNotIn(screenshot_bytes.decode("latin-1"), raw)
        step = records[1]
        self.assertEqual(step["resulting_url"], "https://x.com")
        self.assertNotIn("screenshot", step)


class TestActionDispatch(unittest.TestCase):
    """Coverage for the table-driven action dispatch."""

    def setUp(self):
        os.environ["GEMINI_API_KEY"] = "test_api_key"
        self.mock_browser_computer = MagicMock()
        self.mock_browser_computer.screen_size.return_value = (1000, 1000)
        self.agent = BrowserAgent(
            browser_computer=self.mock_browser_computer,
            query="test query",
            model_name="test_model",
        )
        self.agent._client = MagicMock()

    def test_every_modern_predefined_function_has_a_handler(self):
        from agent import PREDEFINED_COMPUTER_USE_FUNCTIONS

        handlers = self.agent._build_action_handlers(legacy=False)
        missing = [n for n in PREDEFINED_COMPUTER_USE_FUNCTIONS if n not in handlers]
        self.assertEqual(missing, [])

    def test_every_legacy_predefined_function_has_a_handler(self):
        from agent import LEGACY_PREDEFINED_COMPUTER_USE_FUNCTIONS

        handlers = self.agent._build_action_handlers(legacy=True)
        missing = [
            n for n in LEGACY_PREDEFINED_COMPUTER_USE_FUNCTIONS if n not in handlers
        ]
        self.assertEqual(missing, [])

    def test_custom_functions_available_in_both_modes(self):
        for legacy in (False, True):
            handlers = self.agent._build_action_handlers(legacy=legacy)
            for name in ("multiply_numbers", "extract_text", "save_to_file"):
                self.assertIn(name, handlers, f"legacy={legacy}")

    def test_modern_click_denormalizes(self):
        action = types.FunctionCall(name="click", args={"x": 500, "y": 250})
        self.agent.handle_action(action, use_legacy_actions=False)
        self.mock_browser_computer.click_at.assert_called_once_with(x=500, y=250)

    def test_modern_double_click(self):
        action = types.FunctionCall(name="double_click", args={"x": 100, "y": 100})
        self.agent.handle_action(action, use_legacy_actions=False)
        self.mock_browser_computer.double_click_at.assert_called_once_with(
            x=100, y=100
        )

    def test_modern_type_defaults_press_enter_false(self):
        action = types.FunctionCall(name="type", args={"text": "hi"})
        self.agent.handle_action(action, use_legacy_actions=False)
        self.mock_browser_computer.type_text.assert_called_once_with(
            text="hi", press_enter=False
        )

    def test_modern_scroll_down_denormalizes_magnitude(self):
        action = types.FunctionCall(
            name="scroll", args={"x": 500, "y": 500, "direction": "down"}
        )
        self.agent.handle_action(action, use_legacy_actions=False)
        self.mock_browser_computer.scroll_at.assert_called_once_with(
            x=500, y=500, direction="down", magnitude=800
        )

    def test_scroll_unknown_direction_raises(self):
        action = types.FunctionCall(
            name="scroll", args={"x": 0, "y": 0, "direction": "diagonal"}
        )
        with self.assertRaises(ValueError):
            self.agent.handle_action(action, use_legacy_actions=False)

    def test_modern_wait_casts_seconds_to_int(self):
        action = types.FunctionCall(name="wait", args={"seconds": 2.0})
        self.agent.handle_action(action, use_legacy_actions=False)
        self.mock_browser_computer.wait.assert_called_once_with(2)

    def test_modern_hotkey_passes_keys_list(self):
        action = types.FunctionCall(name="hotkey", args={"keys": ["Control", "a"]})
        self.agent.handle_action(action, use_legacy_actions=False)
        self.mock_browser_computer.key_combination.assert_called_once_with(
            ["Control", "a"]
        )

    def test_legacy_key_combination_splits_on_plus(self):
        action = types.FunctionCall(name="key_combination", args={"keys": "ctrl+a"})
        self.agent.handle_action(action, use_legacy_actions=True)
        self.mock_browser_computer.key_combination.assert_called_once_with(
            ["ctrl", "a"]
        )

    def test_drag_and_drop_denormalizes_all_points(self):
        action = types.FunctionCall(
            name="drag_and_drop",
            args={"x": 100, "y": 200, "destination_x": 300, "destination_y": 400},
        )
        self.agent.handle_action(action, use_legacy_actions=False)
        self.mock_browser_computer.drag_and_drop.assert_called_once_with(
            x=100, y=200, destination_x=300, destination_y=400
        )

    def test_modern_unknown_function_raises(self):
        action = types.FunctionCall(name="nope", args={})
        with self.assertRaises(ValueError):
            self.agent.handle_action(action, use_legacy_actions=False)

    def test_handle_legacy_action_delegates(self):
        action = types.FunctionCall(name="click_at", args={"x": 10, "y": 20})
        self.agent.handle_legacy_action(action)
        self.mock_browser_computer.click_at.assert_called_once_with(x=10, y=20)


class TestSafetyConfirmation(unittest.TestCase):
    def setUp(self):
        os.environ["GEMINI_API_KEY"] = "test_api_key"
        mock_computer = MagicMock()
        mock_computer.screen_size.return_value = (1000, 1000)
        self.agent = BrowserAgent(
            browser_computer=mock_computer,
            query="q",
            model_name="m",
        )
        self.agent._client = MagicMock()

    def _safety(self):
        return {"decision": "require_confirmation", "explanation": "why"}

    @patch("builtins.input", return_value="yes")
    def test_yes_continues(self, _mock_input):
        self.assertEqual(self.agent._get_safety_confirmation(self._safety()), "CONTINUE")

    @patch("builtins.input", return_value="no")
    def test_no_terminates(self, _mock_input):
        self.assertEqual(
            self.agent._get_safety_confirmation(self._safety()), "TERMINATE"
        )

    def test_unknown_decision_raises_with_decision_in_message(self):
        with self.assertRaises(ValueError) as ctx:
            self.agent._get_safety_confirmation(
                {"decision": "weird_value", "explanation": "x"}
            )
        self.assertIn("weird_value", str(ctx.exception))


class TestScreenshotPruning(unittest.TestCase):
    def setUp(self):
        os.environ["GEMINI_API_KEY"] = "test_api_key"
        mock_computer = MagicMock()
        mock_computer.screen_size.return_value = (1000, 1000)
        self.agent = BrowserAgent(
            browser_computer=mock_computer,
            query="q",
            model_name="m",
        )
        self.agent._client = MagicMock()

    @staticmethod
    def _screenshot_turn():
        from google.genai.types import Content, FunctionResponse, Part
        from google.genai import types as gtypes

        return Content(
            role="user",
            parts=[
                Part(
                    function_response=FunctionResponse(
                        name="click",
                        response={"url": "https://x.com"},
                        parts=[
                            gtypes.FunctionResponsePart(
                                inline_data=gtypes.FunctionResponseBlob(
                                    mime_type="image/png", data=b"png"
                                )
                            )
                        ],
                    )
                )
            ],
        )

    def test_keeps_only_most_recent_screenshots(self):
        from agent import MAX_RECENT_TURN_WITH_SCREENSHOTS

        total_turns = MAX_RECENT_TURN_WITH_SCREENSHOTS + 3
        self.agent._contents.extend(
            self._screenshot_turn() for _ in range(total_turns)
        )
        self.agent._prune_old_screenshots()

        turns = self.agent._contents[1:]  # skip the initial query turn
        with_screenshot = [
            t for t in turns if t.parts[0].function_response.parts is not None
        ]
        without = [t for t in turns if t.parts[0].function_response.parts is None]
        self.assertEqual(len(with_screenshot), MAX_RECENT_TURN_WITH_SCREENSHOTS)
        self.assertEqual(len(without), 3)
        # The retained screenshots must be the most recent turns.
        self.assertTrue(
            all(t.parts[0].function_response.parts is None for t in turns[:3])
        )

    def test_custom_function_responses_are_never_pruned(self):
        from google.genai.types import Content, FunctionResponse, Part

        turn = Content(
            role="user",
            parts=[
                Part(
                    function_response=FunctionResponse(
                        name="extract_text", response={"text": "hi"}
                    )
                )
            ],
        )
        self.agent._contents.append(turn)
        self.agent._prune_old_screenshots()
        self.assertEqual(
            self.agent._contents[-1].parts[0].function_response.response,
            {"text": "hi"},
        )


if __name__ == "__main__":
    unittest.main()
