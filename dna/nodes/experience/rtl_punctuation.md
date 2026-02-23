---
node_id: experience.rtl_punctuation
tags: [rtl, hebrew, punctuation, ui, text, general]
source: rectangles-game button fix, session 2026-02-23
---

# RTL punctuation placement (general insight)

## The problem
In Hebrew (RTL) text, punctuation marks like `!`, `?`, `.` go at the END of the sentence — which visually appears on the LEFT side. When writing Hebrew strings in code, the exclamation mark must be at the end of the string, not the beginning.

## Common mistake
Writing `!אני יודע` instead of `אני יודע!`. In an LTR code editor, putting `!` at the start of the string feels natural, but in RTL rendering it places the mark on the RIGHT (wrong side).

## The rule
**Hebrew punctuation goes at the END of the string in source code**, same as English. The RTL rendering engine handles placing it visually on the left.

- Correct: `אני יודע את הצורה!`
- Wrong: `!אני יודע את הצורה`

## Applies to
All projects with Hebrew UI text — buttons, labels, messages, alerts, status text.
