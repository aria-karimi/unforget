from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("~/.config/unforget/config.yaml").expanduser()
DEFAULT_STDOUT_LOG_PATH = "/tmp/unforget_stdout.log"


class ValidationError(ValueError):
    pass


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValidationError(f"{field_name} must be a boolean")


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValidationError(f"{field_name} must be an integer")


def _as_non_negative_int(value: Any, field_name: str) -> int:
    parsed = _as_int(value, field_name)
    if parsed < 0:
        raise ValidationError(f"{field_name} must be >= 0")
    return parsed


def _as_list_str(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError(f"{field_name} must be a list")
    if not all(isinstance(item, str) for item in value):
        raise ValidationError(f"{field_name} items must be strings")
    return value


@dataclass
class ApiConfig:
    provider: str = "google"
    model: str = "gemini/gemini-2.5-flash"
    api_key: str = "GOOGLE_API_KEY"
    timeout_seconds: int = 60
    max_output_tokens: int = 128


@dataclass
class InterfaceConfig:
    hotkey: str = "^[u"
    show_warnings: bool = True
    show_timing: bool = False


@dataclass
class ContextConfig:
    max_files: int = 30
    stdout_lines: int = 50
    history_limit: int = 10
    auto_redact: bool = True
    stdout_log_path: str = DEFAULT_STDOUT_LOG_PATH
    stdout_max_lines: int = 2000
    tier_tokens: dict[str, int] = field(
        default_factory=lambda: {
            "vital": 120,
            "environment": 160,
            "filesystem": 240,
            "stdout": 800,
            "history": 160,
        }
    )


@dataclass
class SafetyConfig:
    blocked_commands: list[str] = field(default_factory=lambda: ["mkfs", "shred"])
    destructive_patterns: list[str] = field(
        default_factory=lambda: ["rm -rf", "sudo rm -rf", "dd if=", ":(){ :|:& };:"]
    )


@dataclass
class SecurityConfig:
    consent_accepted: bool = False
    consent_timestamp: str | None = None
    setup_verified: bool = False
    setup_verified_timestamp: str | None = None


@dataclass
class UnforgetConfig:
    api: ApiConfig = field(default_factory=ApiConfig)
    interface: InterfaceConfig = field(default_factory=InterfaceConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


def _parse_config(data: dict[str, Any]) -> UnforgetConfig:
    api_data = data.get("api", {}) or {}
    interface_data = data.get("interface", {}) or {}
    context_data = data.get("context", {}) or {}
    safety_data = data.get("safety", {}) or {}
    security_data = data.get("security", {}) or {}

    defaults = ContextConfig().tier_tokens.copy()
    tier_tokens_raw = context_data.get("tier_tokens", {})
    if isinstance(tier_tokens_raw, dict):
        for key, value in tier_tokens_raw.items():
            if key in defaults:
                defaults[key] = _as_non_negative_int(value, f"context.tier_tokens.{key}")

    api = ApiConfig(
        provider=str(api_data.get("provider", ApiConfig.provider)),
        model=str(api_data.get("model", ApiConfig.model)),
        api_key=str(api_data.get("api_key", ApiConfig.api_key)),
        timeout_seconds=_as_int(
            api_data.get("timeout_seconds", ApiConfig.timeout_seconds),
            "api.timeout_seconds",
        ),
        max_output_tokens=_as_int(
            api_data.get("max_output_tokens", ApiConfig.max_output_tokens),
            "api.max_output_tokens",
        ),
    )
    interface = InterfaceConfig(
        hotkey=str(interface_data.get("hotkey", InterfaceConfig.hotkey)),
        show_warnings=_as_bool(
            interface_data.get("show_warnings", InterfaceConfig.show_warnings),
            "interface.show_warnings",
        ),
        show_timing=_as_bool(
            interface_data.get("show_timing", InterfaceConfig.show_timing),
            "interface.show_timing",
        ),
    )
    context = ContextConfig(
        max_files=_as_non_negative_int(context_data.get("max_files", ContextConfig.max_files), "context.max_files"),
        stdout_lines=_as_non_negative_int(
            context_data.get("stdout_lines", ContextConfig.stdout_lines),
            "context.stdout_lines",
        ),
        history_limit=_as_non_negative_int(
            context_data.get("history_limit", ContextConfig.history_limit),
            "context.history_limit",
        ),
        auto_redact=_as_bool(
            context_data.get("auto_redact", ContextConfig.auto_redact),
            "context.auto_redact",
        ),
        stdout_log_path=str(context_data.get("stdout_log_path", ContextConfig.stdout_log_path)),
        stdout_max_lines=_as_non_negative_int(
            context_data.get("stdout_max_lines", ContextConfig.stdout_max_lines),
            "context.stdout_max_lines",
        ),
        tier_tokens=defaults,
    )
    safety = SafetyConfig(
        blocked_commands=_as_list_str(
            safety_data.get("blocked_commands", SafetyConfig().blocked_commands),
            "safety.blocked_commands",
        ),
        destructive_patterns=_as_list_str(
            safety_data.get("destructive_patterns", SafetyConfig().destructive_patterns),
            "safety.destructive_patterns",
        ),
    )
    consent_accepted = _as_bool(
        security_data.get("consent_accepted", SecurityConfig.consent_accepted),
        "security.consent_accepted",
    )
    consent_timestamp_raw = security_data.get("consent_timestamp", SecurityConfig.consent_timestamp)
    if consent_timestamp_raw is not None and not isinstance(consent_timestamp_raw, str):
        raise ValidationError("security.consent_timestamp must be a string or null")
    setup_verified = _as_bool(
        security_data.get("setup_verified", SecurityConfig.setup_verified),
        "security.setup_verified",
    )
    setup_verified_timestamp_raw = security_data.get(
        "setup_verified_timestamp",
        SecurityConfig.setup_verified_timestamp,
    )
    if setup_verified_timestamp_raw is not None and not isinstance(setup_verified_timestamp_raw, str):
        raise ValidationError("security.setup_verified_timestamp must be a string or null")
    security = SecurityConfig(
        consent_accepted=consent_accepted,
        consent_timestamp=consent_timestamp_raw,
        setup_verified=setup_verified,
        setup_verified_timestamp=setup_verified_timestamp_raw,
    )
    return UnforgetConfig(
        api=api,
        interface=interface,
        context=context,
        safety=safety,
        security=security,
    )


def load_config(path: Path | None = None) -> UnforgetConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return UnforgetConfig()

    raw = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValidationError("Config root must be a mapping")
    return _parse_config(raw)


def save_config(config: UnforgetConfig, path: Path | None = None) -> Path:
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(asdict(config), sort_keys=False))
    return config_path


def resolve_api_key(api_key: str) -> str | None:
    if api_key in os.environ and os.environ[api_key]:
        return os.environ[api_key]
    return api_key or None
