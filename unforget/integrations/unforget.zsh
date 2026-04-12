# >>> unforget managed block >>>
UNFORGET_HOTKEY="${UNFORGET_HOTKEY:-^[u}"
UNFORGET_HOTKEY_FALLBACK="${UNFORGET_HOTKEY_FALLBACK:-^[u}"
UNFORGET_STDOUT_LOG="${UNFORGET_STDOUT_LOG:-/tmp/unforget_stdout.log}"
UNFORGET_STDOUT_MAX_LINES="${UNFORGET_STDOUT_MAX_LINES:-2000}"
UNFORGET_SPINNER_DELAY="${UNFORGET_SPINNER_DELAY:-0.12}"

function _unforget_trim_log() {
  [[ -f "$UNFORGET_STDOUT_LOG" ]] || return 0
  local n
  n=$(wc -l < "$UNFORGET_STDOUT_LOG")
  if (( n > UNFORGET_STDOUT_MAX_LINES )); then
    tail -n "$UNFORGET_STDOUT_MAX_LINES" "$UNFORGET_STDOUT_LOG" > "${UNFORGET_STDOUT_LOG}.tmp" && mv "${UNFORGET_STDOUT_LOG}.tmp" "$UNFORGET_STDOUT_LOG"
  fi
}

function _unforget_preexec() {
  print -r -- "\$ $1" >> "$UNFORGET_STDOUT_LOG" 2>/dev/null
}

function _unforget_precmd() {
  print -r -- "[exit:$?]" >> "$UNFORGET_STDOUT_LOG" 2>/dev/null
  _unforget_trim_log
}

autoload -U add-zsh-hook
add-zsh-hook preexec _unforget_preexec
add-zsh-hook precmd _unforget_precmd

function unforget_widget() {
  local user_query suggestion spin_pid ask_rc old_int old_term
  local ask_stderr ask_stderr_output
  local saved_buffer saved_cursor prompt_buffer
  if ! command unforget ready >/dev/null 2>&1; then
    zle -M "unforget: setup required"
    zle redisplay
    return 1
  fi

  zle -I
  saved_buffer="$BUFFER"
  saved_cursor="$CURSOR"
  BUFFER="unforget> "
  CURSOR=${#BUFFER}
  if ! zle recursive-edit; then
    BUFFER="$saved_buffer"
    CURSOR="$saved_cursor"
    zle -M "unforget: cancelled"
    zle redisplay
    return 1
  fi
  prompt_buffer="$BUFFER"
  BUFFER="$saved_buffer"
  CURSOR="$saved_cursor"
  if [[ "$prompt_buffer" == "unforget> "* ]]; then
    user_query="${prompt_buffer#unforget> }"
  else
    user_query="$prompt_buffer"
  fi
  [[ -z "$user_query" ]] && { zle redisplay; return 0; }

  command unforget consent || {
    zle -M "unforget: consent required"
    zle redisplay
    return 1
  }

  ask_stderr="$(mktemp "${TMPDIR:-/tmp}/unforget-ask.XXXXXX")" || return 1

  old_int="$(trap -p INT)"
  old_term="$(trap -p TERM)"
  trap '_unforget_stop_spinner "$spin_pid"; zle -M "unforget: cancelled"; zle redisplay' INT TERM

  _unforget_start_spinner "unforget: thinking"
  spin_pid=$!
  suggestion="$(command unforget ask "$user_query" 2>"$ask_stderr")"
  ask_rc=$?
  if [[ -s "$ask_stderr" ]]; then
    ask_stderr_output="$(cat "$ask_stderr" 2>/dev/null)"
  fi
  rm -f "$ask_stderr" 2>/dev/null || true
  _unforget_stop_spinner "$spin_pid"
  _unforget_restore_trap INT "$old_int"
  _unforget_restore_trap TERM "$old_term"
  if [[ -n "$ask_stderr_output" ]]; then
    print -r -- "$ask_stderr_output" >&2
  fi
  if (( ask_rc != 0 )); then
    zle -M "unforget: request failed (run: uf_hotkey_status)"
    zle redisplay
    return 1
  fi
  LBUFFER+="$suggestion"
  zle reset-prompt
}
zle -N unforget_widget

function _unforget_start_spinner() {
  local msg="${1:-unforget: thinking}"
  (
    local frames=('-' '\' '|' '/')
    local i=1
    while true; do
      print -n -- $'\r'"${msg} ${frames[$i]}" >&2
      i=$(( i % ${#frames} + 1 ))
      sleep "$UNFORGET_SPINNER_DELAY"
    done
  ) &
}

function _unforget_stop_spinner() {
  local pid="$1"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  print -n -- $'\r\033[K' >&2
}

function _unforget_restore_trap() {
  local sig="$1"
  local previous="$2"
  if [[ -n "$previous" ]]; then
    eval "$previous"
  else
    trap - "$sig"
  fi
}

function uf_bind_hotkey() {
  local primary fallback
  primary="$(_unforget_normalize_hotkey "${UNFORGET_HOTKEY}")"
  fallback="$(_unforget_normalize_hotkey "${UNFORGET_HOTKEY_FALLBACK}")"
  bindkey -M emacs "${primary}" unforget_widget
  bindkey -M viins "${primary}" unforget_widget
  bindkey -M emacs "${fallback}" unforget_widget
  bindkey -M viins "${fallback}" unforget_widget
}

function _unforget_normalize_hotkey() {
  local raw="$1"
  if [[ "$raw" == '\\e'* ]]; then
    print -r -- "^[${raw#\\e}"
    return
  fi
  print -r -- "$raw"
}

function uf_hotkey_status() {
  echo "unforget primary hotkey: ${UNFORGET_HOTKEY}"
  echo "unforget fallback hotkey: ${UNFORGET_HOTKEY_FALLBACK}"
  bindkey -M emacs | grep unforget_widget || true
  bindkey -M viins | grep unforget_widget || true
}

uf_bind_hotkey
# <<< unforget managed block <<<
