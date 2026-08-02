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
from typing import Literal, Optional, Union, Any
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
import termcolor
from google.genai.types import (
    Part,
    GenerateContentConfig,
    Content,
    Candidate,
    FunctionResponse,
    FinishReason,
)
import time
from contextlib import nullcontext
from rich.console import Console
from rich.table import Table

from computers import EnvState, Computer
from prompts import build_initial_user_message
from run_log import RunLogger

MAX_RECENT_TURN_WITH_SCREENSHOTS = 3
LEGACY_COMPUTER_USE_MODELS = [
    "gemini-2.5-computer-use-preview-10-2025",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
]

# Legacy predefined functions, which are used in gemini-2.5-computer-use-preview-10-2025, gemini-3-flash-preview and gemini-3.1-pro-preview.
LEGACY_PREDEFINED_COMPUTER_USE_FUNCTIONS = [
    "open_web_browser",
    "click_at",
    "hover_at",
    "type_text_at",
    "scroll_document",
    "scroll_at",
    "wait_5_seconds",
    "go_back",
    "go_forward",
    "search",
    "navigate",
    "key_combination",
    "drag_and_drop",
]

# Predefined functions which are used in gemini-3.5-flash and future models.
PREDEFINED_COMPUTER_USE_FUNCTIONS = [
    "click",
    "double_click",
    "triple_click",
    "middle_click",
    "right_click",
    "mouse_down",
    "mouse_up",
    "move",
    "type",
    "drag_and_drop",
    "wait",
    "press_key",
    "key_down",
    "key_up",
    "hotkey",
    "take_screenshot",
    "scroll",
    "go_back",
    "navigate",
    "go_forward",
]

# Any predefined computer-use function returns an EnvState with a screenshot.
SCREENSHOT_FUNCTION_NAMES = frozenset(
    PREDEFINED_COMPUTER_USE_FUNCTIONS + LEGACY_PREDEFINED_COMPUTER_USE_FUNCTIONS
)


console = Console()

SAFETY_BLOCK_MESSAGE = (
    "The model declined this request (safety filter). "
    "Try rephrasing the query or a different page."
)
AUTH_BILLING_ERROR_MESSAGE = (
    "API auth/billing error — check your GEMINI_API_KEY and Google AI billing status"
)


def _is_non_retryable_auth_error(exc: Exception) -> bool:
    return isinstance(exc, genai_errors.ClientError) and exc.code in (401, 403)


# Built-in Computer Use tools will return "EnvState".
# Custom provided functions will return "dict".
FunctionResponseT = Union[EnvState, dict]


def multiply_numbers(x: float, y: float) -> dict:
    """Multiplies two numbers."""
    return {"result": x * y}


OUTPUTS_DIR = "outputs"


def extract_text(selector: str | None = None) -> dict:
    """Return visible text from the current page, optionally scoped to a CSS selector."""
    raise NotImplementedError("Routed through BrowserAgent to the browser computer.")


def _resolve_output_path(path: str) -> str:
    base = os.path.abspath(OUTPUTS_DIR)
    os.makedirs(base, exist_ok=True)
    resolved = os.path.abspath(os.path.join(base, path))
    if resolved != base and not resolved.startswith(base + os.sep):
        raise ValueError(f"Path escapes ./{OUTPUTS_DIR}/: {path!r}")
    return resolved


def save_to_file(path: str, content: str) -> dict:
    """Write content to a file under ./outputs/ and return the saved path."""
    try:
        resolved = _resolve_output_path(path)
    except ValueError as e:
        return {"error": str(e)}
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(resolved, "w", encoding="utf-8") as f:
        f.write(content)
    return {"result": f"Saved to {resolved}"}


class BrowserAgent:
    def __init__(
        self,
        browser_computer: Computer,
        query: str,
        model_name: str,
        verbose: bool = True,
        concise_mode: bool = False,
        run_logger: RunLogger | None = None,
    ):
        self._browser_computer = browser_computer
        self._query = query
        self._model_name = model_name
        self._verbose = verbose
        self._run_logger = run_logger
        self.final_reasoning = None
        use_vertexai = os.environ.get("USE_VERTEXAI", "0").lower() in ["true", "1"]
        if use_vertexai:
            self._client = genai.Client(
                vertexai=True,
                project=os.environ.get("VERTEXAI_PROJECT"),
                location=os.environ.get("VERTEXAI_LOCATION"),
            )
        else:
            self._client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self._contents: list[Content] = [
            Content(
                role="user",
                parts=[
                    Part(text=build_initial_user_message(self._query, concise_mode)),
                ],
            )
        ]
        self._use_legacy_computer_use_function_call = (
            model_name in LEGACY_COMPUTER_USE_MODELS
        )

        # Exclude any predefined functions here.
        excluded_predefined_functions = []

        # Add your own custom functions here.
        custom_functions = [
            # For example:
            types.FunctionDeclaration.from_callable(
                client=self._client, callable=multiply_numbers
            ),
            types.FunctionDeclaration.from_callable(
                client=self._client, callable=extract_text
            ),
            types.FunctionDeclaration.from_callable(
                client=self._client, callable=save_to_file
            ),
        ]

        config_kwargs = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "tools": [
                types.Tool(
                    computer_use=types.ComputerUse(
                        environment=types.Environment.ENVIRONMENT_BROWSER,
                        excluded_predefined_functions=excluded_predefined_functions,
                    ),
                ),
                types.Tool(function_declarations=custom_functions),
            ],
            # Concise mode skips thought parts in the response to cut token cost.
            "thinking_config": types.ThinkingConfig(
                include_thoughts=not concise_mode
            ),
        }
        self._generate_content_config = GenerateContentConfig(**config_kwargs)

    def _status(self, message: str):
        """Console spinner in verbose mode, no-op otherwise."""
        if self._verbose:
            return console.status(message, spinner_style=None)
        return nullcontext()

    def _denormalize_point(self, args: dict) -> tuple[int, int]:
        return self.denormalize_x(args["x"]), self.denormalize_y(args["y"])

    def _point_handler(self, method_name: str):
        """Handler for actions that take a normalized (x, y) point."""

        def handler(args: dict) -> FunctionResponseT:
            x, y = self._denormalize_point(args)
            return getattr(self._browser_computer, method_name)(x=x, y=y)

        return handler

    def _handle_scroll_at(self, args: dict) -> FunctionResponseT:
        x, y = self._denormalize_point(args)
        magnitude = args.get("magnitude", 800)
        direction = args["direction"]
        if direction in ("up", "down"):
            magnitude = self.denormalize_y(magnitude)
        elif direction in ("left", "right"):
            magnitude = self.denormalize_x(magnitude)
        else:
            raise ValueError("Unknown direction: ", direction)
        return self._browser_computer.scroll_at(
            x=x, y=y, direction=direction, magnitude=magnitude
        )

    def _handle_drag_and_drop(self, args: dict) -> FunctionResponseT:
        x, y = self._denormalize_point(args)
        return self._browser_computer.drag_and_drop(
            x=x,
            y=y,
            destination_x=self.denormalize_x(args["destination_x"]),
            destination_y=self.denormalize_y(args["destination_y"]),
        )

    def _handle_type_text_at(self, args: dict) -> FunctionResponseT:
        x, y = self._denormalize_point(args)
        return self._browser_computer.type_text_at(
            x=x,
            y=y,
            text=args["text"],
            press_enter=args.get("press_enter", False),
            clear_before_typing=args.get("clear_before_typing", True),
        )

    def _build_action_handlers(self, legacy: bool) -> dict:
        """Build the action-name -> handler dispatch table."""
        bc = self._browser_computer
        # Shared across both model generations, plus the custom functions.
        handlers = {
            "open_web_browser": lambda args: bc.open_web_browser(),
            "go_back": lambda args: bc.go_back(),
            "go_forward": lambda args: bc.go_forward(),
            "navigate": lambda args: bc.navigate(args["url"]),
            "drag_and_drop": self._handle_drag_and_drop,
            multiply_numbers.__name__: lambda args: multiply_numbers(
                x=args["x"], y=args["y"]
            ),
            extract_text.__name__: lambda args: bc.extract_text(
                args.get("selector")
            ),
            save_to_file.__name__: lambda args: save_to_file(
                path=args["path"], content=args["content"]
            ),
        }
        if legacy:
            handlers.update(
                {
                    "click_at": self._point_handler("click_at"),
                    "hover_at": self._point_handler("hover_at"),
                    "type_text_at": self._handle_type_text_at,
                    "scroll_document": lambda args: bc.scroll_document(
                        args["direction"]
                    ),
                    "scroll_at": self._handle_scroll_at,
                    "wait_5_seconds": lambda args: bc.wait_5_seconds(),
                    "search": lambda args: bc.search(),
                    "key_combination": lambda args: bc.key_combination(
                        args["keys"].split("+")
                    ),
                }
            )
        else:
            handlers.update(
                {
                    "click": self._point_handler("click_at"),
                    "double_click": self._point_handler("double_click_at"),
                    "triple_click": self._point_handler("triple_click_at"),
                    "middle_click": self._point_handler("middle_click_at"),
                    "right_click": self._point_handler("right_click_at"),
                    "mouse_down": self._point_handler("mouse_down"),
                    "mouse_up": self._point_handler("mouse_up"),
                    "move": self._point_handler("hover_at"),
                    "type": lambda args: bc.type_text(
                        text=args["text"],
                        press_enter=args.get("press_enter", False),
                    ),
                    "scroll": self._handle_scroll_at,
                    "wait": lambda args: bc.wait(int(args.get("seconds", 1))),
                    "hotkey": lambda args: bc.key_combination(args["keys"]),
                    "press_key": lambda args: bc.press_key(args["key"]),
                    "key_down": lambda args: bc.key_down(args["key"]),
                    "key_up": lambda args: bc.key_up(args["key"]),
                    "take_screenshot": lambda args: bc.take_screenshot(),
                }
            )
        return handlers

    def handle_action(
        self, action: types.FunctionCall, use_legacy_actions: bool
    ) -> FunctionResponseT:
        """Handles the action and returns the environment state."""
        handlers = self._build_action_handlers(legacy=use_legacy_actions)
        handler = handlers.get(action.name)
        if handler is None:
            raise ValueError(f"Unsupported function: {action}")
        return handler(action.args or {})

    def handle_legacy_action(self, action: types.FunctionCall) -> FunctionResponseT:
        """Handles the action defined in the legacy models, and returns the environment state."""
        return self.handle_action(action, use_legacy_actions=True)

    def get_model_response(
        self, max_retries=5, base_delay_s=1
    ) -> types.GenerateContentResponse:
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=self._contents,
                    config=self._generate_content_config,
                )
                return response  # Return response on success
            except Exception as e:
                if _is_non_retryable_auth_error(e):
                    termcolor.cprint(
                        AUTH_BILLING_ERROR_MESSAGE, color="red", attrs=["bold"]
                    )
                    raise
                print(e)
                if attempt < max_retries - 1:
                    delay = base_delay_s * (2**attempt)
                    message = (
                        f"Generating content failed on attempt {attempt + 1}. "
                        f"Retrying in {delay} seconds...\n"
                    )
                    termcolor.cprint(
                        message,
                        color="yellow",
                    )
                    time.sleep(delay)
                else:
                    termcolor.cprint(
                        f"Generating content failed after {max_retries} attempts.\n",
                        color="red",
                    )
                    raise

    def get_text(self, candidate: Candidate) -> Optional[str]:
        """Extracts the text from the candidate."""
        if not candidate.content or not candidate.content.parts:
            return None
        text = []
        for part in candidate.content.parts:
            if part.text and not part.thought:
                text.append(part.text)
        return " ".join(text) or None

    def extract_function_calls(self, candidate: Candidate) -> list[types.FunctionCall]:
        """Extracts the function call from the candidate."""
        if not candidate.content or not candidate.content.parts:
            return []
        ret = []
        for part in candidate.content.parts:
            if part.function_call:
                ret.append(part.function_call)
        return ret

    def run_one_iteration(self) -> Literal["COMPLETE", "CONTINUE"]:
        # Generate a response from the model.
        with self._status("Generating response from Gemini Computer Use..."):
            try:
                response = self.get_model_response()
            except Exception:
                return "COMPLETE"

        if not response.candidates:
            block_reason = (
                response.prompt_feedback.block_reason
                if response.prompt_feedback
                else None
            )
            if block_reason == types.BlockedReason.SAFETY:
                termcolor.cprint(
                    SAFETY_BLOCK_MESSAGE, color="yellow", attrs=["bold"]
                )
                return "COMPLETE"
            print("Response has no candidates!")
            print(response)
            raise ValueError("Empty response")

        # Extract the text and function call from the response.
        candidate = response.candidates[0]
        # Append the model turn to conversation history.
        if candidate.content:
            self._contents.append(candidate.content)

        reasoning = self.get_text(candidate)
        function_calls = self.extract_function_calls(candidate)

        # Retry the request in case of malformed FCs.
        if (
            not function_calls
            and not reasoning
            and candidate.finish_reason == FinishReason.MALFORMED_FUNCTION_CALL
        ):
            return "CONTINUE"

        if not function_calls:
            print(f"Agent Loop Complete: {reasoning}")
            self.final_reasoning = reasoning
            return "COMPLETE"

        function_call_strs = []
        for function_call in function_calls:
            # Print the function call and any reasoning.
            function_call_str = f"Name: {function_call.name}"
            if function_call.args:
                function_call_str += f"\nArgs:"
                for key, value in function_call.args.items():
                    function_call_str += f"\n  {key}: {value}"
            function_call_strs.append(function_call_str)

        table = Table(expand=True)
        table.add_column(
            "Gemini Computer Use Reasoning", header_style="magenta", ratio=1
        )
        table.add_column("Function Call(s)", header_style="cyan", ratio=1)
        table.add_row(reasoning, "\n".join(function_call_strs))
        if self._verbose:
            console.print(table)
            print()

        function_responses = []
        for function_call in function_calls:
            extra_fr_fields = {}
            if function_call.args and (
                safety := function_call.args.get("safety_decision")
            ):
                decision = self._get_safety_confirmation(safety)
                if decision == "TERMINATE":
                    print("Terminating agent loop")
                    return "COMPLETE"
                # Explicitly mark the safety check as acknowledged.
                extra_fr_fields["safety_acknowledgement"] = "true"
            with self._status("Sending command to Computer..."):
                fc_result = self.handle_action(
                    function_call, self._use_legacy_computer_use_function_call
                )
            if isinstance(fc_result, EnvState):
                function_responses.append(
                    FunctionResponse(
                        name=function_call.name,
                        response={
                            "url": fc_result.url,
                            **extra_fr_fields,
                        },
                        parts=[
                            types.FunctionResponsePart(
                                inline_data=types.FunctionResponseBlob(
                                    mime_type="image/png", data=fc_result.screenshot
                                )
                            )
                        ],
                    )
                )
            elif isinstance(fc_result, dict):
                function_responses.append(
                    FunctionResponse(name=function_call.name, response=fc_result)
                )

            if self._run_logger:
                resulting_url = (
                    fc_result.url if isinstance(fc_result, EnvState) else None
                )
                self._run_logger.write_step(
                    action_name=function_call.name,
                    action_args=dict(function_call.args or {}),
                    reasoning_text=reasoning,
                    resulting_url=resulting_url,
                )

        self._contents.append(
            Content(
                role="user",
                parts=[Part(function_response=fr) for fr in function_responses],
            )
        )

        self._prune_old_screenshots()

        return "CONTINUE"

    @staticmethod
    def _screenshot_parts(content: Content) -> list[Part]:
        """Parts of a user turn that carry a computer-use screenshot."""
        if content.role != "user" or not content.parts:
            return []
        return [
            part
            for part in content.parts
            if part.function_response
            and part.function_response.parts
            and part.function_response.name in SCREENSHOT_FUNCTION_NAMES
        ]

    def _prune_old_screenshots(self) -> None:
        """Keep screenshots only in the most recent turns to bound context size."""
        turns_with_screenshots = 0
        for content in reversed(self._contents):
            parts = self._screenshot_parts(content)
            if not parts:
                continue
            turns_with_screenshots += 1
            if turns_with_screenshots > MAX_RECENT_TURN_WITH_SCREENSHOTS:
                for part in parts:
                    part.function_response.parts = None

    def _get_safety_confirmation(
        self, safety: dict[str, Any]
    ) -> Literal["CONTINUE", "TERMINATE"]:
        if safety["decision"] != "require_confirmation":
            raise ValueError(f"Unknown safety decision: {safety['decision']}")
        termcolor.cprint(
            "Safety service requires explicit confirmation!",
            color="yellow",
            attrs=["bold"],
        )
        print(safety["explanation"])
        decision = ""
        while decision.lower() not in ("y", "n", "ye", "yes", "no"):
            decision = input("Do you wish to proceed? [Yes]/[No]\n")
        if decision.lower() in ("n", "no"):
            return "TERMINATE"
        return "CONTINUE"

    def agent_loop(self, max_steps: int | None = None):
        try:
            status = "CONTINUE"
            step = 0
            while status == "CONTINUE":
                if max_steps is not None and step >= max_steps:
                    termcolor.cprint(
                        f"Agent loop stopped: reached MAX_STEPS limit ({max_steps}).",
                        color="yellow",
                        attrs=["bold"],
                    )
                    return
                status = self.run_one_iteration()
                step += 1
        finally:
            if self._run_logger:
                self._run_logger.close()

    def denormalize_x(self, x: int) -> int:
        return int(x / 1000 * self._browser_computer.screen_size()[0])

    def denormalize_y(self, y: int) -> int:
        return int(y / 1000 * self._browser_computer.screen_size()[1])
