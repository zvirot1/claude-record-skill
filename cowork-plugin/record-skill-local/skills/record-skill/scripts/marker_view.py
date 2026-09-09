#!/usr/bin/env python3
"""
marker_view.py - prepare a marker's screenshot for display inline in the chat.

A marker's image is captured full-frame at the recorder's normal size (1568px wide,
JPEG q75) because that resolution is what makes it readable during analysis. Showing
it in the conversation is a different job: an inline image has to be embedded as a
base64 data URI, which travels through the model's context as text, so it has to be
small. This does that reduction - and only for the images actually being shown.

  python marker_view.py <recording-dir>                  # list the markers and sizes
  python marker_view.py <recording-dir> 1                # data URI for marker 1
  python marker_view.py <recording-dir> 1 --crop 785,160,780,485
  python marker_view.py <recording-dir> 1 --width 640 --quality 65
  python marker_view.py <recording-dir> 1 --html         # ready-to-paste widget snippet

Check the size before embedding: --list prints what each marker would cost. Crop to the
region that carries the answer rather than shrinking the whole frame - a dialog cropped
to 560px stays readable where a full frame at 560px does not.
"""
import argparse
import base64
import io
import json
import sys
from pathlib import Path

DEFAULT_WIDTH = 640
DEFAULT_QUALITY = 65


def load_markers(rec: Path) -> list:
    events = rec / "events.jsonl"
    if not events.exists():
        raise SystemExit(f"No events.jsonl in {rec}")
    out = []
    notes = {}
    for line in events.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("type") == "marker":
            out.append(e)
        elif e.get("type") == "note":
            notes[e.get("index")] = e.get("text", "")
    for m in out:
        m["note"] = notes.get(m.get("index"), "")
    return out


def encode(path: Path, crop, width: int, quality: int):
    from PIL import Image

    im = Image.open(path)
    if crop:
        x, y, w, h = crop
        im = im.crop((x, y, x + w, y + h))
    if im.width > width:
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    raw = buf.getvalue()
    return base64.b64encode(raw).decode(), len(raw), im.size


def parse_crop(spec):
    if not spec:
        return None
    try:
        crop = [int(v) for v in spec.split(",")]
    except ValueError:
        raise SystemExit("--crop takes four integers: x,y,w,h")
    if len(crop) != 4:
        raise SystemExit("--crop takes four integers: x,y,w,h")
    return crop


def snippet(b64: str, label: str, t_ms) -> str:
    """One image in a card, ready to paste into the visual widget."""
    caption = label if t_ms is None else f"marker {label} &middot; {t_ms / 1000:.1f}s"
    return ('<div style="padding:1rem 0"><div style="background:var(--surface-1);'
            'border-radius:12px;padding:12px">'
            f'<img src="data:image/jpeg;base64,{b64}" alt="screen at {caption}" '
            'style="width:100%;display:block;border-radius:8px;'
            'border:0.5px solid var(--border)">'
            f'<p style="margin:10px 2px 0;font-size:13px;color:var(--text-secondary)">'
            f'{caption}</p></div></div>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", type=Path, help="a recording folder")
    ap.add_argument("index", nargs="?", type=int, help="marker number (omit to list them)")
    ap.add_argument("--shot", help="show any shot instead of a marker, e.g. shots/003.jpg - use "
                                   "this for a moment the user tried to mark but missed the hotkey")
    ap.add_argument("--crop", help="x,y,w,h in the source image - crop before shrinking")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    ap.add_argument("--html", action="store_true", help="emit a widget snippet, not just the URI")
    args = ap.parse_args()

    rec = args.recording.expanduser().resolve()

    if args.shot:
        img = rec / args.shot
        if not img.exists():
            raise SystemExit(f"{img} is missing from the recording")
        crop = parse_crop(args.crop)
        b64, size, dims = encode(img, crop, args.width, args.quality)
        sys.stderr.write("[marker_view] %s, %dx%d, %d KB -> %d KB base64\n"
                         % (args.shot, dims[0], dims[1], size // 1024, len(b64) // 1024))
        print(snippet(b64, args.shot, None) if args.html else f"data:image/jpeg;base64,{b64}")
        return

    markers = load_markers(rec)
    if not markers:
        raise SystemExit(f"{rec} has no markers - nothing was pressed with the marker hotkey")

    if args.index is None:
        print(f"{len(markers)} marker(s) in {rec.name}:")
        for m in markers:
            f = m.get("file")
            line = f"  marker {m['index']:<3} t={m['t'] / 1000:6.1f}s  {f or '(no image)'}"
            if f and (rec / f).exists():
                _, size, dims = encode(rec / f, None, args.width, args.quality)
                line += (f"  -> {dims[0]}x{dims[1]}, {size // 1024} KB"
                         f" ({int(size * 4 / 3) // 1024} KB as base64)")
            if m["note"]:
                line += f"\n      described as: {m['note']}"
            print(line)
        print("\nCrop to the region that answers the question, then embed only that.")
        return

    match = [m for m in markers if m["index"] == args.index]
    if not match:
        raise SystemExit(f"No marker {args.index}. Run without an index to list them.")
    m = match[0]
    if not m.get("file"):
        raise SystemExit(f"Marker {args.index} has no image. It was recorded before markers "
                         f"captured screenshots, or the grab failed at that moment.")
    img = rec / m["file"]
    if not img.exists():
        raise SystemExit(f"{img} is missing from the recording")

    b64, size, dims = encode(img, parse_crop(args.crop), args.width, args.quality)
    sys.stderr.write(f"[marker_view] marker {args.index} at {m['t'] / 1000:.1f}s, "
                     f"{dims[0]}x{dims[1]}, {size // 1024} KB -> {len(b64) // 1024} KB base64\n")
    print(snippet(b64, str(args.index), m["t"]) if args.html
          else f"data:image/jpeg;base64,{b64}")


if __name__ == "__main__":
    main()
