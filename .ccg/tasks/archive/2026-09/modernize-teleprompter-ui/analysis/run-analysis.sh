#!/usr/bin/env bash
set -u
cd 'E:/Downloads/44456654/teleprompter' || exit 1
task_dir='.ccg/tasks/modernize-teleprompter-ui/analysis'
CODEX_TIMEOUT=300000 'C:/Users/RUD/.claude/bin/codeagent-wrapper.exe' --progress --backend claude - 'E:/Downloads/44456654/teleprompter' < "$task_dir/ui-prompt.txt" > "$task_dir/ui.md" 2> "$task_dir/ui.log" &
ui_pid=$!
CODEX_TIMEOUT=300000 'C:/Users/RUD/.claude/bin/codeagent-wrapper.exe' --progress --backend claude - 'E:/Downloads/44456654/teleprompter' < "$task_dir/behavior-prompt.txt" > "$task_dir/behavior.md" 2> "$task_dir/behavior.log" &
behavior_pid=$!
wait "$ui_pid"
ui_status=$?
wait "$behavior_pid"
behavior_status=$?
printf 'UI analysis exit: %s\nBehavior analysis exit: %s\n' "$ui_status" "$behavior_status"
test "$ui_status" -eq 0 && test "$behavior_status" -eq 0
