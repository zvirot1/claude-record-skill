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
    ├── save_skill.py        installs a drafted skill locally (user or project scope)
    ├── package_plugin.py    wraps a skill as a .plugin so Cowork can run it too
    └── marker_view.py       builds the pages that show each marker's screenshot in the pane
install.sh                   macOS / Linux installer
install.ps1                  Windows installer
```

## Install on a new machine

Two things travel, and the first is needed even if you only ever use Cowork.

### 1. The recorder, on the machine itself

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
macOS needs a step Windows does not: give your terminal app **Screen Recording** *and*
**Accessibility** permission (System Settings → Privacy & Security). Without them the recorder
starts normally and produces an empty recording.

The installer copies `skills/*` into `~/.claude/skills` (Windows:
`%USERPROFILE%\.claude\skills`) and pip-installs `mss`, `pynput` and `pillow`. Nothing else is
required for Claude Code — open a new session and type `/record-skill`.

### 2. For Cowork, additionally

Install `cowork-plugin/dist/record-skill-local.plugin` — it comes with the clone — using **Save
plugin**, then start a new session.

This does *not* replace step 1. Cowork's default shell is a cloud container, so the plugin's own
copy of `record.py` has no screen to capture and no path to your windows. The plugin supplies the
instructions and the `/record-skill` command; the recorder that actually runs is the one in
`~/.claude/skills`. **A plugin on its own records nothing.**

It may already be listed for you: the local manifest holds a server-issued plugin id, which
suggests "My Uploads" is account-level rather than per-machine (only the local copy has been
verified). Check the list before uploading again.

Nothing else needs to move. `cowork-plugin/dist/` also holds `calc-exercise`, `latest-email` and
`save-url` — those are skills built to prove the pipeline works end to end, not parts of the tool.

## Use

1. Record in your own terminal (needs the foreground):
   - Windows: `py -3 "$env:USERPROFILE\.claude\skills\record-skill\scripts\record.py"`
   - macOS: `python3 ~/.claude/skills/record-skill/scripts/record.py`
   Flags: `--note "what this is for"` (states the intent), `--mask-typing` (don't store typed
   text), `--mask-titles` (keep which app, drop window titles — implied by `--mask-typing`),
   `--duration 120`, `--monitor 2`, `--all-monitors`, `--marker-key`, `--stop-key`,
   `--no-prompt` (ask nothing at the end; required when Claude launches it detached).
   Press **Ctrl+Shift+M** while recording to mark a moment; the recorder asks what each marker
   was after it stops, and the answer is filed at the time you pressed it. There is no audio
   capture, so these are how intent gets into a recording.
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

## Running a built skill in Cowork

Claude Code loads skills from `~/.claude/skills`; Cowork loads them from plugins only. Build once,
deliver twice:

```bash
python3 ~/.claude/skills/record-skill/scripts/save_skill.py <draft> --scope user    # Claude Code
python3 ~/.claude/skills/record-skill/scripts/package_plugin.py <skill> --out dist  # Cowork
```

The second writes `dist/<name>.plugin`; install it in Cowork with **Save plugin** and start a new
session. It also generates a `commands/<name>.md` wrapper, because a `skills/` folder alone gets no
slash command in Cowork.

## Cowork

Cowork does not read `~/.claude/skills` at all; it loads skills from plugins.
`cowork-plugin/record-skill-local/` is the plugin source and
`cowork-plugin/dist/record-skill-local.plugin` the installable build. Rebuild it after editing the
skill, then **Save plugin** again:

```bash
cd cowork-plugin/record-skill-local && zip -r ../dist/record-skill-local.plugin . -x "*.DS_Store"
```

Whether a skill built this way can then *act* on the desktop depends on what the session has
attached, so test rather than assume: a Cowork session drove `calc.exe` through its Windows-MCP
integration after this README claimed the desktop was out of reach. The cloud container genuinely
cannot reach it; a host surface can.

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
| a built skill running in Cowork - slash command, description trigger, Gmail connector, host desktop via MCP, and a privacy prompt before writing | 4-of-4 checklist, see HANDOFF.md |
