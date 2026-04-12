from __future__ import annotations

from unforget.config import SafetyConfig


def block_if_forbidden(suggestion: str, safety: SafetyConfig) -> str:
    cleaned = suggestion.strip()
    if not cleaned:
        return cleaned

    command_word = cleaned.split()[0]
    blocked = {cmd.strip() for cmd in safety.blocked_commands}
    if command_word in blocked:
        raise ValueError(f"Blocked command suggested: {command_word}")
    return cleaned


def should_warn_destructive(suggestion: str, safety: SafetyConfig) -> bool:
    cleaned = suggestion.strip().lower()
    return any(pattern.lower() in cleaned for pattern in safety.destructive_patterns)
