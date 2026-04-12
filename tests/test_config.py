from pathlib import Path

import pytest

from unforget.config import ValidationError, UnforgetConfig, load_config, resolve_api_key, save_config


def test_save_and_load_config(tmp_path: Path) -> None:
    cfg = UnforgetConfig()
    cfg.api.model = "openai/gpt-4.1-mini"
    path = tmp_path / "config.yaml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.api.model == "openai/gpt-4.1-mini"


def test_resolve_api_key_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret-value")
    assert resolve_api_key("MY_KEY") == "secret-value"


def test_security_fields_persist(tmp_path: Path) -> None:
    cfg = UnforgetConfig()
    cfg.security.consent_accepted = True
    cfg.security.consent_timestamp = "2026-04-11T00:00:00+00:00"
    cfg.security.setup_verified = True
    cfg.security.setup_verified_timestamp = "2026-04-11T00:00:10+00:00"
    path = tmp_path / "config.yaml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.security.consent_accepted is True
    assert loaded.security.consent_timestamp == "2026-04-11T00:00:00+00:00"
    assert loaded.security.setup_verified is True
    assert loaded.security.setup_verified_timestamp == "2026-04-11T00:00:10+00:00"


def test_invalid_security_field_fails_validation(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("security:\n  consent_accepted: not-a-bool\n")
    with pytest.raises(ValidationError):
        load_config(path)


def test_default_latency_profile_values() -> None:
    cfg = UnforgetConfig()
    assert cfg.interface.hotkey == "^[u"
    assert cfg.context.max_files == 30
    assert cfg.context.stdout_lines == 50
    assert cfg.context.history_limit == 10
    assert cfg.context.tier_tokens["vital"] == 120
    assert cfg.context.tier_tokens["environment"] == 160
    assert cfg.context.tier_tokens["filesystem"] == 240
    assert cfg.context.tier_tokens["stdout"] == 800
    assert cfg.context.tier_tokens["history"] == 160
    assert cfg.api.timeout_seconds == 60
    assert cfg.api.max_output_tokens == 128
    assert cfg.interface.show_timing is False
