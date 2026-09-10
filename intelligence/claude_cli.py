"""Claude provider backed by the local, authenticated Claude Code CLI.

This is the intelligence layer for ``python run_agent.py live``. It reuses every
prompt and every structured-output model from :mod:`intelligence.claude` and only
swaps the transport: instead of calling the Anthropic SDK (which needs an API
key) it shells out to ``claude -p`` in headless mode, which runs on the machine's
signed-in Claude Pro subscription. No API key is involved.

``claude -p --output-format json`` returns an envelope like
``{"type": "result", "subtype": "success", "result": "<text>", "is_error": false}``
and the ``result`` string is fed back through the same JSON validation the SDK
path uses.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from intelligence.claude import ROOT, SYSTEM_PROMPT, ClaudeProvider


def find_claude_binary() -> str | None:
    for name in ("claude", "claude.cmd", "claude.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


class ClaudeCliUnavailable(RuntimeError):
    """Raised when the ``claude`` CLI cannot be located or run."""


class ClaudeCliProvider(ClaudeProvider):
    """Live provider that drives the local Claude Code CLI."""

    is_live = True

    def __init__(
        self,
        *,
        claude_bin: str | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._bin = claude_bin or find_claude_binary()
        self._timeout = timeout or int(os.getenv("CLAUDE_CLI_TIMEOUT", "300"))
        # Optional: pin a model for the CLI (e.g. CLAUDE_CLI_MODEL=claude-opus-5).
        # Unset -> the CLI uses the account's configured default.
        self._cli_model = os.getenv("CLAUDE_CLI_MODEL", "").strip()

    @property
    def available(self) -> bool:
        return bool(self._bin)

    def ensure_available(self) -> None:
        if not self._bin:
            raise ClaudeCliUnavailable(
                "The 'claude' CLI is not on PATH. Install Claude Code and run "
                "'claude' once to sign in before starting live mode."
            )

    # The SDK client is never used on this path.
    @property
    def client(self) -> Any:  # pragma: no cover - guard only
        raise NotImplementedError("ClaudeCliProvider uses the claude CLI, not the Anthropic SDK client")

    def _call_claude(self, user_content: str, system: str = SYSTEM_PROMPT, max_tokens: int = 2000) -> str:
        self.ensure_available()
        prompt = (
            f"{system}\n\n"
            f"----- INPUT -----\n{user_content}\n----- END INPUT -----\n\n"
            "Respond with ONLY the JSON object described above. No prose, no code fences."
        )
        cmd = [self._bin, "-p", "--output-format", "json"]
        if self._cli_model:
            cmd += ["--model", self._cli_model]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self._timeout,
                cwd=str(ROOT),
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired as exc:  # noqa: TRY003
            raise RuntimeError(f"claude CLI timed out after {self._timeout}s") from exc
        except OSError as exc:
            raise ClaudeCliUnavailable(f"could not launch claude CLI: {exc}") from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI exited {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()[:400]}"
            )

        stdout = (proc.stdout or "").strip()
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            # Some versions print the bare result when --output-format is ignored.
            if stdout:
                return stdout
            raise RuntimeError("claude CLI returned an empty response")

        if isinstance(envelope, dict):
            if envelope.get("is_error") or envelope.get("subtype") not in (None, "success"):
                raise RuntimeError(f"claude CLI reported an error: {str(envelope)[:300]}")
            result = envelope.get("result")
            if isinstance(result, str) and result.strip():
                return result
        raise RuntimeError(f"claude CLI response had no result text: {stdout[:300]}")
