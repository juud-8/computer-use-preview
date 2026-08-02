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
"""Run configuration: env-backed defaults and CLI > skill > env resolution."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skills import SkillConfig

DEFAULT_INITIAL_URL = os.environ.get(
    "DEFAULT_INITIAL_URL", "https://www.google.com"
)
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gemini-3.5-flash")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "50"))

_TRUTHY = ("true", "1", "yes")


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in _TRUTHY


def verbose_reasoning() -> bool:
    return _env_bool("VERBOSE_REASONING", True)


def concise_mode() -> bool:
    return _env_bool("CONCISE_MODE", False)


@dataclass(frozen=True)
class RunSettings:
    """Fully resolved settings for one agent run."""

    query: str
    initial_url: str
    model: str
    concise_mode: bool
    verbose: bool
    max_steps: int


def resolve_run_settings(
    cli_query: str | None = None,
    cli_initial_url: str | None = None,
    cli_model: str | None = None,
    skill: "SkillConfig | None" = None,
) -> RunSettings:
    """Resolve run settings with precedence CLI > skill > env default.

    Raises ValueError if no query is available from either the CLI or a skill.
    """
    query = cli_query or (skill.query if skill else None)
    if not query:
        raise ValueError("A query is required (from --query or a skill).")

    initial_url = (
        cli_initial_url
        or (skill.initial_url if skill else None)
        or DEFAULT_INITIAL_URL
    )
    model = cli_model or (skill.model if skill else None) or DEFAULT_MODEL
    run_concise = (
        skill.concise_mode
        if skill is not None and skill.concise_mode is not None
        else concise_mode()
    )
    return RunSettings(
        query=query,
        initial_url=initial_url,
        model=model,
        concise_mode=run_concise,
        verbose=verbose_reasoning(),
        max_steps=MAX_STEPS,
    )
