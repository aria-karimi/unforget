from pathlib import Path

from unforget import cli
from unforget.config import load_config


def _mock_inputs(monkeypatch, values: list[str]) -> None:
    stream = iter(values)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(stream))


def test_setup_uses_fetched_model_choice(tmp_path: Path, monkeypatch) -> None:
    async def fake_fetch(provider: str, api_key: str | None) -> list[str]:
        assert provider == "google"
        return ["gemini/gemini-2.0-flash", "gemini/gemini-1.5-flash"]

    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_fetch_provider_models", fake_fetch)
    monkeypatch.setattr(cli, "_run_setup_connection_test", lambda _path: 0)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    _mock_inputs(monkeypatch, ["google", "GOOGLE_API_KEY", "2"])

    status = cli._run_setup(config_path)
    assert status == 0

    saved = load_config(config_path)
    assert saved.api.provider == "google"
    assert saved.api.model == "gemini/gemini-1.5-flash"
    assert saved.security.setup_verified is True
    assert saved.security.setup_verified_timestamp is not None


def test_setup_allows_custom_model_when_fetch_fails(tmp_path: Path, monkeypatch) -> None:
    async def fake_fetch(_provider: str, _api_key: str | None) -> list[str]:
        return []

    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_fetch_provider_models", fake_fetch)
    monkeypatch.setattr(cli, "_run_setup_connection_test", lambda _path: 0)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    _mock_inputs(monkeypatch, ["openai", "OPENAI_API_KEY", "openai/gpt-4o"])

    status = cli._run_setup(config_path)
    assert status == 0

    saved = load_config(config_path)
    assert saved.api.provider == "openai"
    assert saved.api.model == "openai/gpt-4o"
    assert saved.security.setup_verified is True


def test_setup_requires_non_empty_custom_model_on_fetch_failure(tmp_path: Path, monkeypatch) -> None:
    async def fake_fetch(_provider: str, _api_key: str | None) -> list[str]:
        return []

    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_fetch_provider_models", fake_fetch)
    monkeypatch.setattr(cli, "_run_setup_connection_test", lambda _path: 0)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    _mock_inputs(monkeypatch, ["local", "OLLAMA_KEY", "", "ollama/llama3"])

    status = cli._run_setup(config_path)
    assert status == 0

    saved = load_config(config_path)
    assert saved.api.model == "ollama/llama3"
    assert saved.security.setup_verified is True


def test_google_model_rank_prefers_flash_over_lite() -> None:
    models = [
        "gemini/gemini-2.5-flash-lite",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.0-flash",
    ]
    ranked = sorted(models, key=cli._google_model_rank)
    assert ranked[0] == "gemini/gemini-2.5-flash"


def test_bash_integration_reads_from_tty_and_handles_empty_query() -> None:
    snippet = cli._load_script_template("unforget.bash")
    assert "UNFORGET_HOTKEY=\"${UNFORGET_HOTKEY:-\\eu}\"" in snippet
    assert "UNFORGET_HOTKEY_FALLBACK=\"${UNFORGET_HOTKEY_FALLBACK:-\\eu}\"" in snippet
    assert "command unforget ready" in snippet
    assert "< /dev/tty" in snippet
    assert "stty -g < /dev/tty" in snippet
    assert "stty sane < /dev/tty" in snippet
    assert "stty \"$tty_state\" < /dev/tty" in snippet
    assert "[[ -z \"$user_query\" ]] && return 0" in snippet
    assert "command unforget consent" in snippet
    assert "mktemp" in snippet
    assert "ask_stderr" in snippet
    assert "_unforget_run_with_spinner" in snippet
    assert "python3 - \"$query\" \"${UNFORGET_SPINNER_DELAY}\"" in snippet
    assert 'print(f"\\runforget: thinking {frame}"' in snippet
    assert "_unforget_clear_status" in snippet
    assert "trap '_unforget_clear_status" in snippet
    assert "_unforget_restore_trap INT" in snippet
    assert "_unforget_restore_trap TERM" in snippet
    assert "uf_bind_hotkey() {" in snippet
    assert "uf_hotkey_status() {" in snippet
    assert "uf_bind_hotkey" in snippet
    assert "unforget() {" not in snippet
    assert "unforget_uninstall" not in snippet
    assert "hotkey-status" not in snippet
    assert "bind-hotkey" not in snippet


def test_zsh_integration_is_consent_first_and_interrupt_safe() -> None:
    snippet = cli._load_script_template("unforget.zsh")
    assert "UNFORGET_HOTKEY=\"${UNFORGET_HOTKEY:-^[u}\"" in snippet
    assert "UNFORGET_HOTKEY_FALLBACK=\"${UNFORGET_HOTKEY_FALLBACK:-^[u}\"" in snippet
    assert "command unforget ready" in snippet
    assert "command unforget consent || {" in snippet
    assert "mktemp" in snippet
    assert "ask_stderr" in snippet
    assert "trap '_unforget_stop_spinner" in snippet
    assert "_unforget_restore_trap INT" in snippet
    assert "_unforget_restore_trap TERM" in snippet
    assert "function uf_bind_hotkey() {" in snippet
    assert "function uf_hotkey_status() {" in snippet
    assert "uf_bind_hotkey" in snippet
    assert "unforget() {" not in snippet
    assert "unforget_uninstall" not in snippet
    assert "hotkey-status" not in snippet
    assert "bind-hotkey" not in snippet


def test_fish_integration_is_consent_first_and_interrupt_safe() -> None:
    snippet = cli._load_script_template("unforget.fish")
    assert "set -q UNFORGET_HOTKEY; or set -g UNFORGET_HOTKEY \\eu" in snippet
    assert "set -q UNFORGET_HOTKEY_FALLBACK; or set -g UNFORGET_HOTKEY_FALLBACK \\eu" in snippet
    assert "command unforget ready" in snippet
    assert "command unforget consent" in snippet
    assert "mktemp" in snippet
    assert "ask_stderr" in snippet
    assert "function __unforget_on_int --on-signal INT" in snippet
    assert "_unforget_stop_spinner \"$__unforget_spin_pid\"" in snippet
    assert "function uf_bind_hotkey" in snippet
    assert "function uf_hotkey_status" in snippet
    assert "uf_bind_hotkey" in snippet
    assert "function unforget()" not in snippet
    assert "unforget_uninstall" not in snippet
    assert "hotkey-status" not in snippet
    assert "bind-hotkey" not in snippet
