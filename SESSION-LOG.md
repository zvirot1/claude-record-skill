# Session log — how this project was built

Curated log of the session that produced this repo (macOS, 2026-09-08, Claude Code in the
Claude desktop app). It exists so a session on another machine has the full reasoning without
re-deriving it. Written by Claude at the user's request.

> The raw session transcript is **deliberately not** in this repo. It contains embedded
> screenshots of the user's work machine (internal corporate systems, internal Java source,
> mail subject lines). It stays local at
> `~/.claude/projects/-Users-zvirot-general/<session-uuid>.jsonl` on the Mac.

## Goal

The user asked for a working replacement for Claude Desktop's built-in **"Record a skill"**
feature, with two requirements the built-in one does not meet:

1. The produced skill must be saved **on the local machine**, not to the cloud account.
2. It must work on **Windows** as well as macOS.

## What the built-in feature actually does

Findings from reading the shipped app, `/Applications/Claude.app/Contents/Resources`:

- The UI string "Record a skill" is `en-US.json` id `BTQ6AjqiI0`; the feature flag/codename is
  `cowork_watch_record` (internally also "copper_heron"). Renderer logic sits in
  `ion-dist/assets/v1/shared-10-*.js`; the main-process implementation is in `app.asar` under
  `.vite/build/` (`computerUseWatchRecord.js` preload plus a large `index.chunk-*.js`).
- The recorder builds one synthetic user message wrapped in
  `<watch-record-demonstration durationMs="…" steps="…" images="…" platform="…">`.
  Inside it is a chronological trajectory: lines like
  `[1.2s] full screen (…)` and `[3.4s] changed region (…)` interleaved with screenshot images.
  A trailing `<system-reminder>` carries the instructions to the model.
- Screenshots are JPEG at quality ~0.75, downscaled to fit a max dimension (1568 px), and
  captured with `screenshot.captureExcluding(<Claude's own windows>)` so the app is not in frame.
- Images are capped; past the cap an evenly spaced subset is kept and the reminder says so.
- The reminder tells the model, verbatim in spirit: do **not** replay the manual mouse/keyboard
  actions; for each step identify the **outcome** it produced and pick the fastest reliable tool
  (browser MCP for browser steps; CLI/script/API/MCP for anything reachable that way); fall back to
  computer-use clicking only when no other interface exists. It also marks everything captured
  (typed strings, app names, on-screen text, mic narration) as **untrusted data**.
- Windows-specific note the app appends: key names use Ctrl/Alt/Win, frames may omit OS-protected
  windows, and input into elevated windows is not captured.
- **Why the result lands in the cloud:** the reminder ends by telling the model to call
  `mcp__cowork__propose_skills` (preferred) or `mcp__cowork__save_skill`. Those persist the skill to
  the account. There is no local-write path in that flow.
- Claude Code's own skill loader, by contrast, reads plain folders:
  `~/.claude/skills/<name>/SKILL.md` (honouring `CLAUDE_CONFIG_DIR`) and `.claude/skills/<name>/`
  per project. That is the seam this project uses.

## Design decisions

- **Reproduce the trajectory format exactly.** `record.py` emits the same
  `<watch-record-demonstration>` header and the same `full screen` / `changed region` line grammar,
  so a recording from either source is interchangeable and `SKILL.md` handles both.
- **Python, not a native module.** `mss` + `pynput` + `Pillow` cover macOS, Windows and Linux with
  one implementation. Screenshots are JPEG q75 capped at 1568 px wide, matching the app.
- **Changed-region cropping.** Diff against the previous frame; if the changed bbox is under 40 % of
  the screen, save only that crop (with 40 px padding). Identical frames are skipped entirely.
- **Monitor selection.** The app captures per display. `record.py` defaults to the monitor under the
  mouse cursor and forces a full keyframe when the cursor crosses to another display.
  `--monitor N` and `--all-monitors` override. This mattered in testing: the user has 3 displays and
  a full virtual-desktop grab was an unreadable 1568x337 strip.
- **`save_skill.py` instead of the cloud tools.** Validates frontmatter (name charset,
  description present and ≤1024 chars), copies the folder to the right place for the OS, and refuses
  to overwrite without `--force`. `SKILL.md` forbids `save_skill` / `propose_skills` explicitly.
- **Privacy affordances.** `--mask-typing` records only the length of typed text; the generated
  trajectory carries the same untrusted-content warning as the app; `SKILL.md` tells Claude never to
  copy secrets from a recording into a skill and to offer deleting the recording folder afterwards.

## Bugs found by testing, and their fixes

Three real defects only surfaced in a live run with mouse and keyboard capture:

1. **Silent crash on macOS (SIGABRT).** Two `pynput` keyboard listeners were active: the main one
   plus `GlobalHotKeys` for the stop shortcut. The crash report showed
   `HIToolbox: ABORT -> Text Input Sources … called in two threads concurrently`.
   Fix: a single keyboard listener that recognises the stop combination itself.
   **Do not reintroduce `GlobalHotKeys`.**
2. **Stop hotkey never fired.** `Shift` was stripped from the modifier set before the comparison, so
   Ctrl+Shift+Q was recorded as `Ctrl+q` and the recording only ended on its timer.
   Fix: test the stop combination against the full held-modifier set, before any stripping.
3. **Spaces broke typed text** into `typed "hello"` / `pressed Space` / `typed "from"`.
   Fix: map `Space` to a literal space and let it join the typed buffer.

Also handled: PEP 668 blocks `pip install` on Homebrew Python, so `--install-deps` now tries
`--user`, then `--break-system-packages`, before giving up with a copy-pasteable command;
`mss.mss()` is deprecated, so the code prefers `mss.MSS` when present.

## Verification actually performed (macOS 26, Python 3.12)

- Screenshot-only run: readable JPEG, correct `trajectory.md` and `meta.json`.
- Live run driving TextEdit: left and right clicks with coordinates, `typed "space test works"` as
  one batched string, `pressed Enter`, `Cmd+a`, `Esc`, changed-region crops that contained the typed
  text, monitor switch when the cursor moved, and a stop triggered by Ctrl+Shift+Q rather than the
  timer. The crop image was read back to confirm it showed the real text.
- `save_skill.py`: install, duplicate rejection, `--list`, `--where`, invalid-name rejection, and
  cleanup of the throwaway demo skill.
- `install.sh` run from a fresh `git clone` of this repo.

**Not verified: anything on Windows.** See `HANDOFF.md` for the checklist and the specific risks
(DPI scaling between physical and logical coordinates, `py` vs `python`, pip `--user` path, elevated
windows, key-name conventions).

## Repo history

Built at `~/Projects/claude-record-skill` on the Mac, pushed to the private repo
`zvirot1/claude-record-skill`. The installed working copy on the Mac lives at
`~/.claude/skills/record-skill`; `install.sh` / `install.ps1` refresh it from the repo.
