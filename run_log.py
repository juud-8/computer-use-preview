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
# See the License for the applicable language governing permissions and
# limitations under the License.
import json
import os
from datetime import datetime
from typing import Any

LOGS_DIR = "logs"

_SENSITIVE_KEYS = frozenset({"screenshot", "data", "inline_data", "image", "png"})


def make_log_path() -> str:
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(LOGS_DIR, f"{timestamp}.jsonl")


def sanitize_for_log(value: Any) -> Any:
    if isinstance(value, bytes):
        return None
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key in _SENSITIVE_KEYS:
                continue
            sanitized = sanitize_for_log(item)
            if sanitized is not None:
                cleaned[key] = sanitized
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            sanitized = sanitize_for_log(item)
            if sanitized is not None:
                cleaned_list.append(sanitized)
        return cleaned_list
    return value


def format_short_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    parts = []
    for key, value in args.items():
        if isinstance(value, str):
            parts.append(f"{key}={value!r}")
        else:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def format_replay_line(record: dict[str, Any]) -> str:
    step_number = record["step_number"]
    action_name = record["action_name"]
    short_args = format_short_args(record.get("action_args") or {})
    reasoning = (record.get("reasoning_text") or "").replace("\n", " ").strip()
    url = record.get("resulting_url") or ""
    if short_args:
        action_part = f"{action_name}({short_args})"
    else:
        action_part = f"{action_name}()"
    return f"Step {step_number}: {action_part} — {reasoning} -> {url}"


def format_meta_line(record: dict[str, Any]) -> str:
    return (
        f"Run: query={record['query']!r} | initial_url={record['initial_url']} | "
        f"model={record['model']} | concise_mode={record['concise_mode']} | "
        f"max_steps={record['max_steps']}"
    )


class RunLogger:
    def __init__(self, path: str):
        self._path = path
        self._step_number = 0
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._file = open(path, "w", encoding="utf-8")

    def _write(self, record: dict[str, Any]) -> None:
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def write_meta(
        self,
        *,
        query: str,
        initial_url: str,
        model: str,
        concise_mode: bool,
        max_steps: int,
    ) -> None:
        self._write(
            {
                "type": "meta",
                "query": query,
                "initial_url": initial_url,
                "model": model,
                "concise_mode": concise_mode,
                "max_steps": max_steps,
            }
        )

    def write_step(
        self,
        *,
        action_name: str,
        action_args: dict[str, Any],
        reasoning_text: str | None,
        resulting_url: str | None,
    ) -> None:
        self._step_number += 1
        self._write(
            {
                "type": "step",
                "step_number": self._step_number,
                "action_name": action_name,
                "action_args": sanitize_for_log(action_args),
                "reasoning_text": reasoning_text,
                "resulting_url": resulting_url,
            }
        )

    def close(self) -> None:
        self._file.close()

    @property
    def path(self) -> str:
        return self._path


def replay_log(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    meta = next((r for r in records if r.get("type") == "meta"), None)
    if meta:
        print(format_meta_line(meta))
        print()

    for record in records:
        if record.get("type") == "step":
            print(format_replay_line(record))

    return 0
