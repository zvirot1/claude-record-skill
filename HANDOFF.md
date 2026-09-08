# HANDOFF — context for Claude continuing this project on another machine

## What exists
- `skills/record-skill/scripts/record.py`: recorder built on `mss` + `pynput` + `Pillow`.
  Screenshot after every click, Enter/Tab/Esc and modifier shortcut, plus a keyframe every 5 s when
  something changed; crops to the changed region when < 40 % of the screen changed; batches typed
  characters (including spaces) into `typed "..."`; caps images at 50 (evenly sampled); captures the
  monitor under the mouse (`--monitor N`, `--all-monitors`). Stop hotkey Ctrl+Shift+Q, detected inside the
  single keyboard listener. **Do not add a second pynput keyboard listener / GlobalHotKeys** — on macOS
  HIToolbox aborts the process ("TIS/TSM API called in two threads concurrently").
  Output: `~/.claude/recordings/<ts>/{trajectory.md,events.jsonl,shots/*.jpg,meta.json}`.
- `skills/record-skill/scripts/save_skill.py`: local installer/validator for drafted skills
  (`--scope user|project`, `--list`, `--where`, `--force`, `--open`). Never the cloud tools.
- `skills/record-skill/SKILL.md`: the skill Claude follows. OS-specific path/command table inside.
- `install.sh` / `install.ps1`: copy `skills/*` into `~/.claude/skills` and install deps.

## Verified on macOS (2026-09-08)
Live recording: left/right clicks with coordinates, `typed "space test works"`, `pressed Enter`, `Cmd+a`,
`Esc`, changed-region crops, monitor switch when the mouse moved, hotkey stop. `save_skill.py` install,
duplicate rejection, `--list`, invalid-name rejection.

## To verify on Windows
1. `.\install.ps1` completes and `save_skill.py --list` prints `C:\Users\<me>\.claude\skills`.
2. `py -3 ...\record.py --no-input --duration 5` → `trajectory.md` and one readable JPEG.
3. `py -3 ...\record.py --duration 30` while clicking and typing in Notepad, stop with Ctrl+Shift+Q →
   clicks, `typed "..."`, `pressed Enter`, crops, stopped by the hotkey (not by the timer).
4. Key names use Windows conventions (Ctrl, Alt, Win). If `cmd` shows up, map it to "Win" on win32 in
   `SPECIAL_KEY_NAMES`.
5. `save_skill.py --open record-skill` opens Explorer (`os.startfile`).

Known risks: DPI scaling (mss returns physical pixels; click coordinates from pynput are logical on
some setups — if crops look offset, scale click coords by `ctypes.windll.shcore.GetScaleFactorForDevice(0)/100`);
pynput does not see input in elevated windows; `py` launcher vs `python`; pip `--user` scripts path;
Ctrl+Shift+Q collisions (add `--stop-key "<ctrl>+<alt>+q"` if needed).

Fix issues directly in `skills/record-skill/`, re-run `install.ps1`, commit and push. Then on the Mac:
`git pull && ./install.sh`.
