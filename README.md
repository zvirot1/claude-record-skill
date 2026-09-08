# claude-record-skill

A **local** replacement for Claude Desktop's built-in **"Record a skill"** feature.
Same idea (watch a demonstration of a desktop workflow, turn it into a reusable skill),
but the skill is written to **this machine** under `~/.claude/skills` instead of the
cloud account. Works with Claude Code on **macOS, Windows and Linux**.

```
skills/record-skill/
├── SKILL.md                 what Claude does when you type /record-skill
└── scripts/
    ├── record.py            cross-platform recorder (screenshots + mouse + keyboard)
    └── save_skill.py        installs a drafted skill locally (user or project scope)
install.sh                   macOS / Linux installer
install.ps1                  Windows installer
```

## Install

**Windows** (PowerShell):
```powershell
git clone https://github.com/zvirot1/claude-record-skill.git
cd claude-record-skill
Set-ExecutionPolicy -Scope Process Bypass; .\install.ps1
```
No Python? `winget install Python.Python.3.12`, then re-run.

**macOS / Linux**:
```bash
git clone https://github.com/zvirot1/claude-record-skill.git
cd claude-record-skill && ./install.sh
```
macOS: give your terminal app **Screen Recording** and **Accessibility** permission
(System Settings → Privacy & Security), otherwise input is not captured.

Then open a new Claude Code session and type `/record-skill`.

## Use

1. Record in your own terminal (needs the foreground):
   - Windows: `py -3 "$env:USERPROFILE\.claude\skills\record-skill\scripts\record.py"`
   - macOS: `python3 ~/.claude/skills/record-skill/scripts/record.py`
   Flags: `--mask-typing` (don't store typed text), `--duration 120`, `--monitor 2`, `--all-monitors`.
   Stop with **Ctrl+Shift+Q** or Ctrl+C. Output: `~/.claude/recordings/<timestamp>/trajectory.md` + `shots/`.
2. In Claude Code: `/record-skill` and point it at the recording folder. Claude analyses the
   outcomes (not the clicks), drafts `<name>/SKILL.md`, shows it, and saves it locally with `save_skill.py`.
3. Use the new skill with `/<name>`.

## How it mirrors the built-in feature

The desktop app's recorder emits a `<watch-record-demonstration durationMs steps images platform>`
message: lines like `[1.2s] full screen (...)` / `[3.4s] changed region (...)` interleaved with
screenshots, plus typed/clicked actions, and then tells Claude to call the Cowork tools
`propose_skills` / `save_skill`, which store the skill in the account. `record.py` produces the
same trajectory format; `SKILL.md` forbids those two tools and writes files instead.

## Cowork

Cowork runs its tools inside a Linux VM with no access to the host desktop, so the recorder
cannot run there - and Cowork does not read `~/.claude/skills` at all; it loads skills from
plugins. `cowork-plugin/record-skill-local/` wraps the skill as a plugin for exactly that, and
`cowork-plugin/dist/record-skill-local.plugin` is the installable file. Rebuild it with:

```bash
cd cowork-plugin/record-skill-local && zip -r ../dist/record-skill-local.plugin . -x "*.DS_Store"
```

You still run `record.py` yourself on the host; only the drafted skill crosses into Cowork, and
only if it does not depend on desktop clicks (the VM cannot click on your desktop).

## Background

`SESSION-LOG.md` records how this was built: what the built-in feature does internally, why the
design looks like this, and the three bugs that only showed up in a live recording test.

## Continuing work on another machine (handoff for Claude)

Open the cloned repo as the working folder in Claude Code and paste:

> Read `HANDOFF.md` and `SESSION-LOG.md`, then run the verification steps for this OS. Fix anything
> that fails directly in `skills/record-skill/`, re-run `install.*`, and commit the fixes.

## Status

| Verified | Platform |
|---|---|
| screenshot capture, per-monitor selection, click/typing/shortcut capture, Ctrl+Shift+Q stop, save_skill install/list/validation | macOS 26 (Python 3.12) |
| everything above except DPI scaling (this box runs at 100%) | Windows Server 2022 (Python 3.13) — see HANDOFF.md for the Windows-specific fixes |
