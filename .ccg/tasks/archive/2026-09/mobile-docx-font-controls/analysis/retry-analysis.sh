#!/usr/bin/env bash
set -u
cd 'E:/Downloads/44456654/teleprompter' || exit 1
task='.ccg/tasks/mobile-docx-font-controls/analysis'
wrapper='C:/Users/RUD/.claude/bin/codeagent-wrapper.exe'
"$wrapper" --progress --backend claude - "$PWD" > "$task/material-ui-retry.md" 2> "$task/material-ui-retry.log" <<'UI_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/analyzer.md
<TASK>
请只读审阅 .ccg/tasks/mobile-docx-font-controls/requirements.md 和 plan.md，并参考 index.html、styles.css。用户要将提词器改为 Material Design 风格的移动端单文稿页面，去掉预览，把设置移到右上角弹窗，同时支持 DOCX 导入和提词时调整字号。请用中文简短评价计划的移动端布局和弹窗交互，列出最多五个具体注意事项。不要修改文件。
</TASK>
OUTPUT: 300 字以内的可执行建议。
UI_EOF
ui_pid=$!
"$wrapper" --progress --backend claude - "$PWD" > "$task/material-behavior-retry.md" 2> "$task/material-behavior-retry.log" <<'APP_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/analyzer.md
<TASK>
请只读审阅 .ccg/tasks/mobile-docx-font-controls/requirements.md 和 plan.md，并参考 app.js。用户要将提词器改为 Material Design 风格的移动端单文稿页面，去掉预览，把设置移到右上角弹窗，同时支持 DOCX 导入和提词时调整字号。请用中文简短评价实现计划，列出最多五个文稿导入、播放状态、字号变化和键盘操作方面的注意事项。不要修改文件。
</TASK>
OUTPUT: 300 字以内的可执行建议。
APP_EOF
app_pid=$!
wait "$ui_pid"
ui_status=$?
wait "$app_pid"
app_status=$?
printf 'Retried analysis exit codes: ui=%s app=%s\n' "$ui_status" "$app_status"
test "$ui_status" -eq 0 && test "$app_status" -eq 0
