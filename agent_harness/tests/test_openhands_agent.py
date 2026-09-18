"""The host side of the agent: which --ak kwargs survive the trip to the container.

A key missing from FORWARDED_LLM_KWARGS is not an error. BaseAgent takes **kwargs and ignores
what it does not recognize, so the value disappears between registry.json and the LLM with
nothing logged, and the run still looks valid.
"""
import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import agent_harness.openhands_agent as mod
from agent_harness.openhands_agent import (
    FORWARDED_LLM_KWARGS,
    OpenHandsAgent,
    _forwarded_env,
    _proxy_launch_command,
)


def _agent(tmp_path, **kwargs):
    return OpenHandsAgent(logs_dir=tmp_path, model_name="openai/thinkingmachines/inkling-small",
                          **kwargs)


def test_max_tokens_reaches_the_llm_kwargs(tmp_path):
    # Without this the endpoint default of 4096 applies and every long turn is truncated.
    assert "max_tokens" in FORWARDED_LLM_KWARGS
    assert _agent(tmp_path, max_tokens=250000).llm_kwargs == {"max_tokens": 250000}


def test_a_harbor_string_becomes_an_int(tmp_path):
    # harbor renders --ak values as strings, so the registry's 250000 arrives as "250000".
    # A string cap is not a cap the LLM constructor can use.
    kwargs = _agent(tmp_path, max_tokens="250000").llm_kwargs
    assert kwargs == {"max_tokens": 250000} and isinstance(kwargs["max_tokens"], int)


def test_an_unforwarded_kwarg_is_still_dropped(tmp_path):
    # The allowlist is the contract; this test fails loudly if a key is added without a reason.
    agent = _agent(tmp_path, temperature=0.7)
    assert "temperature" not in agent.llm_kwargs


def test_invoice_line_item_reaches_the_task_container(monkeypatch):
    ili = "00000000-0000-4000-8000-000000000003"
    monkeypatch.setenv("SURGE_INVOICE_LINE_ITEM_ID", ili)
    assert _forwarded_env()["SURGE_INVOICE_LINE_ITEM_ID"] == ili


def test_a_malformed_cap_fails_before_the_run(tmp_path):
    # Loud beats silent: a bad registry value stops trial setup instead of quietly reverting
    # to the endpoint default, which is the failure this allowlist entry exists to prevent.
    with pytest.raises(ValueError):
        _agent(tmp_path, max_tokens="lots")


class _WedgedLaunchEnv:
    """Daytona-like transport: the detached proxy launch never reports an exit code."""

    def __init__(self):
        self.launched = False
        self.commands = []

    async def exec(self, command, timeout_sec=None, **_):
        self.commands.append(command)
        if "nohup" in command:
            assert command == _proxy_launch_command()
            self.launched = True
            await asyncio.Event().wait()  # never returns
        if "curl" in command:
            return SimpleNamespace(return_code=0 if self.launched else 1, stdout="", stderr="")
        return SimpleNamespace(return_code=0, stdout="", stderr="")


def test_setup_survives_a_wedged_proxy_launch_exec(tmp_path, monkeypatch):
    # Seen on Daytona: the proxy comes up but the session exec for `nohup ... &` never
    # completes, so setup used to burn the whole agent-setup budget and time out.
    monkeypatch.setattr(mod, "LAUNCH_EXEC_TIMEOUT", 0.05)
    env = _WedgedLaunchEnv()
    asyncio.run(asyncio.wait_for(_agent(tmp_path).setup(env), timeout=5))
    assert env.launched and any("curl" in c for c in env.commands[-1:])


def test_proxy_launch_returns_while_the_proxy_keeps_running(tmp_path, monkeypatch):
    # Daytona reports a session command's exit code only once its stdout/stderr pipes close.
    # capture_output reproduces that: it waits for EOF, so a launch that leaves a subshell
    # holding the pipes (the old `mkdir && nohup ... &` form) hangs here until the timeout.
    monkeypatch.setattr(mod, "PROXY_START_CMD", "sleep 5")
    monkeypatch.setattr(mod, "REMOTE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(mod, "REMOTE_PROXY_LOG_PATH", str(tmp_path / "logs" / "proxy.log"))
    done = subprocess.run(["bash", "-c", _proxy_launch_command()], capture_output=True, timeout=3)
    assert done.returncode == 0 and (tmp_path / "logs").is_dir()
