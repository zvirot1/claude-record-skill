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

## Building a skill that runs in both Code and Cowork (2026-09-09)

`skills/record-skill/scripts/package_plugin.py` wraps any skill folder as a `.plugin`. It exists
because the two environments load skills from different places, and hand-wrapping repeats every
constraint we had to discover:

- Cowork's validator rejects **XML tags** in a skill description.
- A `skills/` folder alone gets **no slash command** in Cowork; only `commands/*.md` does, so the
  script generates a thin wrapper that reads `${CLAUDE_PLUGIN_ROOT}/skills/<name>/SKILL.md`.
- The manifest blurb is cut on a sentence or word boundary, never mid-token.

Usage, and the two-destination pattern:

```bash
save_skill.py <draft> --scope user          # Claude Code reads ~/.claude/skills
package_plugin.py <skill-folder> --out dist # Cowork reads plugins
```

### The YAML trap, found by running the official validator on generated output
`claude plugin validate` rejected the first `calc-exercise` package:

    frontmatter: YAML frontmatter failed to parse: Nested mappings are not allowed in compact
    mappings ... At runtime this skill loads with empty metadata (all frontmatter fields silently
    dropped).

The cause was a colon followed by a space inside an unquoted description
(`gives the numbers: "..."`), which YAML reads as a nested mapping. This matters far beyond
packaging: such a skill **installs cleanly and then never triggers**, because every frontmatter
field is dropped at load time. Both `save_skill.py` and `package_plugin.py` now run
`lint_frontmatter()` and refuse it, naming the fix (use a dash, or quote the value). Checked the
repo's own skills - `record-skill` is clean; only the freshly written one was affected.

Worth keeping in mind: the regex frontmatter parsers here are lenient, and a session listed the
broken skill with its full description as if nothing were wrong. So a skill can look installed and
working while its metadata is gone at load time. Validate the packaged output, not just the
manifest.

### What is host-only
Cowork's default shell runs in a cloud container (see the correction below). A skill step that
needs the user's own desktop cannot run
there; file, shell and API steps run anywhere. The generated plugin README says so, and
`calc-exercise` marks its Windows-calculator section host-only while computing with `python3` or
`py -3` depending on the environment.

## Cowork verification: both plugins run there (2026-09-09)

Confirmed in a Cowork session by the user, after Save plugin and a new session.

**`/calc-exercise 127*43`** -> `127 * 43 = 5461`, with the activity line reading
"Read a file, ran a command". Both halves matter: "read a file" is the generated
`commands/calc-exercise.md` wrapper pulling in
`${CLAUDE_PLUGIN_ROOT}/skills/calc-exercise/SKILL.md`, and "ran a command" means it
computed the answer instead of doing mental math, which is the skill's central rule.

**`/latest-email`** -> "Loaded tools, used Gmail integration, read a file", then the newest
inbox message summarised, with the conclusion that it was marketing with nothing actionable.
No browser, no clicks.

Two things this settles:

1. **The `commands/*.md` wrapper is what makes a slash command work in Cowork.** Before it,
   `/record-skill` and `/record-skill-local:record-skill` both returned "Unknown skill" with the
   plugin correctly installed. `package_plugin.py` generates the wrapper, and the slash command
   resolved on the first try for both skills.
2. **The Gmail connector is available inside Cowork.** `latest-email` reached it from there, so a
   connector-based skill built on the host runs unchanged in Cowork. That was an open question.

Still untested, and cheap to check when convenient: the description-trigger route in Cowork (only
the slash commands were exercised), the operator-precedence case (`2+3*4` must be 14, not 20), the
host-only branch (asking for the Windows calculator from Cowork should decline and give the number),
and which Python actually ran - `python3` inside the VM or `py -3` on the host through Windows-MCP.

### The pipeline, end to end
A workflow recorded on the host with `record.py`, analysed for its outcome rather than its
gestures, drafted as a SKILL.md, installed with `save_skill.py` for Claude Code and packaged with
`package_plugin.py` for Cowork - two skills through it now, and nothing stored in a cloud account
at any step.

## Correction: where Cowork actually runs a command (2026-09-09)

Earlier notes in this file said Cowork "runs its tools in a Linux VM", inferred from
`logs/cowork_vm_node.log` downloading `rootfs.vhdx` and `vmlinuz`. Asked directly how it had
computed `127*43`, the Cowork session answered:

    command: python3 -c "print(127*43)"
    where:   the session's cloud container (the Bash tool) - not on your computer. I did not touch
             the host, the local VM (device_bash), or the Windows calculator.
    output:  5461

So there are **three** execution surfaces, not one:

| Surface | Reaches |
|---|---|
| `Bash` (default) | a cloud container - nothing local |
| `device_bash` | the local machine / VM |
| Windows-MCP | the host desktop, PowerShell, host files |

The local VM bundle is real - the log proves it downloads - but the default shell is remote. This
also explains how the Cowork session read `C:\Users\...\recordings` earlier: through Windows-MCP,
which it named at the time, not through Bash.

**Why this matters beyond accuracy.** Anything a skill pipes through the default shell leaves the
machine. For `9*18` that is nothing; for a skill that touches client email, ID numbers or financial
figures it is a disclosure path, on a bank-issued machine. Both copies of SKILL.md now tell Claude
to name the surface it used and to prefer the host surface for private data, rather than assuming
"a local VM" as the docs previously implied.

## Second correction: Cowork can reach the desktop after all (2026-09-09)

Test 3 of the Cowork checklist was meant to confirm that asking for the Windows calculator from
Cowork would be declined. It was not. The session used Windows-MCP, and reported:

    Used Windows-MCP integration
    9 * 18 = 162
    I minimised Claude, brought calc.exe to focus, typed 9*18 and Enter (without clicking
    buttons), closed the two extra calculator windows and restored Claude. Same number python
    gave - this route is slower and exists only for the demonstration.

Three things follow:

1. **My prediction was wrong, and so was the instruction I had written into `calc-exercise`.** It
   said the calculator route "does not work from a session whose tools run in a container or VM (a
   Cowork session): there is no Windows desktop to open." Cowork had a host surface and correctly
   ignored that. An instruction that forbids something the agent can actually do is worse than no
   instruction.
2. **The rule must be a check, not an architecture claim.** What a Cowork session can reach depends
   on which surfaces are attached (cloud `Bash`, a device shell, Windows-MCP), not on a fixed
   design. `calc-exercise` now says to look for a host surface and proceed if one exists, and both
   copies of `record-skill`'s SKILL.md tell Claude to test rather than declare impossibility -
   citing this exact incident.
3. **The skill's own instructions did hold where they mattered**: it typed the expression instead
   of clicking buttons, and it tidied the desktop afterwards. Tidying was not in the skill; it is
   now.

This is the third correction in a row about execution surfaces (local VM -> cloud container ->
host reachable via MCP). The lesson worth carrying: infer capability from what the session reports
doing, not from artefacts on disk, and write skills that probe rather than assume.

## latest-email returned the wrong email, and why (2026-09-09)

Test 1 of the checklist passed - both skills triggered from their descriptions with no slash
command, and `calc-exercise` answered 5,461 saying "computed in Python, not in my head". But the
user spotted that `latest-email` had not returned the newest email. It had not. The skill's core
instruction was unsound, and measuring the mailbox showed two independent reasons.

**1. A thread is not a message.** `search_threads` returns threads, each with a `messages` array,
and the newest message can be the second one inside a lower-ranked thread. In one 25-thread sweep
the thread at position 3 held a message 13 minutes newer than the thread at position 2, and the
thread at position 8 held one newer than positions 4 through 7. Taking "first thread, first
message" skips all of those.

**2. The returned order is not by date.** Of those 25 threads, **6 pairs** came back with an older
thread ranked above a newer one - including two single-message threads 164 minutes apart
(`maxfinance` at position 24, `samsung` at 25). So "results come back newest first", which the
skill asserted, is simply false. Whatever the ordering key is, it is not the message date.

The fix: sweep `pageSize: 25` with `THREAD_VIEW_METADATA_ONLY` (cheap, no bodies), flatten every
message of every thread, and take the largest `internalDate` - epoch milliseconds, not the
formatted `date` string. Verified against the live mailbox: the flatten-and-max method picks the
message that is genuinely newest, where the old method's answer was the third newest at the time.

Two smaller things the same investigation surfaced, both now in the skill: pass the *message* id to
`get_message` (for a multi-message thread it differs from the thread id), and state the winner's
timestamp when it is only minutes old, since mail arrives between the sweep and the answer.

### The pattern across these bugs
Every failure in this session came from an assumption stated as fact - pynput's callback signature,
the keyboard layout, "Cowork runs in a local VM", "the calculator is unreachable from Cowork", and
now "search_threads returns newest first". The ones that survived testing were the instructions
written as a check rather than a claim. Worth carrying into any skill drafted from a recording: if
the skill asserts an ordering, a location or a capability, verify it against the real system once,
and write the verification into the skill rather than the conclusion.

## Test 4 passed, and taught the skill something (2026-09-09)

Asked to save the newest email to a file, the Cowork session **stopped before writing** and offered
three destinations:

1. the machine itself (`Desktop`), written through Windows-MCP - "the content does not pass through
   the cloud";
2. a file to download from the chat, built in the cloud environment - adding that *this particular*
   email is a public Seeking Alpha newsletter with no personal data, so that path would not expose
   client information;
3. another path, on request.

That is the behaviour the skill asked for, plus a judgement it did not: it assessed the sensitivity
of **this** email rather than applying a blanket rule. The skill said "for this content use the host
surface, or do not write it at all", which is too absolute - a public newsletter through the cloud
path costs nothing. It now says to match the surface to what the email actually contains, with the
two cases spelled out, and to name the destination before writing rather than after.

Second time a Cowork run has improved the skill by doing something better than instructed (the
first was tidying the desktop after using the calculator). Worth noting as a pattern: watch what a
good run does beyond the instructions, and fold it back in.

### The ordering fix verified live
The same test also confirmed the `latest-email` fix, on a query where the old method would have
failed. `search_threads` returned:

    position 1: htzone        10:01:16
    position 2: seekingalpha  10:05:32   <- actually the newest
    position 3: payngo        10:01:39

The old "first thread" method would have answered htzone, 4 minutes stale. Cowork answered Seeking
Alpha - the flatten-and-take-max-internalDate method picking correctly out of order.

## Cowork checklist complete: 4 of 4 (2026-09-09)

| Test | Result |
|---|---|
| 1. Description trigger, no slash command | PASS - both skills triggered from their descriptions; `calc-exercise` answered 5,461 saying it computed in Python, not in its head |
| 2. Operator precedence | PASS - `2+3*4` returned **14**, with the steps shown and "multiplication before addition, so 14 and not 20" stated explicitly |
| 3. Host-only branch | PASS, and refuted the instruction - Cowork drove the Windows calculator through Windows-MCP, typed rather than clicked, and tidied up afterwards |
| 4. Writing email content to a file | PASS - stopped before writing, offered host vs cloud with the trade-off, and judged that this particular email was a public newsletter |

Two of the four improved the skills rather than merely passing them: test 3 removed an instruction
that forbade something the agent could do, and test 4 replaced a blanket privacy rule with one that
matches the surface to the content. Test 2 is the only one that passed exactly as written - and the
precedence clause it produced ("14 and not 20") is what the skill asks for verbatim.

### Where the project stands
The whole pipeline is exercised end to end on Windows: record on the host, analyse for the outcome
rather than the gestures, draft a SKILL.md, install with `save_skill.py` for Claude Code, package
with `package_plugin.py` for Cowork, and run it in both. Two skills through it (`calc-exercise`,
`latest-email`), nothing stored in a cloud account at any step.

Still unverified anywhere: **DPI scaling** (this machine reports 100%, so `enable_dpi_awareness()`
never has to do any work) and the **numeric keypad on real hardware** (its scan codes could not be
injected through the automation tool, so that path rests on faked key events plus the one recording
that exposed the bug). Also untested: macOS after all the Windows fixes - they are additive, but a
single live run there would close it.

## Two process fixes: ask for outcomes, verify outcomes (2026-09-09)

Both came out of reviewing the workflow rather than from a bug report, and they are the same fix at
the two ends of the pipeline: mechanics were being collected on the way in and assumed on the way
out.

### The input end: the marker prompt asked the wrong question
It used to print `Say what each one was (Enter to skip)`, and the answers it got back were
"opened Chrome", "clicked the email", "copied the content" - all mechanics the trajectory had
already recorded. The one thing a recording can never show, why, was never asked for.

Now it asks `what did this accomplish? (not what you clicked - that is already recorded)`, and
shows the action immediately before each marker so the moment is recognisable:

    marker 1 at 4.0s   [just before: left click at (512, 1052)]
      what did this accomplish?

And when `--note` was omitted it asks for the workflow's purpose at the end, where the user
actually knows it: `what did this workflow accomplish overall?`. `--no-prompt` still silences
everything, and a non-interactive run still says so instead of blocking.

### The output end: a test stage that checks the answer, not the plumbing
Every skill that shipped broken from this workflow shipped with an unverified factual claim inside
it. Step 3b now requires two things before saving:

1. **An assertion audit** - list every claim the draft makes about how a system behaves, and either
   verify it with one cheap call or rewrite it as a runtime check. The four kinds, each with a real
   failure from this session: ordering ("newest first" - 6 of 25 rows out of order), capability
   ("cannot reach the calculator from Cowork" - it did), location ("~/.claude/skills" - not in
   Cowork), field name (`date` string vs `internalDate`).
2. **A correctness smoke test** - and the distinction that matters: calling a tool and watching it
   respond proves it is *reachable*; running what the skill instructs, computing the answer a
   second independent way, and comparing proves it is *correct*. Only the second catches a wrong
   method. `latest-email` was saved after the first kind of check and returned the third-newest
   email until the user noticed.

Plus: run the real validator on the real artifact where one exists, and draft **outside** the
recording folder - the privacy advice is to delete the recording, which used to take the draft
with it.
