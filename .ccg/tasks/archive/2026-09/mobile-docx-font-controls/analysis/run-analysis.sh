#!/usr/bin/env bash
set -u
cd 'E:/Downloads/44456654/teleprompter' || exit 1
task='.ccg/tasks/mobile-docx-font-controls/analysis'
wrapper='C:/Users/RUD/.claude/bin/codeagent-wrapper.exe'
"$wrapper" --progress --backend claude - "$PWD" > "$task/mobile.md" 2> "$task/mobile.log" <<'MOBILE_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/analyzer.md
<TASK>
Read-only analysis; do not edit any files and do not delegate. Read index.html, styles.css, app.js and .ccg/spec/frontend/index.md in this static no-build teleprompter project.
User asks in Chinese: prioritize mobile adaptation, allow DOCX imports in addition to TXT, and replace the player Pause button with a font-size adjustment because tapping the reading area already pauses.
Focus on mobile UX, 320x568 and 390x844 portrait, 844x390 landscape, soft keyboard, safe areas, touch target sizes, accessible in-player font size controls and existing gesture/pause interaction. Identify concrete minimal changes, pitfalls, and useful browser acceptance scenarios. Preserve desktop UI. Files stay local. Do not redesign unrelated features.
</TASK>
OUTPUT: Concise actionable analysis with file references, recommendations and test scenarios. No edits.
MOBILE_EOF
mobile_pid=$!
"$wrapper" --progress --backend claude - "$PWD" > "$task/import-playback.md" 2> "$task/import-playback.log" <<'BEHAVIOR_EOF' &
ROLE_FILE: C:/Users/RUD/.claude/.ccg/prompts/claude/analyzer.md
<TASK>
Read-only analysis; do not edit any files and do not delegate. Read index.html, styles.css, app.js and .ccg/spec/frontend/index.md in this static no-build teleprompter project.
User asks in Chinese: prioritize mobile adaptation, allow DOCX imports in addition to TXT, and replace the player Pause button with a font-size adjustment because tapping the reading area already pauses.
Focus independently on robust local DOCX plain-text extraction (vendored library versus a light unzip/XML parser, dependency/privacy/static Pages constraints), corrupt/empty/large files, import races and undo, and preserving reading position/playback state when font size changes. Analyze relevant lifecycle/fullscreen/keyboard constraints and recommend minimal reliable implementation and meaningful tests.
</TASK>
OUTPUT: Concise actionable analysis with file references, recommendations and test scenarios. No edits.
BEHAVIOR_EOF
behavior_pid=$!
wait "$mobile_pid"
mobile_status=$?
wait "$behavior_pid"
behavior_status=$?
printf 'Analysis exit codes: mobile=%s import-playback=%s\n' "$mobile_status" "$behavior_status"
test "$mobile_status" -eq 0 && test "$behavior_status" -eq 0
