# CHANGES — local divergence from upstream

This document records the changes made to this fork of `computer-use-preview`
on top of the upstream Google course repo. It exists so that a future reader
(or a cold return to this repo) can see at a glance what was added, why, and
how to use it.

**Test suite:** 13 tests (upstream) → **54 tests**, all passing.

---

## Why these changes exist

The upstream repo is a working but fragile demonstration of a Gemini
computer-use agent. In practice it had three rough edges: it ran the model
with **no system instruction** (so reasoning was unconstrained and verbose),
it **crashed on malformed input** instead of recovering, and it shipped with
**two latent bugs** that only surface on certain code paths. It also lacked a
text-extraction tool, so reading any long page meant slow, lossy
scroll-by-screenshot — which caused the agent to thrash or wander off-task.

The changes below fix those problems and add a small amount of personalization
(config, skills, logging) so the agent is faster, more reliable, and reusable.

---

## New capabilities

### Configuration system (`config.py`, `.env`)
Centralized, env-backed settings with sane defaults so common options don't
have to be retyped on every run:

| Setting | Env var | Default |
|---|---|---|
| Default start page | `DEFAULT_INITIAL_URL` | `https://duckduckgo.com`* |
| Default model | `DEFAULT_MODEL` | `gemini-3.5-flash` |
| Step cap (runaway guard) | `MAX_STEPS` | `50` |
| Verbose reasoning table | `VERBOSE_REASONING` | `true` |
| Concise mode | `CONCISE_MODE` | `false` |

\* Default was moved off `google.com`, which reliably triggers a CAPTCHA and
can send the agent into off-task web-wandering.

`MAX_STEPS` is a runaway guard: the agent loop exits gracefully when the cap is
hit, instead of looping indefinitely. CLI flags always override env defaults.

### Concise mode (`prompts.py`)
The upstream repo set **no system instruction at all**. Concise mode adds one
— but because computer-use models do **not** reliably honor
`system_instruction` on `GenerateContentConfig`, the instruction is **injected
into the first user turn** instead. It constrains the agent to one short
sentence of reasoning per step and tells it not to re-scroll to re-verify
content it has already read. `get_text()` was also fixed to skip `thought`
parts, so the reasoning column no longer leaks the model's internal
chain-of-thought.

### New actions
| Action | Returns | What it does |
|---|---|---|
| `extract_text(selector?)` | `dict` | Reads page text via DOM in one call instead of scroll-screenshotting. Rewrites `github.com/.../blob/...` URLs to `raw.githubusercontent.com` so code files read cleanly. Truncates at 50,000 chars. |
| `save_to_file(path, content)` | `dict` | Persists results under `./outputs/`, with path-traversal protection. |
| `go_back()` | `EnvState` | Browser back-navigation, crash-wrapped. |

`extract_text` is the highest-value addition: it turns an 18-step
scroll-and-thrash code read into a clean **2-step** read, and it stops the
agent from wandering to the open web to answer questions it could answer from
the page in front of it.

### Run logging + replay (`run_log.py`)
Every run writes a JSONL log to `./logs/YYYYMMDD-HHMMSS.jsonl`: one **meta**
line (query, initial_url, model, concise_mode, max_steps) followed by one
**step** line per function call (action, args, reasoning, resulting URL).
Screenshot bytes and sensitive keys are stripped, so logs stay small and safe.
The logger is closed in a `finally` block, so even failed runs leave a trace.

`--replay <logfile>` prints a human-readable summary of a past run without
launching a browser or calling the model.

### Skills registry (`skills.yaml`, `skills.py`)
Reusable named task templates, so common runs become one-word commands instead
of retyped queries. Skills support a single `{url}` variable filled by
`--skill-arg`. Explicit CLI flags override skill values. Seed skills:

- `repo_summary` — summarize a GitHub file (auto-rewrites to raw URL, concise)
- `competitor_scan` — list top Product Hunt launches
- `price_check` — extract price + availability from a product page

---

## Bug fixes (latent in upstream)

1. **Malformed-URL crash** — `navigate()` called `page.goto()` with no error
   handling, so a malformed URL from the model (e.g. a trailing paren) crashed
   the whole agent. Now `_sanitize_url()` strips trailing junk and `goto` is
   wrapped in try/except: on failure it logs and returns the unchanged page so
   the model can self-correct.

2. **SDK incompatibility** — `run_one_iteration` referenced
   `types.BlockReason`, which does not exist in `google-genai` 2.8.0 (the enum
   is named `BlockedReason`). This crashed with `AttributeError` whenever the
   safety-feedback branch was reached. Fixed, with a defensive `None`-guard on
   `prompt_feedback`.

3. **Vertex/API-key conflict** (from initial setup) — a placeholder
   `VERTEXAI_PROJECT` was passed alongside the API key, crashing the client.
   Now uses API-key mode when `USE_VERTEXAI=false`.

4. **Headless-mode bug** (from initial setup) — `PLAYWRIGHT_HEADLESS=false` was
   treated as headless because any non-empty string is truthy. Now only runs
   headless when the value is `true`, `1`, or `yes`.

---

## Robustness handling

| Failure | Before | After |
|---|---|---|
| `BlockedReason.SAFETY` | Unhandled `ValueError` traceback | Clean message, loop exits |
| 401 / 403 (auth/billing) | 5 retries (~15s wasted) | Fail fast with a clear message |
| 5xx / 429 / timeouts | Retried | Still retried (correct) |

The key distinction: fail fast on errors that can never succeed on retry (auth,
billing, permission), keep retrying genuinely transient ones.

---

## Quick reference

```bash
# Run a task
python main.py --query "..."

# Start on a specific page (faster, fewer tokens)
python main.py --initial_url "https://example.com" --query "..."

# Use a skill
python main.py --list-skills
python main.py --skill repo_summary \
  --skill-arg "https://github.com/juud-8/computer-use-preview/blob/main/agent.py"

# Replay a past run
python main.py --replay logs/<timestamp>.jsonl

# Concise mode (set in .env)
CONCISE_MODE=true
```

---

## Known rough edges (non-blocking)

- The Gemini safety filter occasionally returns a false-positive `SAFETY` block
  on benign code-reading queries. It is intermittent and usually clears on a
  rerun. Handled gracefully (clean exit, meta-only log) rather than crashing.
- Concise mode is delivered via injected user message because computer-use
  models ignore `system_instruction`; if a future SDK changes this, revisit
  `prompts.py`.

---

## Architecture pass (2026-07-06)

**Test suite: 54 → 93 tests, all passing.**

### Mode/settings consolidation
- `config.py` now owns run-configuration end to end: a frozen `RunSettings`
  dataclass plus `resolve_run_settings()` encoding the CLI > skill > env
  precedence in one tested function. `main.py`'s `hasattr`-based resolution
  logic was deleted in favor of it. Boolean env parsing is deduplicated into
  `_env_bool`.

### Agent refactor (`agent.py`)
- The two ~100-line duplicated `elif` action-dispatch chains (modern + legacy)
  were replaced by a table-driven dispatch (`_build_action_handlers`), with a
  shared handler set for actions common to both model generations and the
  custom functions. `handle_legacy_action` is now a thin delegate.
- Fixed a broken f-string in `_get_safety_confirmation` (the error message
  printed the literal text `safety['decision']` instead of the value).
- Removed the leftover `[debug] concise_mode=...` startup print.
- Screenshot pruning extracted to `_prune_old_screenshots` using a precomputed
  `SCREENSHOT_FUNCTION_NAMES` frozenset (previously the two function lists were
  concatenated on every part of every turn, every iteration).
- Verbose/non-verbose duplication around console status spinners collapsed
  into a `_status()` helper (nullcontext when not verbose).

### GitHub URL rewriting consolidated (`urls.py`)
- There were two divergent implementations (regex in `skills.py`, urlparse in
  `computers/playwright/playwright.py` — the latter didn't handle `/raw/`
  URLs). Both now delegate to a single `urls.github_to_raw_url`.
- The hardcoded `if name == "repo_summary"` special case in `skills.py` is
  replaced by a declarative `normalize_github_url: true` flag in `skills.yaml`,
  so any skill can opt in.

### New tests
- `test_config.py`: env-bool parsing, full RunSettings precedence matrix
  (CLI over skill, skill over env, skill `concise_mode: false` beating env
  true, frozen dataclass).
- `test_urls.py`: blob/raw/www forms, idempotency, non-GitHub passthrough.
- `test_agent.py`: dispatch-table completeness against both predefined
  function lists (a new predefined action without a handler now fails CI),
  modern-action handlers (click/type/scroll/wait/hotkey/drag), legacy
  key_combination splitting, safety confirmation yes/no/unknown-decision,
  and screenshot pruning (keeps only the N most recent, never touches custom
  function responses).
- `test_skills.py`: non-flagged skills keep URLs verbatim; `{url}` template
  without `--skill-arg` raises.
