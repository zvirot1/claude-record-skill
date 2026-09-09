# record-skill-local

A Cowork plugin wrapper for `record-skill`: turn a recorded desktop workflow into a reusable
skill that stays **on your machine**, instead of in your cloud account like the built-in
"Record a skill" does.

## What's inside

```
record-skill-local/
├── .claude-plugin/plugin.json
└── skills/record-skill/
    ├── SKILL.md
    └── scripts/
        ├── record.py        cross-platform recorder (mss + pynput + Pillow)
        └── save_skill.py    local installer/validator for drafted skills
```

## Install

Accept the `.plugin` file in chat (press **Save plugin**), then start a **new** session -
plugins load at session start.

Two ways to invoke it:
- `/record-skill` - the slash command.
- Just describe the task: "turn the recording in <folder> into a skill saved on my machine".
  The skill triggers from its description, which is the more reliable route in Cowork.

## The one thing to know

Cowork's default shell runs in a cloud container, so **Claude cannot record your screen for
you** — no display there, and no path to your windows. Reading a finished recording off your disk
does work (Cowork reached the recording folders through its Windows-MCP integration), but the
recording itself you run yourself, in your own terminal:

```powershell
py -3 "$env:USERPROFILE\.claude\skills\record-skill\scripts\record.py"
```
```bash
python3 ~/.claude/skills/record-skill/scripts/record.py
```

Stop with **Ctrl+Shift+Q**. The recording lands in `~/.claude/recordings/<timestamp>/`.
Then point Claude at that folder — or paste `trajectory.md` into the chat if the VM cannot
reach the path — and it drafts the skill from there.

The scripts are bundled in this plugin under `skills/record-skill/scripts/`, so they work even
if you never installed the standalone repo.

## Two destinations, deliberately

- **Claude Code** (CLI and the Code tab) reads skills from `~/.claude/skills`. `save_skill.py`
  installs there.
- **Cowork** does not read that path — it loads skills from plugins. So a skill destined for
  Cowork gets wrapped in a plugin and delivered as a `.plugin` file you install with a button.

Both routes stay on your machine. Neither calls `save_skill` or `propose_skills`.

## Recording flags

| Flag | Use |
|---|---|
| `--mask-typing` | store only the length of typed text, not the text |
| `--duration 120` | auto-stop after N seconds |
| `--monitor 2` / `--all-monitors` | pick a display (default: the one under the mouse) |
| `--stop-key "<ctrl>+<alt>+q"` | if another app owns Ctrl+Shift+Q |
| `--install-deps` | pip install mss, pynput and Pillow on first run |

## Platform notes

Verified on macOS 26 and Windows Server 2022 (Python 3.13). On macOS the terminal needs
Screen Recording **and** Accessibility permission. On Windows, input from windows running
elevated is invisible unless the recorder is elevated too.
