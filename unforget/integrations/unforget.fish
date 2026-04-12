# >>> unforget managed block >>>
set -q UNFORGET_HOTKEY; or set -g UNFORGET_HOTKEY \eu
set -q UNFORGET_HOTKEY_FALLBACK; or set -g UNFORGET_HOTKEY_FALLBACK \eu
set -q UNFORGET_STDOUT_LOG; or set -g UNFORGET_STDOUT_LOG /tmp/unforget_stdout.log
set -q UNFORGET_STDOUT_MAX_LINES; or set -g UNFORGET_STDOUT_MAX_LINES 2000
set -q UNFORGET_SPINNER_DELAY; or set -g UNFORGET_SPINNER_DELAY 0.12

function _unforget_trim_log
    if test -f "$UNFORGET_STDOUT_LOG"
        set n (wc -l < "$UNFORGET_STDOUT_LOG")
        if test "$n" -gt "$UNFORGET_STDOUT_MAX_LINES"
            tail -n "$UNFORGET_STDOUT_MAX_LINES" "$UNFORGET_STDOUT_LOG" > "$UNFORGET_STDOUT_LOG.tmp"
            mv "$UNFORGET_STDOUT_LOG.tmp" "$UNFORGET_STDOUT_LOG"
        end
    end
end

function _unforget_log --on-event fish_postexec
    echo "[exit:$status]" >> "$UNFORGET_STDOUT_LOG" 2>/dev/null
    _unforget_trim_log
end

function unforget_widget
    set -l spin_pid
    set -l ask_status 0
    set -l ask_stderr
    set -l ask_stderr_output
    command unforget ready >/dev/null 2>&1
    or begin
        echo "unforget: setup required" >&2
        return 1
    end

    read -P "unforget> " user_query
            if not string match -q "*\n" -- "$ask_stderr_output"
                printf "\n" >&2
            end
    test -n "$user_query"; or return 0

    command unforget consent
    or begin
        echo "unforget: consent required" >&2
        return 1
    end

    _unforget_start_spinner "unforget: thinking"
    set spin_pid $last_pid
    set -g __unforget_spin_pid "$spin_pid"
    function __unforget_on_int --on-signal INT
        _unforget_stop_spinner "$__unforget_spin_pid"
        set -e __unforget_spin_pid
        functions -e __unforget_on_int
    end

    if set -q TMPDIR
        set ask_stderr (mktemp "$TMPDIR/unforget-ask.XXXXXX" 2>/dev/null)
    else
        set ask_stderr (mktemp /tmp/unforget-ask.XXXXXX 2>/dev/null)
    end
    if test -z "$ask_stderr"
        _unforget_stop_spinner "$spin_pid"
        set -e __unforget_spin_pid
        functions -e __unforget_on_int
        return 1
    end

    set suggestion (command unforget ask "$user_query" 2> "$ask_stderr")
    set ask_status $status
    if test -s "$ask_stderr"
        set ask_stderr_output (string collect < "$ask_stderr")
    end
    rm -f "$ask_stderr" 2>/dev/null
    _unforget_stop_spinner "$spin_pid"
    set -e __unforget_spin_pid
    functions -e __unforget_on_int

    if test -n "$ask_stderr_output"
        printf "%s" "$ask_stderr_output" >&2
    end

    if test "$ask_status" -ne 0
        _unforget_stop_spinner "$spin_pid"
        echo "unforget: request failed" >&2
        return 1
    end
    commandline -i -- "$suggestion"
end

function _unforget_start_spinner
    set -l msg "$argv[1]"
    test -n "$msg"; or set msg "unforget: thinking"
    while true
        for frame in '-' '\' '|' '/'
            printf "\r%s %s" "$msg" "$frame" >&2
            sleep "$UNFORGET_SPINNER_DELAY"
        end
    end &
end

function _unforget_stop_spinner
    set -l pid "$argv[1]"
    if test -n "$pid"
        kill "$pid" >/dev/null 2>&1
    end
    printf "\r\033[K" >&2
end

function uf_bind_hotkey
    set -l primary (_unforget_normalize_hotkey "$UNFORGET_HOTKEY")
    set -l fallback (_unforget_normalize_hotkey "$UNFORGET_HOTKEY_FALLBACK")
    for mode in default insert visual
        bind -M $mode $primary unforget_widget
        bind -M $mode $fallback unforget_widget
    end
end

function _unforget_normalize_hotkey
    set -l raw "$argv[1]"
    if string match -rq '^\^\[[[:alnum:]]$' -- "$raw"
        set -l ch (string sub -s 3 -l 1 -- "$raw")
        echo "\\e$ch"
        return
    end
    if string match -rq '^\^[[:alpha:]]$' -- "$raw"
        set -l ch (string lower (string sub -s 2 -l 1 -- "$raw"))
        echo "\\c$ch"
        return
    end
    echo "$raw"
end

function uf_hotkey_status
    echo "unforget primary hotkey: $UNFORGET_HOTKEY"
    echo "unforget fallback hotkey: $UNFORGET_HOTKEY_FALLBACK"
    bind | grep unforget_widget
end

uf_bind_hotkey
# <<< unforget managed block <<<
