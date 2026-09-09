# HANDOFF — context for Claude continuing this project on another machine

Read `SESSION-LOG.md` alongside this file: it explains how the built-in feature works internally,
why the design is what it is, and which bugs were already found and fixed (do not reintroduce them).

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

## Verified on Windows (2026-09-08, Windows Server 2022, Python 3.13.2)
`install.ps1`, `--where`, `--no-input` capture (readable JPEG), live capture of clicks with
coordinates, `pressed Ctrl+a`, `typed "space test works"` (spaces batched), `pressed Enter`,
changed-region crops containing the typed text, stop via Ctrl+Shift+Q (18s of a 40s budget),
`save_skill.py` install / duplicate rejection / `--force` / invalid name / `--list` / `--open`
(opens Explorer). Live human run also confirmed `pressed Win+r` (the crop shows the Run dialog it
opened), scroll capture, and Hebrew typed text surviving as UTF-8.

### Windows bugs found and fixed
1. **Keyboard capture was completely dead.** On Windows pynput calls
   `on_press(key, injected)` / `on_release(key, injected)`; macOS passes only `key`. The extra
   argument raised `TypeError`, pynput killed the listener thread, and because nobody joins it the
   failure was silent - mouse events kept coming, no keys ever appeared. All listener callbacks now
   take `*_`, and every callback is wrapped in `Recorder.guard()` which records an `error` event
   with a traceback instead of dying quietly.
2. **Modifiers were never tracked.** pynput reports `Key.ctrl_l` / `shift_l` / `alt_l` on Windows;
   only the unsuffixed macOS spellings were in `SPECIAL_KEY_NAMES`, so `Ctrl` was logged as the
   bogus key `Ctrl_l` and never entered `pressed_mods` - which also meant the stop hotkey could
   never match. The `_l` variants (plus `super*`, `insert`, `num_lock`, ... ) are mapped now.
3. **Ctrl+letter recorded control codes.** With Ctrl held, Windows translates the letter to its
   control character, so Ctrl+Q arrived as `''`. `key_name()` recovers the letter from
   `key.vk` (falling back to `ord+96`), so shortcuts read `Ctrl+a` and the stop combo matches.
4. `cmd` now maps to **Win** on Windows.
5. `enable_dpi_awareness()` marks the process per-monitor-DPI-aware at startup so mss pixels and
   pynput mouse coordinates share one coordinate space on scaled displays (this box runs at 100%,
   where coordinates already matched exactly: a click at (1300,400) logged as (1300,400)).
6. `save_skill.py --open <missing>` printed a WinError and exited 0; it now exits non-zero with
   `No such skill: <path>`.

### Found in the live human run (and fixed)
7. **Typed lines rendered out of order.** A typed batch is emitted when the batch ends but
   timestamped when it started, so `typed "..."` appeared *after* the Enter that terminated it.
   `write_outputs()` now sorts events by `t`.
8. **Key auto-repeat was recorded as real actions.** Holding Enter produced five
   `pressed Enter` lines, each queueing its own screenshot (13 images in 15 s, all near-identical).
   `self.held` drops repeat presses until the key is released; a genuine second press still counts.
9. **Screenshot bursts.** `delayed_screenshot()` coalesces - one pending shot captures the
   settled state instead of one image per action in a burst. The same live workflow now yields
   4 images instead of 13.

Not retested on macOS after these changes - they are additive (extra key mappings, `*_` on
callbacks, a Windows-only DPI call), but re-run the macOS live test when you pull.

Fix issues directly in `skills/record-skill/`, re-run `install.ps1`, commit and push. Then on the Mac:
`git pull && ./install.sh`.

## Cowork packaging (2026-09-08)
`cowork-plugin/record-skill-local/` wraps the skill as a Cowork plugin; the installable file is
`cowork-plugin/dist/record-skill-local.plugin` (a zip with the manifest at the root). Cowork's
plugin preview parsed it correctly on the first try - it listed every bundled file.

**Cowork's skill validator is stricter than Claude Code's**: it rejects a `description`
containing XML tags. `<watch-record-demonstration>` in the description failed with
"SKILL.md description cannot contain XML tags"; it is now written without angle brackets in
both copies of the skill. Claude Code loads either form, so this only shows up when packaging.

Cowork loads skills from plugins, never from `~/.claude/skills` - its own skills come from an
account-synced plugin under `AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\`
with a `manifest.json` of skillId/creatorType/enabled. Cowork also runs its tools in a Linux
microVM (`rootfs.vhdx` + `vmlinuz`, see `logs/cowork_vm_node.log`), so `record.py` cannot capture
the host screen from there - the recorder always runs on the host.

Rebuild after editing the skill:
```bash
cp skills/record-skill/scripts/*.py cowork-plugin/record-skill-local/skills/record-skill/scripts/
cd cowork-plugin/record-skill-local && zip -r ../dist/record-skill-local.plugin . -x "*.DS_Store"
```

### Cowork verification (2026-09-08) - what actually works
The plugin installs correctly: it appears in
`local-agent-mode-sessions/<account>/<session>/rpm/manifest.json` as `record-skill-local`
(marketplace "My Uploads", `updatedAtVerified: true`) and materialises under `rpm/plugin_<id>/`.

**Skills in `skills/` are NOT exposed as slash commands in Cowork.** Both `/record-skill` and
`/record-skill-local:record-skill` returned "Unknown skill" with the plugin fully installed - the
`<plugin>:<skill>` form is Claude Code's convention, not Cowork's. Slash commands come only from
`commands/*.md` (the "legacy" format), so v0.2.0 adds `commands/record-skill.md`, a thin wrapper
that reads `${CLAUDE_PLUGIN_ROOT}/skills/record-skill/SKILL.md` and follows it.

**Description-based triggering works, and works well.** Asked in plain Hebrew to turn a recording
folder into a local skill, Cowork loaded the skill, read both recordings from the host (via its
Windows-MCP integration - so the host filesystem IS reachable from Cowork), and correctly refused
to invent a workflow: it reported 14.8s, 1 click, 11 keystrokes, "meaningless letter sequences",
no files opened or saved, and asked for a real recording instead. That is exactly the behaviour
step 2 of the skill prescribes.

## Windows status after merging the Mac commits (2026-09-08, re-verified)

| Check | Status |
|---|---|
| 1. `install.ps1` + `save_skill.py --where` | PASS - installs to `C:\Users\<me>\.claude\skills`, finds `py -3` (3.13.2) |
| 2. `--no-input --duration 5` | PASS - `trajectory.md` + a readable full-screen JPEG, read back and confirmed |
| 3. Live recording | PASS - see below |
| 4. `save_skill.py` matrix | PASS - install, duplicate rejection (exit 1), `--force`, invalid name (exit 1), `--list`, `--open` (Explorer), `--open <missing>` (exit 1) |

Check 3 in detail. One clean run on the merged tree (2026-09-09, after the desktop session came
back at 1920x1080), all four points in a single recording:
- **Clicks with correct coordinates**: a click at (1372, 521) was recorded as exactly `(1372, 521)`.
- **Batched typed text including spaces**: `typed "space test works"` as one string.
- **`pressed Enter`** and **`pressed Ctrl+a`** (the Windows control-code path).
- **Hotkey stop**: stopped at 21.1s of a 60s budget - Ctrl+Shift+Q, not the timer.
- 7 images, 0 error events, `screenCaptureFailing: false`, and the crop after Enter was read back
  and shows the typed text in Notepad with `Ln 2, Col 1`.

Also confirmed by the user's own live human run (`20260908-103741`): stopped at 14.8s of a 30s
budget, produced `pressed Win+r` with a crop showing the Run dialog it opened, scroll capture, and
Hebrew typed text intact as UTF-8.

**DPI scaling is still unverified.** This machine reports `GetScaleFactorForDevice(0) == 100`, so
coordinates match trivially and `enable_dpi_awareness()` never has to do any work. Exercising it
needs a HiDPI display (a scaled laptop panel).

### Bug found during this re-verification (fixed)
10. **An unguarded first screenshot killed the whole recording.** `run()` called
    `self.screenshot("initial")` outside any try/except, so when the grab failed the process died
    with a traceback *before any listener started and before any output was written* - the folder
    was left with a lone `start` line, no `trajectory.md`, no `meta.json`. It surfaced when this
    machine's desktop session became uncapturable mid-test (mss raises
    `Windows graphics function failed: BitBlt` for a locked session or a disconnected RDP session;
    on macOS a missing Screen Recording permission does the same).
    Fix: `try_screenshot()` reports instead of raising, prints a warning naming the likely cause,
    and the recording continues and always writes its outputs. Repeated failures no longer emit an
    error event every 5 s - only the first failure and any recovery - and `meta.json` now carries
    `screenCaptureFailing`. Both copies of SKILL.md tell Claude to check that flag and offer to
    re-record instead of guessing at a workflow it has no images for.

### .gitignore
`*.log` did not cover rotated logs, so a `jdbc-server.log.1` appeared untracked but unignored -
the same way the original `jdbc-server.log` got committed by accident. `*.log.*` is now ignored
too. Rotated logs stay on disk; they are not this project's files.

## Audio / narration: not implemented, and probably not worth implementing as speech

`record.py` captures **no audio at all** - the dependencies are `mss`, `pynput`, `Pillow` and
there is no audio code path. Both copies of SKILL.md now say so outright and tell Claude to ask
the user for the intent in chat, because the trajectory shows *what* happened and never *why*.

### What was actually verified about the built-in feature
Scanned the installed Windows package
(`C:\Program Files\WindowsApps\Claude_1.10628.0.0_x64__pzs8sxrjxfjjc\app\resources\app.asar`):

- The app **does** carry mic plumbing, but it belongs to Quick Entry **dictation**, not to the
  recorder: `quickEntryDictationShortcut` (`capslock` / `double-tap-capslock` / `off`),
  `quickAccess.dictation.show/stop/toggle`, `dictation.setLanguage(...)`, a microphone-permission
  modal, and "Voice mode settings (hold-to-talk / tap-to-toggle dictation)". `setLanguage`
  alongside `api.setCredentials` says transcription happens **service-side**; there is no local
  ASR model in the bundle.
- `getUserMedia` and `MediaRecorder`: **zero** hits. The `audio/webm` hits are just mime-db
  tables, not capture code.
- The watch-record feature is **not in this bundle at all**: `watch-record-demonstration`,
  `cowork_watch_record`, `Record a skill` and `changed region` all return 0 hits. Consistent with
  the Mac finding that its renderer lives in a served `ion-dist/assets/v1/shared-10-*.js`, so the
  Windows package cannot be used to settle what the recorder captures.

### Correction to an earlier claim in this file's history
It was asserted in conversation that the built-in recorder captures mic narration. That is **not
established**. The only evidence is SESSION-LOG.md line 40, which paraphrases the app's
system-reminder marking narration as *untrusted data if present* - that is an instruction about
how to treat narration, not proof that audio is recorded. It may simply cover a mic that is open
for another reason. Treat the question as open.

### Why this shapes the roadmap
Recording audio is cheap on any platform. **Transcribing it locally is the expensive part**, and
only the local-only constraint - the whole point of this project - forces that. The built-in flow
pays no such cost: it is a cloud client whose model is server-side anyway.

So speech was not reached for first. The cheap options are **implemented** as of this commit:
1. `--note "..."` stores one sentence of intent with the recording (header + `meta.json.intent`).
2. **Ctrl+Shift+M** stamps a marker mid-recording; the descriptions are collected after the
   listeners are down, and each is filed at the marker's timestamp.
3. Describing the intent in chat still works and SKILL.md still asks for it - a typed answer is
   more precise than a transcript.

The synchronisation problem and how it is solved: a note is always written *after* the moment it
describes, so the keypress carries the timestamp and the words arrive later. That is the same
split the typed-text batching already used (stamped at the first character, emitted when the batch
ends), and it is why `write_outputs()` sorts by `t` - a late event with an early timestamp lands
back in the right place. Collecting the text only after the recording stops is not just
convenient: the keyboard hook is global, so anything typed while it is live would be recorded as
typed text and pollute the trajectory. Verified: the Ctrl+Shift+M presses do not appear in the
trajectory at all, and the typed strings around them stay clean.

Residual imprecision, by design: human reaction lag means a marker lands ~1s after what it
describes, and `delayed_screenshot` takes the image 0.35s after an action, so the nearest image to
a marker may be the following one. Markers are for coarse annotation, not for pinpointing a
200ms flash.

`--no-prompt` exists because a scripted run with a console attached would otherwise block forever
on the marker questions.

Local speech-to-text (a Whisper-class model, hundreds of MB, CPU-bound, with real quality risk for
Hebrew) is only worth it if narrating hands-free during the workflow turns out to matter more than
answering one question afterwards.

## Hebrew keyboard and the numeric keypad (2026-09-09)

Found by recording something deliberately trivial - 9 * 18 in the Windows calculator. Three real
defects, all invisible on a US layout:

11. **The numeric keypad produced no usable input.** Keypad keys report a virtual key code and no
    character, so pynput renders them as `<105>` and the trajectory read
    `pressed <105>` / `typed "*"` / `pressed <97>` / `pressed <104>` - the exercise 9*18 was
    unrecoverable. `WIN_NUMPAD_VK` now maps vk 96-111 to their characters and they join the typed
    buffer, giving `typed "9*18"`. The codes are Windows-specific (macOS and X11 number keys
    differently), so the lookup is guarded by `IS_WINDOWS`.

12. **Shortcuts were logged in the layout's alphabet.** With a Hebrew layout active, Win+R came out
    as `pressed Win+<resh>`. A shortcut names a *physical* key, so `physical_key()` maps the scan
    code back through `MapVirtualKey(scan, MAPVK_VSC_TO_VK)` - layout-independent - and it is
    applied when a non-Shift modifier is held. Ctrl-based hotkeys were already safe by accident:
    Ctrl turns a letter into a control code, and the existing vk recovery caught that, which is
    why Ctrl+Shift+Q kept working on a Hebrew keyboard while Win+R did not.

13. **Typed text was recorded in the wrong alphabet.** "calc" typed into the Run box came out as
    `typed "\u05d1\u05e9\u05da\u05d1"` - the Hebrew letters on those keys - even though the box
    clearly received `calc`, since the calculator opened. pynput caches the keyboard layout and
    updates it on `WM_INPUTLANGCHANGE`, which its listener thread can miss, so after a layout
    switch it keeps translating with the old one. Rather than guess which is right, a type event
    now carries both: `text` as the layout produced it and `keys` as the physical keys, rendered as
    `typed "\u05d1\u05e9\u05da\u05d1"  (physical keys: "calc")`. Latin typing gets no `keys` field.
    Both copies of SKILL.md tell Claude to prefer the physical reading when they disagree and to
    say which it used.

Verified by faking the key events (a `KeyCode` stand-in with `char`, `vk` and `_scan`): keypad
digits become typed text, no `<105>` press events survive, a scan code recovers the Latin letter,
Win+resh logs as `Win+r`, Hebrew typing keeps both readings, Latin typing carries no second one,
and the trajectory renders both. A live run then confirmed no regression: exact click coordinates,
`typed "9*18"` batched, `pressed Enter`, and a hotkey stop at 29.3s of a 45s budget. The true
keypad scan codes could not be sent through the automation tool, so that path rests on the faked
events plus the original recording that exposed it.

### A note on what recordings leave on disk
The two Gmail recordings from this session contain a client's name, national ID number and
financial details in the screenshots. `~/.claude/recordings/` is a plain folder with no expiry -
it is worth deleting a recording once the skill is drafted, and worth preferring subjects with no
sensitive data (a calculator, a scratch file) when the goal is only to exercise the pipeline.
