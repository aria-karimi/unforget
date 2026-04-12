from __future__ import annotations

import getpass
import os
import platform
import shlex
from pathlib import Path

from unforget.config import ContextConfig
from unforget.core.scrubber import SecretScrubber


def _token_char_budget(tokens: int) -> int:
    return max(0, tokens * 4)


def _trim_by_budget(text: str, tokens: int) -> str:
    budget = _token_char_budget(tokens)
    if len(text) <= budget:
        return text
    return text[-budget:]


def _read_tail_chunk(path: Path, max_bytes: int) -> str:
    if not path.exists() or max_bytes <= 0:
        return ""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        read_from = max(0, size - max_bytes)
        f.seek(read_from)
        data = f.read()
    return data.decode(errors="ignore")


def _read_tail_lines(path: Path, lines: int) -> str:
    if lines <= 0:
        return ""
    # Read from the end to avoid loading entire logs on each ask.
    tail_text = _read_tail_chunk(path, max_bytes=max(4096, lines * 512))
    data = [line for line in tail_text.splitlines() if line.strip()]
    return "\n".join(data[-lines:])


def _read_shell_history(limit: int) -> list[str]:
    if limit <= 0:
        return []
    shell = os.environ.get("SHELL", "")
    candidates: list[Path] = []
    home = Path.home()
    if "zsh" in shell:
        candidates.append(home / ".zsh_history")
    if "bash" in shell:
        candidates.append(home / ".bash_history")
    candidates.extend([home / ".zsh_history", home / ".bash_history"])

    for path in candidates:
        if path.exists():
            # Read only a tail window from history; full-file scans are expensive on large histories.
            lines = [
                line.strip()
                for line in _read_tail_lines(path, max(limit * 40, 200)).splitlines()
                if line.strip()
            ]
            parsed: list[str] = []
            for line in lines:
                # zsh stores metadata like ": 1712386425:0;command".
                if line.startswith(": ") and ";" in line:
                    parsed.append(line.split(";", 1)[1].strip())
                else:
                    parsed.append(line)
            return parsed[-limit:]
    return []


def _filesystem_tree(cwd: Path, max_files: int) -> list[str]:
    entries: list[str] = []
    try:
        for entry in sorted(cwd.iterdir(), key=lambda p: p.name.lower()):
            marker = ""
            if entry.is_dir():
                marker = "/"
            elif os.access(entry, os.X_OK):
                marker = "*"
            entries.append(f"{entry.name}{marker}")
            if len(entries) >= max_files:
                break
    except OSError:
        return []
    return entries


def build_context_bundle(
    query: str,
    context_cfg: ContextConfig,
    scrubber: SecretScrubber | None = None,
) -> str:
    scrub = scrubber or SecretScrubber()
    cwd = Path.cwd()

    vital = {
        "os": platform.system(),
        "kernel": platform.release(),
        "shell": os.environ.get("SHELL", "unknown"),
        "user": getpass.getuser(),
        "cwd": str(cwd),
        "query": query,
    }
    env_subset = {
        key: os.environ.get(key, "")
        for key in ("PATH", "EDITOR", "LANG", "TERM", "HOME", "SHELL")
        if key in os.environ
    }
    env_subset = scrub.scrub_mapping(env_subset) if context_cfg.auto_redact else env_subset

    max_files = max(0, context_cfg.max_files)
    stdout_lines = max(0, min(context_cfg.stdout_lines, context_cfg.stdout_max_lines))
    history_limit = max(0, context_cfg.history_limit)

    tree = _filesystem_tree(cwd, max_files)

    stdout_text = ""
    try:
        stdout_text = _read_tail_lines(Path(context_cfg.stdout_log_path), stdout_lines)
        if context_cfg.auto_redact:
            stdout_text = scrub.scrub_text(stdout_text)
    except OSError:
        stdout_text = ""

    history_text = ""
    try:
        history_cmds = _read_shell_history(history_limit)
        if context_cfg.auto_redact:
            history_cmds = [scrub.scrub_text(cmd) for cmd in history_cmds]
        history_text = "\n".join(history_cmds)
    except OSError:
        history_text = ""

    tier_tokens = context_cfg.tier_tokens
    vital_text = _trim_by_budget("\n".join(f"{k}: {v}" for k, v in vital.items()), tier_tokens["vital"])
    env_text = _trim_by_budget(
        "\n".join(f"{k}={shlex.quote(v)}" for k, v in env_subset.items()),
        tier_tokens["environment"],
    )
    fs_text = _trim_by_budget("\n".join(tree), tier_tokens["filesystem"])
    out_text = _trim_by_budget(stdout_text, tier_tokens["stdout"])
    hist_text = _trim_by_budget(history_text, tier_tokens["history"])

    parts = [
        "[Vital]",
        vital_text,
        "",
        "[Environment]",
        env_text,
        "",
        "[Filesystem]",
        fs_text,
        "",
        "[Stdout]",
        out_text,
        "",
        "[History]",
        hist_text,
    ]
    return "\n".join(parts).strip() + "\n"
