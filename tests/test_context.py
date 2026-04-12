from pathlib import Path

from unforget.config import ContextConfig
from unforget.core.context import build_context_bundle
from unforget.core.scrubber import SecretScrubber


def test_context_includes_sections(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "stdout.log"
    log.write_text("token=abc\nnormal line\n")
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("PATH", "/usr/bin")

    cfg = ContextConfig(stdout_log_path=str(log), stdout_lines=10, max_files=5, history_limit=1)
    bundle = build_context_bundle("why failed", cfg, scrubber=SecretScrubber())

    assert "[Vital]" in bundle
    assert "[Environment]" in bundle
    assert "[Filesystem]" in bundle
    assert "[Stdout]" in bundle
    assert "[History]" in bundle
    assert "[REDACTED]" in bundle


def test_context_enforces_stdout_and_tier_limits(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "stdout.log"
    log.write_text("line1\nline2\nline3\nline4\nline5\n")
    monkeypatch.setenv("SHELL", "/bin/bash")

    cfg = ContextConfig(
        stdout_log_path=str(log),
        stdout_lines=5,
        stdout_max_lines=2,
        history_limit=0,
        tier_tokens={
            "vital": 120,
            "environment": 160,
            "filesystem": 240,
            "stdout": 1,
            "history": 160,
        },
    )
    bundle = build_context_bundle("check limits", cfg, scrubber=SecretScrubber())

    # stdout section is limited by min(stdout_lines, stdout_max_lines)=2 lines before token trim.
    assert "line1" not in bundle
    assert "line2" not in bundle
    # token budget of 1 token means 4 chars retained from stdout tail.
    assert "line5" not in bundle
