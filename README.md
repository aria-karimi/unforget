# unforget

`unforget` is a lightweight BYOK shell assistant that suggests commands using local terminal context (filesystem, shell env, recent output/history) and your chosen LLM provider.

> **Distribution:** install from GitHub using `uv`, or install the PyPI package `unforget-cli`.

## Prerequisites
- Python 3.10+
- Bash, Zsh, or Fish shell
- [uv](https://docs.astral.sh/uv/)

## Install

The installed command is always `unforget`.

### GitHub + uv

```bash
uv tool install "git+https://github.com/aria-karimi/unforget.git"
```

### PyPI

```bash
uv tool install unforget-cli
```

or:

```bash
pipx install unforget-cli
```

### Manage install

```bash
uv tool install --reinstall "git+https://github.com/aria-karimi/unforget.git"
unforget uninstall    # removes config, shell integration, and tool
```

Note: Use `unforget uninstall` instead of `uv tool uninstall unforget` directly. The latter only removes the tool but leaves behind local config files (`~/.config/unforget/config.yaml`), shell integration blocks, and logs in your home directory.

## Quick start

1. Install using `uv` (see commands above).
2. Run setup:

```bash
unforget setup
```

3. Reload your shell once to load the integration:

```bash
exec "$SHELL"
```

4. Request a suggestion:

```bash
unforget ask "find all large files in this folder"
```

Setup runs an interactive provider/model/key wizard and a connection test. After setup succeeds, it prints reload guidance so the shell integration can be loaded.

## Command reference

### CLI commands

```bash
unforget setup         # interactive provider/model/key setup + connection test
unforget ask "..."     # request a shell suggestion
unforget ready         # exit 0 only after a successful setup test
unforget consent       # show disclosure and record consent
unforget cleanup       # remove local config, managed shell block, and logs
unforget uninstall     # confirmation prompt, cleanup, uv uninstall, then reload guidance
```

### Shell integration functions

Available after `unforget setup` succeeds and you reload the shell once:

```bash
uf_hotkey_status   # show active hotkey bindings in the current shell session
uf_bind_hotkey     # re-bind hotkeys in the current shell session
```

## Shell behavior

Setup installs shell integration snippets in:
- Bash: `~/.bashrc`
- Zsh: `~/.zshrc`
- Fish: `~/.config/fish/config.fish`

Hotkey binding:
- Default: `Alt+u`, fallback: `Esc+u` (configurable via `UNFORGET_HOTKEY` env vars)
- When pressed, opens an `unforget>` prompt
- Injects suggestion into current command buffer (does not auto-run)

Prerequisites:
- Must run `unforget setup`, then reload your shell once, before `ask` or hotkey work
- First hotkey use prompts for consent before any spinner appears

During suggestion fetch:
- A short `unforget: thinking` spinner runs in-widget
- Press `Ctrl+C` to cancel the request and clear the spinner

## BYOK / API integration guide

`unforget` is BYOK: you choose provider/model and bring your own key.

### Built-in setup providers

`unforget setup` currently supports:
- Google
- OpenAI
- Anthropic
- Local (Ollama)

During setup, `unforget` tries to fetch available models for your provider and lets you pick from them.
If model fetch fails, setup asks for a custom litellm model string.

Config is written to:

`~/.config/unforget/config.yaml`

### API key methods

You can store either:
1. Environment variable name (**recommended**)
2. Plain-text key in config (fallback)

Example env vars:

```bash
export GOOGLE_API_KEY="..."
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
```

Example config:

```yaml
api:
  provider: "openai"
  model: "openai/gpt-4.1-mini"
  api_key: "OPENAI_API_KEY"
  timeout_seconds: 60
  max_output_tokens: 128
interface:
  show_timing: false
```

### Default context profile

`unforget` defaults to a balanced context profile:
- `context.max_files: 30`
- `context.stdout_lines: 50`
- `context.history_limit: 10`
- `context.tier_tokens.vital: 120`
- `context.tier_tokens.environment: 160`
- `context.tier_tokens.filesystem: 240`
- `context.tier_tokens.stdout: 800`
- `context.tier_tokens.history: 160`

### Generic litellm model routing

Any `litellm` model string is supported. Examples:

```yaml
api:
  model: "anthropic/claude-3-5-sonnet-latest"
```

```yaml
api:
  model: "gemini/gemini-1.5-flash"
```

```yaml
api:
  model: "ollama/llama3"
```

## Safety and consent

- On first `unforget ask`, you must accept the disclosure prompt before suggestions are returned.
- AI output is non-deterministic. Review every command before pressing Enter.
- Sensitive values are scrubbed from context before provider calls.

## Troubleshooting

### `unforget error: setup required`

`ask` and hotkey usage are blocked until setup finishes with a successful provider connection test.

```bash
unforget setup
```

After setup succeeds, run your command again:

```bash
unforget ask "echo hello"
```

### `unforget error: consent required`

Accept the disclosure once:

```bash
unforget consent
```

Or run `ask` again and accept the prompt:

```bash
unforget ask "echo hello"
```

### LLM call fails or provider module is missing

Reinstall the tool:

```bash
uv tool install --reinstall "git+https://github.com/aria-karimi/unforget.git"
```

If reinstall fails with hardlink/`Operation not permitted`:

```bash
uv tool install --reinstall --link-mode copy "git+https://github.com/aria-karimi/unforget.git"
```

Optional persistent fix:

```bash
export UV_LINK_MODE=copy
```

If provider dependencies are compiled from source on your system, install Rust:

```bash
curl https://sh.rustup.rs -sSf | sh
```

### Hotkey/integration does not load

First, make sure you reloaded your shell after setup:

```bash
exec "$SHELL"
```

Then check active bindings:

```bash
uf_hotkey_status
```

If bindings are missing, re-bind in the current shell session:

```bash
uf_bind_hotkey
```

If you changed hotkey environment variables manually, reload once:

```bash
export UNFORGET_HOTKEY="\\eu"
export UNFORGET_HOTKEY_FALLBACK="\\eu"
exec "$SHELL"
```

To cancel an in-flight hotkey request while the spinner is visible, press `Ctrl+C`.

### `unforget ask` feels slow

Use the same model when comparing direct API calls vs `unforget ask`.

Quick benchmark:

```bash
bash -lc 'time unforget ask "echo hello"'
```

Optional tuning:

```yaml
context:
  max_files: 12
  stdout_lines: 5
  history_limit: 2
interface:
  show_timing: true
api:
  max_output_tokens: 96
```

### Uninstall and remove local config

Use the unified uninstall command:

```bash
unforget uninstall
```

Behavior:
- prompts for confirmation (`y` or `yes` proceeds)
- removes local config (`~/.config/unforget/config.yaml`)
- removes managed shell integration blocks from rc files
- removes stdout logs
- runs `uv tool uninstall unforget` to remove the tool
- prints reload guidance on success

Manual fallback (if shell integration is not loaded):

```bash
unforget cleanup
uv tool uninstall unforget
exec "$SHELL"
```