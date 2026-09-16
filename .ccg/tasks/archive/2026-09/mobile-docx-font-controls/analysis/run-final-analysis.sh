#!/usr/bin/env bash
set -u
cd 'E:/Downloads/44456654/teleprompter' || exit 1
task='.ccg/tasks/mobile-docx-font-controls/analysis'
wrapper='C:/Users/RUD/.claude/bin/codeagent-wrapper.exe'
"$wrapper" --progress --backend claude - "$PWD" > "$task/material-ui.md" 2> "$task/material-ui.log" <<'MOBILE_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/analyzer.md
<TASK>
Read-only, no file edits, no delegation. User UPDATED the request: Material Design (MD) mobile-first style, delete the preview page, make the home console primarily a draft editor, and move ALL settings into a top-right settings popup. Still add local DOCX alongside TXT import and replace the reader Pause toolbar button with font-size adjustment; tap on reading area pauses/resumes.
Read .ccg/tasks/mobile-docx-font-controls/requirements.md, index.html, styles.css, app.js. Earlier frontend spec's tabs/two-column/preview requirements are superseded by the user. Keep no-build static deployment and local privacy. Proposed UI: one large draft editor + fixed mobile Start button, Material filled/tonal buttons, native settings dialog as mobile bottom sheet and centered desktop modal, in-reader size slider with +/- and no pause toolbar button.
Identify only concrete critical design/interaction constraints at 320x568, 390x844, 844x390 including soft keyboard, accessible dialog focus and toolbar sizing. Provide a concise recommendation for implementation splitting by file ownership.
</TASK>
OUTPUT: At most 500 words of actionable analysis. Do not implement.
MOBILE_EOF
mobile_pid=$!
"$wrapper" --progress --backend claude - "$PWD" > "$task/material-behavior.md" 2> "$task/material-behavior.log" <<'BEHAVIOR_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/analyzer.md
<TASK>
Read-only, no file edits, no delegation. User UPDATED the request: Material Design mobile-first single draft console; delete ALL preview UI/logic/tabs; settings accessed in a top-right native dialog. Still support local TXT + DOCX and replace reader pause toolbar button with live font-size adjustment; tapping reading area still pauses/resumes.
Read .ccg/tasks/mobile-docx-font-controls/requirements.md, app.js, index.html and styles.css. Earlier spec for preview/tabs/two-column is superseded. No build/backend/CDN. Proposed separation: parent owns HTML/CSS; one implementer owns app.js lifecycle/settings/playback; one owns document-import.js + a pinned local ZIP library; another owns browser verification. Potential importer: small vendored fflate to extract only bounded word/document.xml, DOMParser to preserve paragraph/manual break/tab/table text, user friendly failures. Alternative mammoth 1.12.3 bundle is 637KB and raw text drops manual line breaks, so evaluate tradeoff concisely. Important risks: stale async imports replacing edits, ZIP expansion, font changes preserving reading progress/end detection, keyboard events not hijacking slider keys, settings dialog focus/escape and removal of preview references.
</TASK>
OUTPUT: At most 500 words of actionable constraints and tests. Do not implement.
BEHAVIOR_EOF
behavior_pid=$!
wait "$mobile_pid"
mobile_status=$?
wait "$behavior_pid"
behavior_status=$?
printf 'Final analysis exit codes: material-ui=%s material-behavior=%s\n' "$mobile_status" "$behavior_status"
test "$mobile_status" -eq 0 && test "$behavior_status" -eq 0
