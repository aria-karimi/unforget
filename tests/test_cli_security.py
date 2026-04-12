import asyncio
from pathlib import Path

from unforget import cli
from unforget.config import UnforgetConfig, load_config


def test_ask_refuses_when_consent_declined(capsys, tmp_path: Path, monkeypatch) -> None:
    cfg = UnforgetConfig()
    cfg.security.setup_verified = True
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_prompt_disclosure_ack", lambda: False)

    status = asyncio.run(cli._run_ask("list files", cfg, config_path=cfg_path))
    captured = capsys.readouterr()
    assert status == 1
    assert "consent required" in captured.err
    assert cfg.security.consent_accepted is False


def test_ask_accepts_consent_and_persists(tmp_path: Path, monkeypatch, capsys) -> None:
    cfg = UnforgetConfig()
    cfg.security.setup_verified = True
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_prompt_disclosure_ack", lambda: True)
    async def fake_request_suggestion(**_kwargs):
        return "ls -la"
    monkeypatch.setattr(cli, "request_suggestion", fake_request_suggestion)

    status = asyncio.run(cli._run_ask("list files", cfg, config_path=cfg_path))
    captured = capsys.readouterr()
    assert status == 0
    assert "ls -la" in captured.out
    saved = load_config(cfg_path)
    assert saved.security.consent_accepted is True
    assert saved.security.consent_timestamp is not None


def test_ask_shows_timing_only_and_passes_timeout(tmp_path: Path, monkeypatch, capsys) -> None:
    cfg = UnforgetConfig()
    cfg.security.setup_verified = True
    cfg.interface.show_timing = True
    cfg.api.timeout_seconds = 9
    cfg.api.max_output_tokens = 64
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_prompt_disclosure_ack", lambda: True)
    received: dict[str, object] = {}

    async def fake_request_suggestion(**kwargs):
        received.update(kwargs)
        return "echo ok"

    monkeypatch.setattr(cli, "request_suggestion", fake_request_suggestion)

    status = asyncio.run(cli._run_ask("test", cfg, config_path=cfg_path))
    captured = capsys.readouterr()
    assert status == 0
    assert "building context" not in captured.err
    assert "contacting model" not in captured.err
    assert "unforget timing: " in captured.err
    assert received["timeout_seconds"] == 9
    assert received["max_output_tokens"] == 64


def test_cleanup_removes_config_and_managed_block(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    custom_log = tmp_path / "stdout-custom.log"
    config_path.write_text(
        "api:\n  provider: google\n"
        "context:\n"
        f"  stdout_log_path: {custom_log}\n"
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli, "DEFAULT_STDOUT_LOG_PATH", str(tmp_path / "stdout-default.log"))

    rc_path = tmp_path / ".bashrc"
    rc_path.write_text(
        "prefix\n"
        f"{cli.MANAGED_START}\n"
        "managed-content\n"
        f"{cli.MANAGED_END}\n"
        "suffix\n"
    )
    (tmp_path / "stdout-default.log").write_text("x\n")
    custom_log.write_text("y\n")

    status = cli._run_cleanup(config_path)
    assert status == 0
    assert not config_path.exists()
    assert not (tmp_path / "stdout-default.log").exists()
    assert not custom_log.exists()

    text = rc_path.read_text()
    assert "managed-content" not in text


def test_parser_includes_management_commands() -> None:
    parser = cli.build_parser()
    parsed = parser.parse_args(["cleanup"])
    assert parsed.command == "cleanup"
    parsed = parser.parse_args(["consent"])
    assert parsed.command == "consent"
    parsed = parser.parse_args(["ready"])
    assert parsed.command == "ready"
    parsed = parser.parse_args(["uninstall"])
    assert parsed.command == "uninstall"


def test_setup_prints_reload_guidance(tmp_path: Path, monkeypatch, capsys) -> None:
    async def fake_fetch(_provider: str, _api_key: str | None) -> list[str]:
        return ["openai/gpt-4o"]

    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_fetch_provider_models", fake_fetch)
    monkeypatch.setattr(cli, "_run_setup_connection_test", lambda _path: 0)
    monkeypatch.setattr(cli, "_choose_provider", lambda: "openai")
    monkeypatch.setattr(cli, "_choose_model", lambda _provider, _options: "openai/gpt-4o")
    monkeypatch.setattr(cli, "_install_shell_integration", lambda _cfg: 0)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "OPENAI_API_KEY")

    status = cli._run_setup(config_path)
    captured = capsys.readouterr()

    assert status == 0
    assert 'Reload your shell to apply integration changes: exec "$SHELL"' in captured.out


def test_ask_shows_exception_type_when_message_empty(tmp_path: Path, monkeypatch, capsys) -> None:
    cfg = UnforgetConfig()
    cfg.security.setup_verified = True
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_prompt_disclosure_ack", lambda: True)

    async def fake_request_suggestion(**_kwargs):
        raise TimeoutError()

    monkeypatch.setattr(cli, "request_suggestion", fake_request_suggestion)

    status = asyncio.run(cli._run_ask("test", cfg, config_path=cfg_path))
    captured = capsys.readouterr()
    assert status == 1
    assert "unforget error: TimeoutError" in captured.err


def test_prompt_disclosure_ack_returns_false_on_eof(monkeypatch) -> None:
    class _DummyPath:
        def open(self, *_args, **_kwargs):
            raise OSError("no tty")

    monkeypatch.setattr(cli, "Path", lambda *_args, **_kwargs: _DummyPath())
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: (_ for _ in ()).throw(EOFError()))

    assert cli._prompt_disclosure_ack() is False


def test_ask_requires_setup_verification(tmp_path: Path, capsys) -> None:
    cfg = UnforgetConfig()
    cfg_path = tmp_path / "config.yaml"

    status = asyncio.run(cli._run_ask("echo hi", cfg, config_path=cfg_path))
    captured = capsys.readouterr()
    assert status == 1
    assert "setup required" in captured.err


def test_cleanup_prints_reload_guidance_when_it_removes_files(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api:\n  provider: google\n")
    monkeypatch.setenv("HOME", str(tmp_path))

    rc_path = tmp_path / ".bashrc"
    rc_path.write_text(
        "prefix\n"
        f"{cli.MANAGED_START}\n"
        "managed-content\n"
        f"{cli.MANAGED_END}\n"
        "suffix\n"
    )

    status = cli._run_cleanup(config_path)
    captured = capsys.readouterr()

    assert status == 0
    assert 'Reload your shell to apply integration changes: exec "$SHELL"' in captured.out


def test_uninstall_cancels_when_not_confirmed(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_prompt_yes_no", lambda _question: False)

    status = cli._run_uninstall(config_path)
    captured = capsys.readouterr()
    assert status == 1
    assert "cancelled" in captured.err.lower()


def test_uninstall_runs_cleanup_and_uv_when_confirmed(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    called: dict[str, bool] = {"cleanup": False, "uv": False}
    monkeypatch.setattr(cli, "_prompt_yes_no", lambda _question: True)

    def fake_cleanup(path: Path, suppress_reload_message: bool = False) -> int:
        called["cleanup"] = True
        assert path == config_path
        assert suppress_reload_message is True
        return 0

    def fake_uv_uninstall() -> int:
        called["uv"] = True
        return 0

    monkeypatch.setattr(cli, "_run_cleanup", fake_cleanup)
    monkeypatch.setattr(cli, "_run_uv_uninstall", fake_uv_uninstall)

    status = cli._run_uninstall(config_path)
    captured = capsys.readouterr()
    assert status == 0
    assert called["cleanup"] is True
    assert called["uv"] is True
    assert "Uninstall completed." in captured.out


def test_uninstall_aborts_when_cleanup_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "_prompt_yes_no", lambda _question: True)
    monkeypatch.setattr(cli, "_run_cleanup", lambda _path, suppress_reload_message=False: 1)

    status = cli._run_uninstall(config_path)
    captured = capsys.readouterr()
    assert status == 1
    assert "cleanup failed" in captured.err
