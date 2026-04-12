# >>> unforget managed block >>>
UNFORGET_HOTKEY="${UNFORGET_HOTKEY:-\eu}"
UNFORGET_HOTKEY_FALLBACK="${UNFORGET_HOTKEY_FALLBACK:-\eu}"
UNFORGET_STDOUT_LOG="${UNFORGET_STDOUT_LOG:-/tmp/unforget_stdout.log}"
UNFORGET_STDOUT_MAX_LINES="${UNFORGET_STDOUT_MAX_LINES:-2000}"
UNFORGET_SPINNER_DELAY="${UNFORGET_SPINNER_DELAY:-0.12}"

_unforget_trim_log() {
  [[ -f "$UNFORGET_STDOUT_LOG" ]] || return 0
  local n
  n=$(wc -l < "$UNFORGET_STDOUT_LOG")
  if [[ "$n" -gt "$UNFORGET_STDOUT_MAX_LINES" ]]; then
    tail -n "$UNFORGET_STDOUT_MAX_LINES" "$UNFORGET_STDOUT_LOG" > "${UNFORGET_STDOUT_LOG}.tmp" && mv "${UNFORGET_STDOUT_LOG}.tmp" "$UNFORGET_STDOUT_LOG"
  fi
}

_unforget_log_preexec() {
  [[ -n "$BASH_COMMAND" ]] && printf '$ %s\n' "$BASH_COMMAND" >> "$UNFORGET_STDOUT_LOG" 2>/dev/null
}

_unforget_log_precmd() {
  local st="$?"
  printf '[exit:%s]\n' "$st" >> "$UNFORGET_STDOUT_LOG" 2>/dev/null
  _unforget_trim_log
}

trap '_unforget_log_preexec' DEBUG
PROMPT_COMMAND="_unforget_log_precmd${PROMPT_COMMAND:+; $PROMPT_COMMAND}"

_unforget_widget() {
  local user_query suggestion read_rc tty_state
  local ask_rc old_int old_term ask_stderr ask_stderr_output

  if ! command unforget ready; then
    return 1
  fi

  tty_state="$(stty -g < /dev/tty 2>/dev/null)" || return 1
  stty sane < /dev/tty 2>/dev/null || true
  IFS= read -r -p "unforget> " user_query < /dev/tty
  read_rc=$?
  if (( read_rc != 0 )); then
    [[ -n "$tty_state" ]] && stty "$tty_state" < /dev/tty 2>/dev/null || true
    return 1
  fi
  [[ -z "$user_query" ]] && return 0

  command unforget consent || {
    [[ -n "$tty_state" ]] && stty "$tty_state" < /dev/tty 2>/dev/null || true
    return 1
  }
  [[ -n "$tty_state" ]] && stty "$tty_state" < /dev/tty 2>/dev/null || true

  ask_stderr="$(mktemp "${TMPDIR:-/tmp}/unforget-ask.XXXXXX")" || return 1

  old_int="$(trap -p INT)"
  old_term="$(trap -p TERM)"
  trap '_unforget_clear_status; printf "\n" >&2' INT TERM

  suggestion="$(_unforget_run_with_spinner "$user_query" "$ask_stderr")"
  ask_rc=$?
  if [[ -s "$ask_stderr" ]]; then
    ask_stderr_output="$(cat "$ask_stderr" 2>/dev/null)"
  fi
  rm -f "$ask_stderr" 2>/dev/null || true
  _unforget_clear_status
  _unforget_restore_trap INT "$old_int"
  _unforget_restore_trap TERM "$old_term"
  if [[ -n "$ask_stderr_output" ]]; then
    printf '%s' "$ask_stderr_output" >&2
    [[ "$ask_stderr_output" == *$'\n' ]] || printf '\n' >&2
  fi
  if (( ask_rc != 0 )); then
    printf 'unforget: request failed\n' >&2
    return 1
  fi
  READLINE_LINE="${READLINE_LINE}${suggestion}"
  READLINE_POINT="${#READLINE_LINE}"
}

_unforget_run_with_spinner() {
  local query="$1"
  local stderr_path="$2"
  python3 - "$query" "${UNFORGET_SPINNER_DELAY}" "$stderr_path" <<'PY'
import subprocess
import sys
import time

query = sys.argv[1]
try:
  delay = float(sys.argv[2])
except (IndexError, ValueError):
  delay = 0.12
stderr_path = sys.argv[3]

frames = "-\\|/"
proc = subprocess.Popen(
  ["unforget", "ask", query],
  stdout=subprocess.PIPE,
  stderr=subprocess.PIPE,
  text=True,
)

spinner_i = 0
return_code = 1
stdout_text = ""
stderr_text = ""
try:
  while proc.poll() is None:
    frame = frames[spinner_i % len(frames)]
    spinner_i += 1
    print(f"\runforget: thinking {frame}", end="", file=sys.stderr, flush=True)
    time.sleep(delay)
  stdout_text, stderr_text = proc.communicate()
  return_code = proc.returncode
except KeyboardInterrupt:
  if proc.poll() is None:
    proc.terminate()
    try:
      proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
      proc.kill()
  return_code = 130
finally:
  print("\r\033[K", end="", file=sys.stderr, flush=True)

if stderr_text:
  with open(stderr_path, "w", encoding="utf-8") as handle:
    handle.write(stderr_text)
if stdout_text:
  print(stdout_text, end="")
sys.exit(return_code)
PY
}

_unforget_clear_status() {
  printf '\r\033[K' >&2
}

_unforget_restore_trap() {
  local sig="$1"
  local previous="$2"
  if [[ -n "$previous" ]]; then
    eval "$previous"
  else
    trap - "$sig"
  fi
}

uf_bind_hotkey() {
  local primary fallback
  primary="$(_unforget_normalize_hotkey "${UNFORGET_HOTKEY}")"
  fallback="$(_unforget_normalize_hotkey "${UNFORGET_HOTKEY_FALLBACK}")"
  bind -x "\"${primary}\":_unforget_widget"
  if [[ -n "${fallback}" ]]; then
    bind -x "\"${fallback}\":_unforget_widget"
  fi
}

_unforget_normalize_hotkey() {
  local raw="${1:-}"
  if [[ "$raw" =~ ^\^\[(.)$ ]]; then
    printf '\\e%s' "${BASH_REMATCH[1]}"
    return
  fi
  if [[ "$raw" =~ ^\^(.)$ ]]; then
    printf '\\C-%s' "${BASH_REMATCH[1],,}"
    return
  fi
  printf '%s' "$raw"
}

uf_hotkey_status() {
  echo "unforget primary hotkey: ${UNFORGET_HOTKEY}"
  echo "unforget fallback hotkey: ${UNFORGET_HOTKEY_FALLBACK}"
  bind -P | grep -i "_unforget_widget" || true
}

uf_bind_hotkey
# <<< unforget managed block <<<
