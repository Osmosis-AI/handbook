#!/usr/bin/env python3
"""Exercise real MCP tools and verifiers in Docker with a scripted model, offline."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
import uuid
from pathlib import Path


def verify(task: Path) -> dict:
    subprocess.run(["bash", "/tests/test.sh"], check=True)
    feedback = json.loads(Path("/logs/verifier/results.json").read_text())
    reward = float(Path("/logs/verifier/reward.txt").read_text())
    assert math.isfinite(reward) and 0 <= reward <= 1
    assert reward == feedback["score"]
    assert feedback["rubrics_total"] == len(
        json.loads((task / "tests/rubrics.json").read_text())
    )
    return {
        "task": task.name,
        "rubrics": feedback["rubrics_total"],
        "noop_reward": reward,
    }


def inside(task: Path, verifier_only: bool = False) -> None:
    config = tomllib.loads((task / "task.toml").read_text())
    os.environ.update(config["environment"]["env"])
    for source, destination in (
        ("initial_external_services", "/data"),
        ("initial_external_services", "/initial_data"),
        ("initial_workspace", "/workdir"),
    ):
        shutil.copytree(task / "environment" / source, destination, dirs_exist_ok=True)
    shutil.copytree(
        task / "environment/initial_workspace", "/environment/initial_workspace"
    )
    shutil.copytree(
        task / "environment/initial_external_services",
        "/environment/initial_external_services",
    )
    shutil.copytree(task / "tests", "/tests")
    if verifier_only:
        print(json.dumps(verify(task)))
        return
    Path("/logs/agent").mkdir(parents=True)
    with Path("/logs/agent/mcp-proxy.log").open("w") as log:
        proxy = subprocess.Popen(
            ["/app/scripts/start.sh", "--method", "http", "--port", "8000"],
            stdout=log,
            stderr=log,
        )
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=2):
                    break
            except OSError:
                if proxy.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(
                        Path("/logs/agent/mcp-proxy.log").read_text()[-4000:]
                    )
                time.sleep(0.25)

        import openhands.sdk.llm.llm as llm_module
        from litellm.types.utils import ModelResponse

        sys.path.insert(0, "/app/openhands-runner")
        import openhands_runner

        calls = 0

        def completion(**kwargs):
            nonlocal calls
            calls += 1
            assert calls <= 2, "Agent failed to stop at finish"
            if calls == 1:
                names = [tool["function"]["name"] for tool in kwargs["tools"]]
                assert any("slack" in name.lower() for name in names)
                assert any("google_mail" in name.lower() for name in names)
                name = next(name for name in names if name.endswith("listFiles"))
                arguments = {"directory": "/workdir"}
            else:
                name, arguments = (
                    "finish",
                    {"message": "Offline runtime smoke completed"},
                )
            return ModelResponse(
                id="chatcmpl-" + uuid.uuid4().hex,
                created=0,
                model="gpt-4o",
                object="chat.completion",
                choices=[
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_" + uuid.uuid4().hex,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(arguments),
                                    },
                                }
                            ],
                        },
                    }
                ],
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )

        llm_module.litellm_completion = completion
        os.environ["OPENAI_API_KEY"] = "offline-smoke-not-a-credential"
        result = openhands_runner.run(
            {
                "model": "openai/gpt-4o",
                "mcpUrl": "http://localhost:8000/mcp",
                "systemPrompt": (task / "system_prompt.md").read_text(),
                "instruction": (task / "instruction.md").read_text(),
                "maxToolCalls": 200,
                "logDir": "/logs/agent",
            }
        )
        assert result["stopped_reason"] == "end_turn", result
        assert result["n_tool_calls"] == calls == 2, result
        from openhands.sdk.event import Event
        from openhands.sdk.event.base import LLMConvertibleEvent

        events = [
            Event.model_validate_json(path.read_text())
            for path in sorted(
                Path(openhands_runner.STATE_DIR).glob("*/events/event-*.json")
            )
        ]
        assert events, "The official SDK must persist the conversation"
        observations = [
            event.to_llm_message().model_dump(mode="json")
            for event in events
            if isinstance(event, LLMConvertibleEvent)
            and event.to_llm_message().role == "tool"
        ]
        expected = next((task / "environment/initial_workspace").iterdir()).name
        assert expected in json.dumps(observations), (expected, observations)
        listing = next(
            message for message in observations if message["name"].endswith("listFiles")
        )
        payload = next(
            json.loads(block["text"])
            for block in listing["content"]
            if block.get("text", "").startswith("{")
        )
        assert payload["returncode"] == 0, payload

        print(json.dumps({**verify(task), "tool_calls": calls}))
    finally:
        proxy.terminate()
        proxy.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--inside", type=Path)
    parser.add_argument(
        "--all-verifiers",
        action="store_true",
        help="Run all 65 task verifier wrappers, without an agent",
    )
    args = parser.parse_args()
    if args.inside:
        inside(args.inside, verifier_only=args.all_verifiers)
        return
    if not args.image or not args.dataset:
        parser.error("--image and --dataset are required")
    tasks = sorted((args.dataset / "tasks").iterdir())
    if not args.all_verifiers:
        tasks = [
            next(task for task in tasks if task.name.startswith(domain + "_"))
            for domain in ("finance", "hr", "insurance", "logistics", "medical")
        ]
    for task in tasks:
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                f"{args.dataset.resolve()}:/dataset:ro",
                "-v",
                f"{Path(__file__).resolve()}:/smoke.py:ro",
                args.image,
                "/app/openhands-runner/.venv/bin/python",
                "/smoke.py",
                "--inside",
                f"/dataset/tasks/{task.name}",
                *(["--all-verifiers"] if args.all_verifiers else []),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
        if completed.returncode:
            raise RuntimeError(completed.stdout[-12000:])
        print(completed.stdout.strip().splitlines()[-1], flush=True)


if __name__ == "__main__":
    main()
