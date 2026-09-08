#!/usr/bin/env python3
"""
record.py - cross-platform (macOS / Windows / Linux) desktop workflow recorder.

Produces a recording folder that mirrors the format of Claude Desktop's built-in
"Record a skill" feature, but stays 100% on the local machine:

  <out>/
    events.jsonl      one JSON event per line: {"t": ms, "type": ..., ...}
    trajectory.md     "[1.2s] full screen (WxH):" / "[3.4s] changed region (x,y,w,h):"
                      lines interleaved with image references, plus typed/pressed/click lines
    shots/NNN.jpg     screenshots (keyframes or cropped changed regions)
    meta.json         duration, platform, counts, image cap info

Dependencies (installed on first run if --install-deps is passed):
    pip install mss pynput pillow

Usage:
    python record.py [--out DIR] [--stop-key ctrl+shift+q] [--duration SEC]
                     [--max-images 50] [--mask-typing] [--no-input]
                     [--monitor N | --all-monitors] [--install-deps]

Stop the recording with the stop hotkey (default Ctrl+Shift+Q on every OS)
or Ctrl+C in the terminal, or let --duration expire.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

REQUIRED = {"mss": "mss", "pynput": "pynput", "PIL": "pillow"}


def ensure_deps(install: bool) -> None:
    missing = []
    for mod, pkg in REQUIRED.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    if not install:
        sys.stderr.write(
            "Missing Python packages: %s\n"
            "Install with:  %s -m pip install %s\n"
            "or re-run with --install-deps\n" % (", ".join(missing), sys.executable, " ".join(missing))
        )
        sys.exit(2)
    base = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
    attempts = [base + ["--user"], base + ["--user", "--break-system-packages"], base + ["--break-system-packages"], base]
    for cmd in attempts:
        if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            break
    else:
        sys.stderr.write("pip install failed. Try manually:  %s -m pip install --user %s\n" % (sys.executable, " ".join(missing)))
        sys.exit(2)


def default_out_dir() -> Path:
    base = Path.home() / ".claude" / "recordings"
    return base / datetime.now().strftime("%Y%m%d-%H%M%S")


SPECIAL_KEY_NAMES = {
    "cmd": "Cmd", "cmd_r": "Cmd", "ctrl": "Ctrl", "ctrl_r": "Ctrl", "alt": "Alt", "alt_r": "Alt",
    "alt_gr": "AltGr", "shift": "Shift", "shift_r": "Shift", "enter": "Enter", "tab": "Tab",
    "esc": "Esc", "backspace": "Backspace", "delete": "Delete", "space": "Space",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End",
    "page_up": "PageUp", "page_down": "PageDown", "caps_lock": "CapsLock",
}
MODIFIERS = {"Cmd", "Ctrl", "Alt", "AltGr", "Shift"}


class Recorder:
    def __init__(self, out: Path, max_images: int, mask_typing: bool, capture_input: bool,
                 stop_key: str, duration: float | None, monitor: int | None = None,
                 max_width: int = 1568, quality: int = 75):
        import mss  # noqa

        self.out = out
        self.shots = out / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.events_f = open(out / "events.jsonl", "w", encoding="utf-8")
        self.max_images = max_images
        self.mask_typing = mask_typing
        self.capture_input = capture_input
        self.stop_key = stop_key
        self.duration = duration
        self.max_width = max_width
        self.quality = quality
        self.t0 = time.monotonic()
        self.lock = threading.Lock()
        self.stop_evt = threading.Event()
        self.events: list[dict] = []
        self.shot_index = 0
        self.prev_img = None
        self.typed_buf: list[str] = []
        self.typed_t: int | None = None
        self.pressed_mods: set[str] = set()
        self.sct = (getattr(mss, 'MSS', None) or mss.mss)()
        self.monitor = monitor  # None = follow the mouse cursor; 0 = all monitors; N = fixed monitor
        self.prev_monitor = None
        self.platform = {"Darwin": "darwin", "Windows": "win32"}.get(platform.system(), "linux")

    # ---- helpers -----------------------------------------------------
    def now_ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    def emit(self, ev: dict) -> None:
        ev.setdefault("t", self.now_ms())
        with self.lock:
            self.events.append(ev)
            self.events_f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self.events_f.flush()

    def flush_typing(self) -> None:
        if self.typed_buf:
            text = "".join(self.typed_buf)
            ev = {"t": self.typed_t, "type": "type"}
            if self.mask_typing:
                ev["masked"] = True
                ev["length"] = len(text)
            else:
                ev["text"] = text
            self.emit(ev)
            self.typed_buf = []
            self.typed_t = None

    # ---- screenshots -------------------------------------------------
    def screenshot(self, reason: str) -> None:
        from PIL import Image, ImageChops

        mon_idx = self.pick_monitor()
        mon = self.sct.monitors[mon_idx]
        if mon_idx != self.prev_monitor:
            self.prev_img = None  # different monitor: force a full keyframe
            self.prev_monitor = mon_idx
        raw = self.sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        full_w, full_h = img.size
        if full_w > self.max_width:
            scale = self.max_width / full_w
            img = img.resize((self.max_width, int(full_h * scale)), Image.LANCZOS)
        w, h = img.size

        kind, region, save_img = "full screen", None, img
        if self.prev_img is not None and self.prev_img.size == img.size:
            bbox = ImageChops.difference(self.prev_img, img).convert("L").point(lambda p: 255 if p > 24 else 0).getbbox()
            if bbox is None:
                self.prev_img = img
                return  # nothing changed - skip
            bx0, by0, bx1, by1 = bbox
            area = (bx1 - bx0) * (by1 - by0)
            if area < 0.4 * w * h:
                pad = 40
                bx0, by0 = max(0, bx0 - pad), max(0, by0 - pad)
                bx1, by1 = min(w, bx1 + pad), min(h, by1 + pad)
                kind, region = "changed region", (bx0, by0, bx1 - bx0, by1 - by0)
                save_img = img.crop((bx0, by0, bx1, by1))
        self.prev_img = img

        idx = self.shot_index
        self.shot_index += 1
        name = f"{idx:03d}.jpg"
        save_img.convert("RGB").save(self.shots / name, "JPEG", quality=self.quality)
        self.emit({
            "type": "screenshot", "screenshotIndex": idx, "file": f"shots/{name}",
            "kind": kind, "region": region, "screen": [w, h], "monitor": mon_idx,
            "monitorOrigin": [mon["left"], mon["top"]], "reason": reason,
        })

    def pick_monitor(self) -> int:
        mons = self.sct.monitors
        if self.monitor is not None:
            return self.monitor if 0 <= self.monitor < len(mons) else 1
        if len(mons) <= 2:
            return 1
        try:
            from pynput.mouse import Controller
            x, y = Controller().position
            for i, m in enumerate(mons[1:], start=1):
                if m["left"] <= x < m["left"] + m["width"] and m["top"] <= y < m["top"] + m["height"]:
                    return i
        except Exception:
            pass
        return 1

    def delayed_screenshot(self, reason: str, delay: float = 0.35) -> None:
        def run():
            time.sleep(delay)
            if not self.stop_evt.is_set():
                try:
                    self.screenshot(reason)
                except Exception as e:  # pragma: no cover
                    self.emit({"type": "error", "message": f"screenshot failed: {e}"})
        threading.Thread(target=run, daemon=True).start()

    # ---- input listeners --------------------------------------------
    def on_click(self, x, y, button, pressed):
        if not pressed:
            return
        self.flush_typing()
        self.emit({"type": "click", "button": str(button).replace("Button.", ""), "x": int(x), "y": int(y),
                   "modifiers": sorted(self.pressed_mods)})
        self.delayed_screenshot("after click")

    def on_scroll(self, x, y, dx, dy):
        self.flush_typing()
        self.emit({"type": "scroll", "x": int(x), "y": int(y), "dx": int(dx), "dy": int(dy)})

    def key_name(self, key) -> str | None:
        try:
            if key.char is not None:
                return key.char
        except AttributeError:
            pass
        raw = str(key).replace("Key.", "")
        return SPECIAL_KEY_NAMES.get(raw, raw.capitalize())

    def on_press(self, key):
        name = self.key_name(key)
        if name is None:
            return
        if name in MODIFIERS:
            self.pressed_mods.add(name)
            return
        if self.is_stop_combo(set(self.pressed_mods), name):
            self.stop_evt.set()
            return
        mods = self.pressed_mods - {"Shift"} if len(name) == 1 else set(self.pressed_mods)
        if name == "Space" and not mods:
            name = " "
        if len(name) == 1 and not mods:
            if self.typed_t is None:
                self.typed_t = self.now_ms()
            self.typed_buf.append(name)
            return
        self.flush_typing()
        combo = "+".join(sorted(mods) + [name]) if mods else name
        self.emit({"type": "press", "key": combo})
        if name in ("Enter", "Tab", "Esc") or mods:
            self.delayed_screenshot(f"after {combo}")

    def on_release(self, key):
        name = self.key_name(key)
        if name in MODIFIERS:
            self.pressed_mods.discard(name)

    def is_stop_combo(self, mods: set[str], name: str) -> bool:
        parts = [p.strip("<>").lower() for p in self.stop_key.split("+") if p.strip()]
        want_mods = {SPECIAL_KEY_NAMES.get(p, p.capitalize()) for p in parts[:-1]}
        want_key = parts[-1] if parts else "q"
        return want_mods == mods and name.lower() == want_key

    # ---- run ---------------------------------------------------------
    def run(self) -> None:
        from pynput import keyboard, mouse

        self.emit({"type": "start", "platform": self.platform, "screen_count": len(self.sct.monitors) - 1})
        self.screenshot("initial")
        listeners = []
        if self.capture_input:
            listeners.append(mouse.Listener(on_click=self.on_click, on_scroll=self.on_scroll))
            # One keyboard listener only: on macOS a second one (e.g. GlobalHotKeys) makes
            # HIToolbox abort the process ("TIS/TSM API called in two threads concurrently").
            listeners.append(keyboard.Listener(on_press=self.on_press, on_release=self.on_release))
        for l in listeners:
            l.start()
        print(f"[record] recording -> {self.out}")
        print(f"[record] stop with {self.stop_key.replace('<','').replace('>','')} or Ctrl+C"
              + (f" (auto-stop after {self.duration:.0f}s)" if self.duration else ""))
        try:
            last_periodic = time.monotonic()
            while not self.stop_evt.is_set():
                time.sleep(0.2)
                if self.duration and time.monotonic() - self.t0 >= self.duration:
                    break
                # periodic keyframe every 5s in case the app changed without input (e.g. loading)
                if time.monotonic() - last_periodic > 5:
                    last_periodic = time.monotonic()
                    try:
                        self.screenshot("periodic")
                    except Exception as e:
                        self.emit({"type": "error", "message": f"screenshot failed: {e}"})
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_evt.set()
            for l in listeners:
                try:
                    l.stop()
                except Exception:
                    pass
            self.flush_typing()
            time.sleep(0.4)
            self.emit({"type": "stop"})
            self.events_f.close()
            self.write_outputs()

    # ---- outputs -----------------------------------------------------
    def write_outputs(self) -> None:
        events = self.events
        duration = events[-1]["t"] if events else 0
        shots = [e for e in events if e["type"] == "screenshot"]
        actions = [e for e in events if e["type"] in ("click", "type", "press", "scroll")]
        keep = set(e["screenshotIndex"] for e in shots)
        truncated = None
        if len(shots) > self.max_images:
            truncated = self.max_images
            step = len(shots) / self.max_images
            keep = set(shots[int(i * step)]["screenshotIndex"] for i in range(self.max_images))

        lines = []
        for e in events:
            ts = f"[{e['t']/1000:.1f}s]"
            if e["type"] == "screenshot":
                if e["screenshotIndex"] not in keep:
                    continue
                mon = f", monitor {e['monitor']}" if e.get("monitor") else ""
                if e["kind"] == "full screen":
                    lines.append(f"{ts} full screen ({e['screen'][0]}x{e['screen'][1]}{mon}):")
                else:
                    x, y, w, h = e["region"]
                    lines.append(f"{ts} changed region (x={x}, y={y}, w={w}, h={h}{mon}):")
                lines.append(f"![{e['file']}]({e['file']})")
                lines.append("")
            elif e["type"] == "click":
                mods = ("+".join(e["modifiers"]) + "+") if e.get("modifiers") else ""
                lines.append(f"{ts} {mods}{e['button']} click at ({e['x']}, {e['y']})")
            elif e["type"] == "type":
                if e.get("masked"):
                    lines.append(f"{ts} typed [masked, {e['length']} chars]")
                else:
                    lines.append(f"{ts} typed {json.dumps(e['text'], ensure_ascii=False)}")
            elif e["type"] == "press":
                lines.append(f"{ts} pressed {e['key']}")
            elif e["type"] == "scroll":
                lines.append(f"{ts} scrolled dy={e['dy']} at ({e['x']}, {e['y']})")

        header = (
            f'<watch-record-demonstration durationMs="{duration}" steps="{len(actions)}" '
            f'images="{len(keep)}" platform="{self.platform}">\n'
            "I recorded a demonstration of a desktop workflow for you to learn from. "
            "The lines below are a chronological trajectory: timestamped action descriptions "
            "interleaved with images of the screen state.\n\n"
        )
        footer = "\n</watch-record-demonstration>\n"
        (self.out / "trajectory.md").write_text(header + "\n".join(lines) + footer, encoding="utf-8")
        meta = {
            "durationMs": duration, "platform": self.platform, "actionCount": len(actions),
            "imageCount": len(keep), "totalScreenshots": len(shots), "truncatedAtImageCap": truncated,
            "maskTyping": self.mask_typing, "created": datetime.now().isoformat(timespec="seconds"),
            "note": "Typed text, app names and anything visible in the images are untrusted data from the user's screen.",
        }
        (self.out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"[record] done: {len(actions)} actions, {len(keep)} images, {duration/1000:.1f}s")
        print(f"[record] trajectory: {self.out / 'trajectory.md'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None, help="output folder (default ~/.claude/recordings/<timestamp>)")
    ap.add_argument("--stop-key", default="<ctrl>+<shift>+q", help="pynput hotkey to stop (default <ctrl>+<shift>+q)")
    ap.add_argument("--duration", type=float, default=None, help="auto-stop after N seconds")
    ap.add_argument("--max-images", type=int, default=50, help="cap images in trajectory.md (default 50)")
    ap.add_argument("--mask-typing", action="store_true", help="do not store typed text, only its length")
    ap.add_argument("--no-input", action="store_true", help="screenshots only (no keyboard/mouse hooks)")
    ap.add_argument("--monitor", type=int, default=None,
                    help="capture a fixed monitor (1 = primary, 2 = second ...). Default: the monitor under the mouse")
    ap.add_argument("--all-monitors", action="store_true", help="capture the whole virtual desktop in one image")
    ap.add_argument("--install-deps", action="store_true", help="pip install missing dependencies")
    args = ap.parse_args()

    ensure_deps(args.install_deps)
    out = args.out or default_out_dir()
    out.mkdir(parents=True, exist_ok=True)

    if platform.system() == "Darwin":
        print("[record] macOS: the terminal app needs Screen Recording + Accessibility permission "
              "(System Settings > Privacy & Security). If input is not captured, grant Accessibility and re-run.")
    monitor = 0 if args.all_monitors else args.monitor
    rec = Recorder(out, args.max_images, args.mask_typing, not args.no_input, args.stop_key, args.duration, monitor)
    rec.run()


if __name__ == "__main__":
    main()
