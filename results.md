# Repo audit — `computer-use-preview` (read-only)

## 1. GIT

**`git log --oneline -10`**
```
5125dde Fix BlockReason->BlockedReason SDK compat crash in run_one_iteration
155603b Harden navigate(): sanitize URLs + catch goto failures instead of crashing
55c6446 Add config flags + MAX_STEPS runaway guard
c93bb2d Merge pull request #121 from google-gemini/new-cu-tool
60d0631 Separate legacy predefined functions in a different variable.
61be680 Apply suggestions from code review
49d6dc6 Update unit test in test_agent.py
c822360 Merge pull request #120 from patrickloeber/readme-updates
3081e0f Update README available models and default model selection to Gemini 3.5 Flash
a0b8dd1 Merge branch 'google-gemini:main' into gemini-3.5-flash-support
```

**`git status`**
- Branch: `main`, **3 commits ahead** of `origin/main`
- **Modified (uncommitted):** `results.md` only
- No staged changes

---

## 2. CONFIG (`config.py`)

| Setting | Env var | Default (if unset) |
|---------|---------|-------------------|
| `DEFAULT_INITIAL_URL` | `DEFAULT_INITIAL_URL` | `https://www.google.com` |
| `DEFAULT_MODEL` | `DEFAULT_MODEL` | `gemini-3.5-flash` |
| `MAX_STEPS` | `MAX_STEPS` | `50` |
| `verbose_reasoning()` | `VERBOSE_REASONING` | `true` |
| `concise_mode()` | `CONCISE_MODE` | `false` |

---

## 3. `.env` (non-secret values only)

| Var | Value |
|-----|-------|
| `GEMINI_API_KEY` | SET |
| `USE_VERTEXAI` | `false` |
| `VERTEXAI_PROJECT` | `your_gcp_project_id` (placeholder) |
| `VERTEXAI_LOCATION` | `us-central1` |
| `PLAYWRIGHT_HEADLESS` | `false` |
| `BROWSERBASE_API_KEY` | UNSET (placeholder string) |
| `BROWSERBASE_PROJECT_ID` | UNSET (placeholder string) |
| `CONCISE_MODE` | `true` |
| `DEFAULT_INITIAL_URL` | `https://duckduckgo.com` |
| `DEFAULT_MODEL` | *(not set — uses default `gemini-3.5-flash`)* |
| `MAX_STEPS` | *(not set — uses default `50`)* |
| `VERBOSE_REASONING` | *(not set — uses default `true`)* |

---

## 4. NEW ACTIONS

### `extract_text`
- **agent.py:** Module-level stub (`raise NotImplementedError`); registered in `custom_functions` via `from_callable`; dispatched in `handle_action` / `handle_legacy_action` → `self._browser_computer.extract_text(selector)`.
- **playwright.py:** If current URL is `github.com/.../blob/...`, rewrites to `raw.githubusercontent.com/...` and fetches via `urllib.request`; else `page.inner_text(selector)` or `page.inner_text("body")`. Truncates at 8000 chars with `\n...[truncated, N chars total]`.
- **Return type:** `dict` (`{"text": "..."}` or `{"text": "", "error": "..."}` on GitHub fetch failure)

### `save_to_file`
- **agent.py:** Full implementation; `_resolve_output_path()` confines writes under `./outputs/`; registered + dispatched like `multiply_numbers`.
- **playwright.py:** Not present (agent-level only).
- **Return type:** `dict` (`{"result": "Saved to ..."}` or `{"error": "..."}` on path traversal)

### `go_back`
- **agent.py:** Built-in Computer Use action (in `PREDEFINED_COMPUTER_USE_FUNCTIONS`); dispatched → `self._browser_computer.go_back()`.
- **playwright.py:** `page.go_back()` + `wait_for_load_state()` in try/except; logs warning on failure; always returns `current_state()`.
- **Return type:** `EnvState`

---

## 5. NAVIGATE HARDENING (`playwright.py`)

`_sanitize_url(url)` exists: `url.strip().rstrip(")],.")`.

```349:358:computers/playwright/playwright.py
    def navigate(self, url: str) -> EnvState:
        normalized_url = _sanitize_url(url)
        if not normalized_url.startswith(("http://", "https://")):
            normalized_url = "https://" + normalized_url
        try:
            self._page.goto(normalized_url)
            self._page.wait_for_load_state()
        except Exception as e:
            logging.warning("Navigate failed for %r: %s", normalized_url, e)
        return self.current_state()
```

`goto` is wrapped in try/except; on failure logs and returns `current_state()` (no raise).

---

## 6. CONCISE MODE

**`prompts.py`:** `CONCISE_SYSTEM_INSTRUCTION` (reasoning + scroll rules); `get_system_instruction(concise_mode)` returns that string if `True`, else `None`.

**`agent.py`:** In `BrowserAgent.__init__` (lines 178–197): `system_instruction = get_system_instruction(concise_mode)`; added to `config_kwargs` only when not `None`. Wired from `main.py` via `concise_mode=concise_mode()`.

When `CONCISE_MODE=false` (or unset): no `system_instruction` on `GenerateContentConfig`.

---

## 7. SAFETY BLOCK

```483:495:agent.py
        if not response.candidates:
            block_reason = (
                response.prompt_feedback.block_reason
                if response.prompt_feedback
                else None
            )
            if block_reason == types.BlockedReason.SAFETY:
                raise ValueError(
                    f"Response was blocked due to safety. Feedback: {response.prompt_feedback}"
                )
            print("Response has no candidates!")
            print(response)
            raise ValueError("Empty response")
```

**Behavior on `BlockedReason.SAFETY`:** raises `ValueError` (unhandled → traceback, process exits non-zero). Not graceful. Location: `agent.py:489-492`.

Other block reasons fall through to `"Empty response"` `ValueError` at line 495.

---

## 8. TESTS

`python -m unittest discover -v` (venv): **33 tests, 33 passed, 0 failed** (~2.4s).

Files: `test_agent.py`, `test_main.py`, `test_playwright.py`, `test_prompts.py`.

---

## 9. KNOWN ISSUE (SAFETY blocks on live runs)

Observed in recent manual runs (not unit tests):

- Queries that **name `extract_text`** or use **"read this file" / command-line** phrasing in computer-use context often get `prompt_feedback.block_reason=BlockedReason.SAFETY`. Can occur on turn 1 or later turns; not always before any action.
- **Benign-file run tried:** `main.py` blob URL with query mentioning `extract_text` — blocked on turn 1.
- **Same tooling, different query:** `"Say hello"` + computer_use + custom tools — passes (API/key OK).
- **Successful end-to-end run:** `agent.py` blob URL with query *without* naming `extract_text` (`"Summarize how the agent_loop and run_one_iteration functions work..."`) — completed (exit 0); model used scroll/screenshot rather than `extract_text`.
- Original failing query pattern (`Use extract_text to read this file... Do not search the web.`) — observed `ValueError` at `agent.py:490` via unhandled safety branch.

**Current `.env` has `CONCISE_MODE=true`.** Safety blocks were also reproduced with `CONCISE_MODE=false` in a one-off shell override during debugging.