from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from unforget.config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_STDOUT_LOG_PATH,
    UnforgetConfig,
    load_config,
    resolve_api_key,
    save_config,
)
from unforget.core.context import build_context_bundle
from unforget.core.llm import request_suggestion
from unforget.core.safety import block_if_forbidden, should_warn_destructive
from unforget.core.scrubber import SecretScrubber

try:
    from rich.console import Console
    from rich.panel import Panel
except ImportError:  # pragma: no cover
    Console = None
    Panel = None

PROVIDER_HELP_LINKS = {
    "google": "https://aistudio.google.com/app/apikey",
    "openai": "https://platform.openai.com/api-keys",
    "anthropic": "https://console.anthropic.com/settings/keys",
    "local": "https://ollama.com/",
}
MAX_MODEL_CHOICES = 25

MANAGED_START = "# >>> unforget managed block >>>"
MANAGED_END = "# <<< unforget managed block <<<"
DISCLOSURE_TEXT = (
    "unforget will gather local file names and terminal output to assist you. "
    "Do you acknowledge that you are 100% responsible for verifying every command before hitting Enter?"
)


def _google_model_rank(model: str) -> tuple[int, str]:
    name = model.lower()
    if "gemini-2.5-flash" in name and "lite" not in name and "preview" not in name:
        return (0, name)
    if "gemini-2.0-flash" in name and "lite" not in name and "preview" not in name:
        return (1, name)
    if "flash" in name and "lite" not in name and "preview" not in name:
        return (2, name)
    if "flash-lite" in name:
        return (3, name)
    if "preview" in name or "exp" in name:
        return (4, name)
    return (5, name)


def _load_script_template(name: str) -> str:
    return resources.files("unforget").joinpath("integrations", name).read_text()


def _ensure_managed_block(rc_path: Path, snippet: str) -> None:
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    content = rc_path.read_text(errors="ignore") if rc_path.exists() else ""
    if MANAGED_START in content and MANAGED_END in content:
        start = content.index(MANAGED_START)
        end = content.index(MANAGED_END) + len(MANAGED_END)
        new_content = content[:start].rstrip() + "\n\n" + snippet.strip() + "\n"
    else:
        new_content = content.rstrip() + ("\n\n" if content.strip() else "") + snippet.strip() + "\n"
    rc_path.write_text(new_content)


def _remove_managed_block(rc_path: Path) -> bool:
    if not rc_path.exists():
        return False
    content = rc_path.read_text(errors="ignore")
    if MANAGED_START not in content or MANAGED_END not in content:
        return False
    start = content.index(MANAGED_START)
    end = content.index(MANAGED_END) + len(MANAGED_END)
    new_content = (content[:start] + content[end:]).strip()
    rc_path.write_text((new_content + "\n") if new_content else "")
    return True


def _strip_template_markers(snippet: str) -> str:
    lines = []
    for line in snippet.splitlines():
        if line.strip() in {MANAGED_START, MANAGED_END}:
            continue
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def _detect_shell() -> str:
    shell_path = os.environ.get("SHELL", "").lower()
    if shell_path.endswith("zsh"):
        return "zsh"
    if shell_path.endswith("bash"):
        return "bash"
    if shell_path.endswith("fish"):
        return "fish"
    return "bash"


def _shell_rc_path(shell: str) -> Path:
    home = Path.home()
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "fish":
        return home / ".config" / "fish" / "config.fish"
    return home / ".bashrc"


def _install_shell_integration(config: UnforgetConfig) -> int:
    shell = _detect_shell()
    rc_path = _shell_rc_path(shell)
    snippet_name = f"unforget.{shell}"
    snippet_raw = _load_script_template(snippet_name)
    snippet = _strip_template_markers(snippet_raw)

    configured = (
        f'export UNFORGET_HOTKEY="{config.interface.hotkey}"\n'
        f'export UNFORGET_STDOUT_MAX_LINES="{config.context.stdout_max_lines}"\n'
        f'export UNFORGET_STDOUT_LOG="{config.context.stdout_log_path}"\n'
    )
    _ensure_managed_block(
        rc_path,
        f"{MANAGED_START}\n{configured}\n{snippet}{MANAGED_END}",
    )
    print(f"Installed integration for {shell}: {rc_path}")
    return 0


def _ensure_consent_for_ask(config: UnforgetConfig, config_path: Path) -> bool:
    if config.security.consent_accepted:
        return True
    if not _prompt_disclosure_ack():
        print("unforget error: consent required to continue.", file=sys.stderr)
        return False

    config.security.consent_accepted = True
    config.security.consent_timestamp = datetime.now(timezone.utc).isoformat()
    save_config(config, config_path)
    return True


def _is_setup_ready(config: UnforgetConfig) -> bool:
    return bool(config.security.setup_verified)


def _print_setup_required_error() -> None:
    print(
        "unforget error: setup required. Run `unforget setup` and complete a successful connection test first.",
        file=sys.stderr,
    )


def _print_reload_shell_message() -> None:
    print('Reload your shell to apply integration changes: exec "$SHELL"')


async def _run_ask(
    query: str,
    config: UnforgetConfig,
    config_path: Path = DEFAULT_CONFIG_PATH,
    require_consent: bool = True,
    require_ready: bool = True,
) -> int:
    if require_ready and not _is_setup_ready(config):
        _print_setup_required_error()
        return 1

    if require_consent and not _ensure_consent_for_ask(config, config_path):
        return 1

    scrubber = SecretScrubber()
    api_key = resolve_api_key(config.api.api_key)
    show_timing = config.interface.show_timing

    started_at = time.perf_counter()
    context_started_at = time.perf_counter()
    context = build_context_bundle(query, config.context, scrubber=scrubber)
    context_elapsed = time.perf_counter() - context_started_at

    try:
        model_started_at = time.perf_counter()
        suggestion = await request_suggestion(
            model=config.api.model,
            api_key=api_key,
            query=query,
            context_bundle=context,
            timeout_seconds=config.api.timeout_seconds,
            max_output_tokens=config.api.max_output_tokens,
        )
        model_elapsed = time.perf_counter() - model_started_at
        suggestion = block_if_forbidden(suggestion, config.safety)
        if config.interface.show_warnings and should_warn_destructive(suggestion, config.safety):
            print("warning: destructive command detected in suggestion", file=sys.stderr)
        if show_timing:
            total_elapsed = time.perf_counter() - started_at
            print(
                f"unforget timing: context={context_elapsed:.2f}s model={model_elapsed:.2f}s total={total_elapsed:.2f}s",
                file=sys.stderr,
            )
            print(
                f"unforget diag: model={config.api.model} context_chars={len(context)} max_output_tokens={config.api.max_output_tokens}",
                file=sys.stderr,
            )
        print(suggestion)
        return 0
    except Exception as exc:
        details = str(exc).strip() or exc.__class__.__name__
        print(f"unforget error: {details}", file=sys.stderr, flush=True)
        return 1


def _choose_provider() -> str:
    providers = ["google", "openai", "anthropic", "local"]
    print("Which provider? (Google/OpenAI/Anthropic/Local)")
    raw = input("> ").strip().lower()
    if raw in providers:
        return raw
    return "google"


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urlrequest.Request(url, headers=headers or {})
    with urlrequest.urlopen(req, timeout=15) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def _fetch_provider_models_sync(provider: str, api_key: str | None) -> list[str]:
    try:
        if provider == "google":
            if not api_key:
                return []
            query = urlparse.urlencode({"key": api_key})
            data = _http_get_json(f"https://generativelanguage.googleapis.com/v1beta/models?{query}")
            models = []
            for item in data.get("models", []):
                name = str(item.get("name", ""))
                methods = item.get("supportedGenerationMethods", []) or []
                if name.startswith("models/") and "generateContent" in methods:
                    model_name = name.split("/", 1)[1]
                    models.append(f"gemini/{model_name}")
            models.sort(key=_google_model_rank)
            return models

        if provider == "openai":
            if not api_key:
                return []
            data = _http_get_json(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            models = [f"openai/{m.get('id')}" for m in data.get("data", []) if m.get("id")]
            return models

        if provider == "anthropic":
            if not api_key:
                return []
            data = _http_get_json(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            models = [f"anthropic/{m.get('id')}" for m in data.get("data", []) if m.get("id")]
            return models

        if provider == "local":
            data = _http_get_json("http://localhost:11434/api/tags")
            models = [f"ollama/{m.get('name')}" for m in data.get("models", []) if m.get("name")]
            return models
    except (urlerror.URLError, json.JSONDecodeError, TimeoutError, KeyError, ValueError):
        return []

    return []


async def _fetch_provider_models(provider: str, api_key: str | None) -> list[str]:
    models = await asyncio.to_thread(_fetch_provider_models_sync, provider, api_key)
    # Preserve order while de-duplicating.
    unique: list[str] = []
    seen: set[str] = set()
    for model in models:
        if model not in seen:
            seen.add(model)
            unique.append(model)
    return unique[:MAX_MODEL_CHOICES]


def _choose_model(provider: str, options: list[str]) -> str:
    if not options:
        print(f"Could not fetch available {provider} models.")
        print("Enter custom model string:")
        while True:
            custom = input("> ").strip()
            if custom:
                return custom
            print("Model string cannot be empty. Enter custom model string:")

    print("Which model?")
    for idx, model in enumerate(options, start=1):
        default_suffix = " (default)" if idx == 1 else ""
        print(f"{idx}. {model}{default_suffix}")
    custom_idx = len(options) + 1
    print(f"{custom_idx}. Custom model string")

    raw = input("> ").strip()
    if raw == "":
        return options[0]

    try:
        choice = int(raw)
    except ValueError:
        print("Invalid selection, using default model.")
        return options[0]

    if 1 <= choice <= len(options):
        return options[choice - 1]
    if choice == custom_idx:
        print("Enter custom model string:")
        custom = input("> ").strip()
        return custom or options[0]

    print("Invalid selection, using default model.")
    return options[0]


async def _run_setup_async(config_path: Path) -> int:
    cfg = load_config(config_path)
    provider = _choose_provider()
    cfg.api.provider = provider

    print(f"API key page: {PROVIDER_HELP_LINKS[provider]}")
    print("Enter env var name (recommended) or plain API key:")
    cfg.api.api_key = input("> ").strip()
    resolved_key = resolve_api_key(cfg.api.api_key)
    fetched_models = await _fetch_provider_models(provider, resolved_key)
    cfg.api.model = _choose_model(provider, fetched_models)
    cfg.security.setup_verified = False
    cfg.security.setup_verified_timestamp = None
    cfg_path = save_config(cfg, config_path)
    print(f"Saved config to: {cfg_path}")
    _install_shell_integration(cfg)

    print("Testing provider connection...")
    status = _run_setup_connection_test(config_path)
    if status == 0:
        cfg.security.setup_verified = True
        cfg.security.setup_verified_timestamp = datetime.now(timezone.utc).isoformat()
        save_config(cfg, config_path)
        print("Connection OK.")
        _print_reload_shell_message()
    else:
        cfg.security.setup_verified = False
        cfg.security.setup_verified_timestamp = None
        save_config(cfg, config_path)
    return status


def _run_setup(config_path: Path) -> int:
    return asyncio.run(_run_setup_async(config_path))


def _run_verify_setup_command(config_path: Path) -> int:
    cfg = load_config(config_path)
    return asyncio.run(
        _run_ask(
            "echo hello",
            cfg,
            config_path=config_path,
            require_consent=False,
            require_ready=False,
        )
    )


def _run_setup_connection_test(config_path: Path) -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unforget.cli",
            "--config",
            str(config_path),
            "_verify-setup",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0 and completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def _run_cleanup(config_path: Path, suppress_reload_message: bool = False) -> int:
    removed_any = False
    had_error = False
    stdout_candidates: list[Path] = [Path(DEFAULT_STDOUT_LOG_PATH)]

    if config_path.exists():
        try:
            cfg = load_config(config_path)
            stdout_candidates.append(Path(cfg.context.stdout_log_path))
        except Exception:
            # Best effort: continue cleanup even if config parsing fails.
            pass

    if config_path.exists():
        try:
            config_path.unlink()
            removed_any = True
            print(f"Removed config: {config_path}")
        except OSError as exc:
            had_error = True
            print(f"Could not remove config {config_path}: {exc}", file=sys.stderr)

    for shell in ("bash", "zsh", "fish"):
        rc_path = _shell_rc_path(shell)
        try:
            if _remove_managed_block(rc_path):
                removed_any = True
                print(f"Removed shell integration block: {rc_path}")
        except OSError as exc:
            had_error = True
            print(f"Could not update shell rc file {rc_path}: {exc}", file=sys.stderr)

    unique_logs: set[Path] = set(stdout_candidates)
    for log_path in unique_logs:
        if not log_path.exists():
            continue
        try:
            log_path.unlink()
            removed_any = True
            print(f"Removed stdout log: {log_path}")
        except OSError as exc:
            had_error = True
            print(f"Could not remove stdout log {log_path}: {exc}", file=sys.stderr)

    if not removed_any:
        print("Nothing to clean up.")
    if removed_any and not suppress_reload_message:
        _print_reload_shell_message()
    return 1 if had_error else 0


def _run_consent(config_path: Path) -> int:
    cfg = load_config(config_path)
    if not _is_setup_ready(cfg):
        _print_setup_required_error()
        return 1
    return 0 if _ensure_consent_for_ask(cfg, config_path) else 1


def _run_ready(config_path: Path) -> int:
    cfg = load_config(config_path)
    if _is_setup_ready(cfg):
        return 0
    _print_setup_required_error()
    return 1


def _prompt_yes_no(question: str) -> bool:
    prompt = f"{question} [y/N]: "
    answer = ""
    try:
        with Path("/dev/tty").open("r", encoding="utf-8", errors="ignore") as tty_in, Path("/dev/tty").open(
            "w", encoding="utf-8", errors="ignore"
        ) as tty_out:
            tty_out.write(prompt)
            tty_out.flush()
            answer = tty_in.readline().strip().lower()
    except OSError:
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            answer = ""
    return answer in {"y", "yes"}


def _run_uv_uninstall() -> int:
    try:
        completed = subprocess.run(["uv", "tool", "uninstall", "unforget"], check=False)
    except FileNotFoundError:
        print("unforget error: uv is required but was not found in PATH.", file=sys.stderr)
        return 1
    return completed.returncode


def _run_uninstall(config_path: Path) -> int:
    if not _prompt_yes_no("Are you sure you want to uninstall unforget and remove local integration?"):
        print("Uninstall cancelled.", file=sys.stderr)
        return 1

    cleanup_status = _run_cleanup(config_path, suppress_reload_message=True)
    if cleanup_status != 0:
        print("unforget error: cleanup failed; aborting uninstall.", file=sys.stderr)
        return cleanup_status

    uninstall_status = _run_uv_uninstall()
    if uninstall_status != 0:
        print("unforget error: uv uninstall failed.", file=sys.stderr)
        return uninstall_status

    print("Uninstall completed.")
    _print_reload_shell_message()
    return 0


def _show_disclosure() -> None:
    title = "Security & Privacy Disclosure"
    if Console and Panel:
        console = Console(file=sys.stderr)
        console.print(Panel(DISCLOSURE_TEXT, title=title, border_style="yellow"))
    else:
        print(f"[{title}]", file=sys.stderr)
        print(DISCLOSURE_TEXT, file=sys.stderr)


def _prompt_disclosure_ack() -> bool:
    _show_disclosure()
    prompt = "Type yes or y to proceed: "
    answer = ""
    try:
        with Path("/dev/tty").open("r", encoding="utf-8", errors="ignore") as tty_in, Path("/dev/tty").open(
            "w", encoding="utf-8", errors="ignore"
        ) as tty_out:
            tty_out.write(prompt)
            tty_out.flush()
            answer = tty_in.readline().strip().lower()
    except OSError:
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            answer = ""
    return answer in {"yes", "y"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unforget")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Ask for a shell suggestion")
    ask.add_argument("query", type=str)

    sub.add_parser("setup", help="Interactive setup wizard")
    sub.add_parser("cleanup", help="Remove local config and managed shell integration")
    sub.add_parser("consent", help="Show disclosure and record consent")
    sub.add_parser("ready", help="Check whether setup has been completed successfully")
    sub.add_parser("uninstall", help="Confirm and uninstall unforget")
    sub.add_parser("_verify-setup", help=argparse.SUPPRESS)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "setup":
        raise SystemExit(_run_setup(args.config))
    if args.command == "cleanup":
        raise SystemExit(_run_cleanup(args.config))
    if args.command == "consent":
        raise SystemExit(_run_consent(args.config))
    if args.command == "ready":
        raise SystemExit(_run_ready(args.config))
    if args.command == "uninstall":
        raise SystemExit(_run_uninstall(args.config))
    if args.command == "_verify-setup":
        raise SystemExit(_run_verify_setup_command(args.config))

    cfg = load_config(args.config)
    if args.command == "ask":
        raise SystemExit(asyncio.run(_run_ask(args.query, cfg, config_path=args.config)))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
