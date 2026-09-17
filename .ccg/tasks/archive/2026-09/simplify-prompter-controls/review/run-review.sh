#!/usr/bin/env bash
set -u
cd 'E:/Downloads/44456654/teleprompter' || exit 1
task_dir='.ccg/tasks/simplify-prompter-controls/review'
CODEX_TIMEOUT=90000 'C:/Users/RUD/.claude/bin/codeagent-wrapper.exe' --progress --backend claude - 'E:/Downloads/44456654/teleprompter' < "$task_dir/ui-prompt.txt" > "$task_dir/ui.md" 2> "$task_dir/ui.log" &
ui_pid=$!
CODEX_TIMEOUT=90000 'C:/Users/RUD/.claude/bin/codeagent-wrapper.exe' --progress --backend claude - 'E:/Downloads/44456654/teleprompter' < "$task_dir/state-prompt.txt" > "$task_dir/state.md" 2> "$task_dir/state.log" &
state_pid=$!
wait "$ui_pid"
ui_status=$?
wait "$state_pid"
state_status=$?
printf 'UI review exit: %s\nState review exit: %s\n' "$ui_status" "$state_status"
test "$ui_status" -eq 0 && test "$state_status" -eq 0
