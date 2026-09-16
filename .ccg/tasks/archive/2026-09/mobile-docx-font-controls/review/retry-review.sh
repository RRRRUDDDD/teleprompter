#!/usr/bin/env bash
set -u
cd 'E:/Downloads/44456654/teleprompter' || exit 1
task='.ccg/tasks/mobile-docx-font-controls/review'
wrapper='C:/Users/RUD/.claude/bin/codeagent-wrapper.exe'
# Scoped fallback: the default Claude service returned no report / exit 1.
# Its earlier no-content response recommended claude-opus-4.8. No global configuration changes.
ANTHROPIC_MODEL=claude-opus-4.8 CODEX_TIMEOUT=180000 "$wrapper" --progress --backend claude - "$PWD" > "$task/ui-retry.md" 2> "$task/ui-retry.log" <<'UI_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/reviewer.md
<TASK>
只读审查 index.html、styles.css、app.js 的 git diff。最终需求：Material Design 手机优先单文稿页面，无预览，右上角设置弹窗，TXT/DOCX 导入，提词按钮改为调整大小，轻点阅读画面暂停。检查移动端布局和键盘/弹窗/触控。新增 --viewport-offset-top 使软键盘打开时弹窗保持可见。浏览器交互和截图已验证。不要修改文件。
</TASK>
OUTPUT: 简短 Critical/Warning/Info 报告，最多 5 项、有代码证据和行号；无问题则明确说明。
UI_EOF
ui_pid=$!
ANTHROPIC_MODEL=claude-opus-4.8 CODEX_TIMEOUT=180000 "$wrapper" --progress --backend claude - "$PWD" > "$task/behavior-retry.md" 2> "$task/behavior-retry.log" <<'APP_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/reviewer.md
<TASK>
只读审查 app.js 的 git diff 和新增 document-import.js 全文。最终需求：本地 TXT/DOCX 导入、设置弹窗、提词中调整字号且保持进度、点击阅读画面暂停。检查导入错误保护、异步结果、文字提取和播放生命周期。ZIP 仅解压主文档，校验长度/CRC；最近已补齐 Word noBreakHyphen。36 项浏览器回归和72项导入检查已覆盖主要行为。不要修改文件。
</TASK>
OUTPUT: 简短 Critical/Warning/Info 报告，最多 5 项、有代码证据和行号；无问题则明确说明。
APP_EOF
app_pid=$!
wait "$ui_pid"
ui_status=$?
wait "$app_pid"
app_status=$?
printf 'Retried review exit codes: ui=%s behavior=%s\n' "$ui_status" "$app_status"
test "$ui_status" -eq 0 && test "$app_status" -eq 0
