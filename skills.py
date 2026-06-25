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
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SKILLS_FILENAME = "skills.yaml"
URL_TEMPLATE = "{url}"


@dataclass(frozen=True)
class SkillConfig:
    name: str
    query: str
    initial_url: str | None = None
    concise_mode: bool | None = None
    model: str | None = None
    description: str | None = None


def skills_path(base_dir: Path | None = None) -> Path:
    root = base_dir or Path(__file__).resolve().parent
    return root / SKILLS_FILENAME


def load_skills(path: Path | None = None) -> dict[str, dict[str, Any]]:
    skills_file = path or skills_path()
    with skills_file.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{skills_file} must contain a mapping of skill names.")
    return data


def github_to_raw_url(url: str) -> str:
    """Rewrite a github.com blob/raw URL to raw.githubusercontent.com."""
    if "raw.githubusercontent.com" in url:
        return url

    blob_match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)",
        url,
    )
    if blob_match:
        owner, repo, ref, path = blob_match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"

    raw_match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/raw/([^/]+)/(.*)",
        url,
    )
    if raw_match:
        owner, repo, ref, path = raw_match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"

    return url


def apply_url_template(value: str | None, url_arg: str | None) -> str | None:
    if value is None:
        return None
    if URL_TEMPLATE not in value:
        return value
    if url_arg is None:
        raise ValueError(
            f"Skill requires --skill-arg to fill {URL_TEMPLATE} in its configuration."
        )
    return value.replace(URL_TEMPLATE, url_arg)


def resolve_skill(
    name: str,
    skill_arg: str | None = None,
    path: Path | None = None,
) -> SkillConfig:
    skills = load_skills(path)
    if name not in skills:
        available = ", ".join(sorted(skills))
        raise KeyError(f"Unknown skill '{name}'. Available skills: {available}")

    raw = skills[name]
    if not isinstance(raw, dict):
        raise ValueError(f"Skill '{name}' must be a mapping.")

    query = raw.get("query")
    if not query:
        raise ValueError(f"Skill '{name}' is missing required field 'query'.")

    url_value = skill_arg
    if name == "repo_summary" and url_value:
        url_value = github_to_raw_url(url_value)

    initial_url = apply_url_template(raw.get("initial_url"), url_value)
    resolved_query = apply_url_template(query, url_value)
    if resolved_query is None:
        raise ValueError(f"Skill '{name}' is missing required field 'query'.")

    return SkillConfig(
        name=name,
        query=resolved_query,
        initial_url=initial_url,
        concise_mode=raw.get("concise_mode"),
        model=raw.get("model"),
        description=raw.get("description"),
    )


def format_skills_list(path: Path | None = None) -> str:
    skills = load_skills(path)
    lines: list[str] = []
    for name in sorted(skills):
        entry = skills[name]
        description = ""
        if isinstance(entry, dict):
            description = entry.get("description") or ""
        suffix = f" — {description}" if description else ""
        lines.append(f"{name}{suffix}")
    return "\n".join(lines)
