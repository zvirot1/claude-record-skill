---
description: Turn a recorded desktop workflow into a local skill
argument-hint: [recording-folder-or-nothing]
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/record-skill/SKILL.md` and follow it exactly. It is the
authoritative instructions for this task; this command only exists so the workflow is reachable
as a slash command.

The user said: $ARGUMENTS

If that names a recording folder, start at step 2 (read the trajectory). If it is empty, start at
step 1 (tell the user how to record, and wait — you cannot record the screen yourself).

Never call `save_skill` or `propose_skills`. The whole point is that the skill stays on this
machine.
