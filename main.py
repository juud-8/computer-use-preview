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
import argparse
import sys

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from config import resolve_run_settings
from agent import BrowserAgent
from computers import BrowserbaseComputer, PlaywrightComputer
from run_log import RunLogger, make_log_path, replay_log
from skills import format_skills_list, resolve_skill, skills_path


PLAYWRIGHT_SCREEN_SIZE = (1440, 900)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the browser agent with a query.")
    parser.add_argument(
        "--query",
        type=str,
        required=False,
        help="The query for the browser agent to execute.",
    )
    parser.add_argument(
        "--replay",
        type=str,
        metavar="LOGFILE",
        help="Print a step summary from a JSONL log file (no browser or model).",
    )

    parser.add_argument(
        "--env",
        type=str,
        choices=("playwright", "browserbase"),
        default="playwright",
        help="The computer use environment to use.",
    )
    parser.add_argument(
        "--initial_url",
        type=str,
        default=argparse.SUPPRESS,
        help="The inital URL loaded for the computer.",
    )
    parser.add_argument(
        "--highlight_mouse",
        action="store_true",
        default=False,
        help="If possible, highlight the location of the mouse.",
    )
    parser.add_argument(
        "--model",
        default=argparse.SUPPRESS,
        help="Set which main model to use.",
    )
    parser.add_argument(
        "--skill",
        type=str,
        help="Named run template from skills.yaml.",
    )
    parser.add_argument(
        "--skill-arg",
        type=str,
        dest="skill_arg",
        help="Value for the {url} template variable in the selected skill.",
    )
    parser.add_argument(
        "--list-skills",
        action="store_true",
        help="List available skills from skills.yaml and exit.",
    )
    args = parser.parse_args()

    if args.list_skills:
        print(format_skills_list(skills_path()))
        return 0

    if args.replay:
        if hasattr(args, "query") and args.query:
            print("Note: --replay takes precedence; ignoring --query.")
        return replay_log(args.replay)

    skill_config = None
    if args.skill:
        try:
            skill_config = resolve_skill(
                args.skill,
                skill_arg=args.skill_arg,
                path=skills_path(),
            )
        except KeyError as exc:
            print(exc, file=sys.stderr)
            return 1
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    try:
        settings = resolve_run_settings(
            cli_query=getattr(args, "query", None),
            cli_initial_url=getattr(args, "initial_url", None),
            cli_model=getattr(args, "model", None),
            skill=skill_config,
        )
    except ValueError:
        parser.error("--query is required unless --replay or --skill is used.")

    log_path = make_log_path()
    run_logger = RunLogger(log_path)
    run_logger.write_meta(
        query=settings.query,
        initial_url=settings.initial_url,
        model=settings.model,
        concise_mode=settings.concise_mode,
        max_steps=settings.max_steps,
    )

    if args.env == "playwright":
        env = PlaywrightComputer(
            screen_size=PLAYWRIGHT_SCREEN_SIZE,
            initial_url=settings.initial_url,
            highlight_mouse=args.highlight_mouse,
        )
    elif args.env == "browserbase":
        env = BrowserbaseComputer(
            screen_size=PLAYWRIGHT_SCREEN_SIZE,
            initial_url=settings.initial_url
        )
    else:
        raise ValueError("Unknown environment: ", args.env)

    with env as browser_computer:
        agent = BrowserAgent(
            browser_computer=browser_computer,
            query=settings.query,
            model_name=settings.model,
            verbose=settings.verbose,
            concise_mode=settings.concise_mode,
            run_logger=run_logger,
        )
        agent.agent_loop(max_steps=settings.max_steps)
    return 0


if __name__ == "__main__":
    main()
