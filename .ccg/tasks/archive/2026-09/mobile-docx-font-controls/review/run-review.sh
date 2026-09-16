#!/usr/bin/env bash
set -u
cd 'E:/Downloads/44456654/teleprompter' || exit 1
task='.ccg/tasks/mobile-docx-font-controls/review'
wrapper='C:/Users/RUD/.claude/bin/codeagent-wrapper.exe'
"$wrapper" --progress --backend claude - "$PWD" > "$task/ui.md" 2> "$task/ui.log" <<'UI_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/reviewer.md
<TASK>
请审查当前提词器网页的最终改动，只读，不修改文件。用户要求 Material Design 移动端单文稿控制台，删除预览页，右上角设置弹窗，支持 TXT 与 DOCX 导入，提词工具栏将暂停改为调整大小（点击阅读区域仍暂停）。
运行 git diff -- index.html styles.css app.js README.md，读取 .ccg/tasks/mobile-docx-font-controls/requirements.md 及 tests/verify_ui.py。重点检查 320px 窄屏、390px 竖屏、844x390 横屏布局，原生设置弹窗的焦点/滚动，字号面板的触控/键盘隔离，以及已删除预览是否有残留依赖。截图在 tests/artifacts/chromium。不要按旧的双栏/预览规范提出回退要求。
</TASK>
OUTPUT: Critical/Warning/Info 分级报告，引用文件行号。仅报告可复现或有明确代码证据的问题，最多 8 项。若无问题请直说。
UI_EOF
ui_pid=$!
"$wrapper" --progress --backend claude - "$PWD" > "$task/behavior.md" 2> "$task/behavior.log" <<'APP_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/reviewer.md
<TASK>
请审查当前提词器网页的最终改动，只读，不修改文件。用户要求 Material Design 移动端单文稿控制台，删除预览页，右上角设置弹窗，支持 TXT 与 DOCX 导入，提词工具栏将暂停改为调整大小（点击阅读区域仍暂停）。
运行 git diff -- app.js index.html，完整读取新增 document-import.js、vendor/README.md 及 tests/verify_ui.py。重点独立检查 DOCX 文字提取与边界错误处理、导入异步状态和文稿保存、字号变化的阅读进度/结束条件、倒计时/全屏/键盘/手柄生命周期。仅本机解析，无后端。当前普通文档导入和主要浏览器交互测试已通过。
</TASK>
OUTPUT: Critical/Warning/Info 分级报告，引用文件行号。仅报告可复现或有明确代码证据的问题，最多 8 项。若无问题请直说。
APP_EOF
app_pid=$!
wait "$ui_pid"
ui_status=$?
wait "$app_pid"
app_status=$?
printf 'Review exit codes: ui=%s behavior=%s\n' "$ui_status" "$app_status"
test "$ui_status" -eq 0 && test "$app_status" -eq 0
