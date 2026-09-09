#!/usr/bin/env python3
"""
marker_view.py - prepare a marker's screenshot for display inline in the chat.

A marker's image is captured full-frame at the recorder's normal size (1568px wide,
JPEG q75) because that resolution is what makes it readable during analysis. Showing
it in the conversation is a different job: an inline image has to be embedded as a
base64 data URI, which travels through the model's context as text, so it has to be
small. This does that reduction - and only for the images actually being shown.

  python marker_view.py <rec>                      # list the markers and their sizes
  python marker_view.py <rec> --page              # one page with every marked moment
  python marker_view.py <rec> 1 --page            # one page for marker 1 alone
  python marker_view.py <rec> --page --at 11.7    # a moment with no marker, nearest full frame
  python marker_view.py <rec> 1                   # a data URI, for embedding elsewhere

For display, open a --page in the browser pane. Prefer full frames: a marker's image
always is one, but a frame near an unmarked moment is often a region crop, and one in
this project's own recording is 101x94 - stretched to a pane's width it is unreadable.
--at picks the nearest full frame for you, and a too-small shot is flagged.

The page is self-contained (images inlined by this script, never through a response),
carries a CSS size toggle per frame, and ships no JavaScript - the pane renders a local
file as a static snapshot, so scripts do not run and links do not resolve.
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


MIN_USEFUL_WIDTH = 400


def load_shots(rec: Path) -> list:
    out = []
    for line in (rec / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("type") == "screenshot":
            out.append(e)
    return out


def nearest_full(rec: Path, t_ms: int):
    """The full-screen frame closest in time to a moment.

    Region crops are the wrong thing to display: their size is unpredictable - one in
    this project's own recording is 101x94 - and stretching that to a pane's width turns
    it into mush. A marker's own image is always a full frame; a frame merely *near* a
    moment often is not, so pick deliberately rather than by index.
    """
    full = [e for e in load_shots(rec) if e.get("kind") == "full screen"]
    if not full:
        return None
    return min(full, key=lambda e: abs((e.get("t") or 0) - t_ms))


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


PAGE_CSS = """
:root { color-scheme: light dark }
body { margin:0; padding:20px; font:14px/1.6 system-ui,sans-serif;
       background:#faf9f7; color:#1a1a18 }
h1 { font-size:17px; font-weight:500; margin:0 0 4px }
p.sub { margin:0 0 18px; color:#6b6b66 }
section { margin:0 0 30px }
figure { margin:0 }
figcaption { display:block; font-size:13px; color:#6b6b66; margin:0 0 8px }
figcaption b { color:#1a1a18; font-weight:500 }
img { max-width:100%; width:auto; height:auto; display:block;
      border:1px solid #e0ded9; border-radius:8px }
p.hint { margin:0 0 12px; font-size:13px; color:#6b6b66 }
code { font:12px ui-monospace,monospace; color:#4a4a45 }
input.zt { position:absolute; opacity:0; width:0; height:0 }
label.zl { display:inline-block; margin:0 0 12px; padding:5px 12px; font:13px inherit;
           border:1px solid #d4d2cc; border-radius:6px; cursor:pointer; user-select:none }
label.zl:hover { background:#efede8 }
label.zl:after { content:"actual size" }
input.zt:checked ~ label.zl:after { content:"fit to width" }
input.zt:checked ~ figure img { max-width:none }
@media (prefers-color-scheme: dark) {
  body { background:#1a1a18; color:#f0efec }
  p.sub, figcaption { color:#9b9b95 }
  figcaption b { color:#f0efec }
  img { border-color:#3a3a36 }
  code { color:#b5b5ae }
  label.zl { border-color:#4a4a45 }
  label.zl:hover { background:#2a2a27 }
}
"""


def write_one(rec: Path, file: str, label: str, t: str, note: str, name: str) -> Path:
    """One frame per page, so the question being asked has the pane to itself.

    A single image at the pane's full width is far more legible than three stacked.

    No script. The pane renders a local page as a **static snapshot and does not execute
    JavaScript** - established by shipping a page that reported its own state: the hint line
    read "no script is running on this page" and the buttons stayed disabled. So scroll-wheel
    zoom is not available here at all, and the toggle is a CSS checkbox: fit-to-width or the
    native 1568px, with the page scrolling. For free zooming, open the JPEG itself in a tab -
    the browser's image viewer handles it, and navigating a tab there works even though a
    link inside the page does not.

    Do not link the image to the original file. It looks right and fails: the pane renders
    a local page as a static snapshot with no base URL, so a `file:///C:/Users/.../shots/
    009.jpg` href gets resolved against the *project* folder and the click lands on a file
    that is not there. The page prints the real path instead.
    """
    img = rec / file
    if not img.exists():
        raise SystemExit(f"{img} is missing from the recording")
    data = base64.b64encode(img.read_bytes()).decode()
    stamp = f" &middot; {t}" if t else ""
    html = (f"<!doctype html><meta charset=utf-8><title>{label} - {rec.name}</title>"
            f"<style>{PAGE_CSS}</style>"
            f"<h1>{label}</h1><p class=sub>{rec.name}{stamp} &middot; {file} &middot; {note}</p>"
            f'<input type=checkbox class=zt id=z><label class=zl for=z></label>'
            f'<figure><img src="data:image/jpeg;base64,{data}" alt="{label}"></figure>'
            f'<p class=hint>The button switches between fit-to-width and 1568px. For free '
            f'zooming, open the image itself in a tab: <code>{img}</code></p>')
    out = rec / name
    out.write_text(html, encoding="utf-8")
    sys.stderr.write("[marker_view] wrote %s - %d KB, self-contained\n"
                     % (out, out.stat().st_size // 1024))
    return out


def write_page(rec: Path, markers: list, also: list) -> Path:
    """A plain local page of the marked moments, opened in the browser pane.

    The images are inlined as data URIs, written into the file by this script. That is the
    point: base64 was never the problem, transcribing it through a response was. Here the
    bytes go from disk to disk, so nothing can corrupt them, and they stay full resolution.

    Inlining is also what makes the page work at all in the browser pane. A file outside
    the project folder renders there as a static snapshot rather than being served, so a
    relative `src="shots/009.jpg"` does not resolve and every image comes out blank. A
    self-contained page has nothing to resolve.
    """
    items = []
    for m in markers:
        if m.get("file"):
            label = f"marker {m['index']}"
            note = m.get("note") or "not described yet"
            items.append((m["file"], label, f"{m['t'] / 1000:.1f}s", note))
    for spec in also:
        f, _, cap = spec.partition(":")
        items.append((f, cap or f, "", "nearest frame, no marker recorded here"))
    if not items:
        raise SystemExit("nothing to show - no marker had an image, and no --also was given")

    rows = []
    for f, label, t, note in items:
        img = rec / f
        if not img.exists():
            sys.stderr.write("[marker_view] skipping missing %s\n" % f)
            continue
        data = base64.b64encode(img.read_bytes()).decode()
        from PIL import Image
        dims = Image.open(img).size
        stamp = f" &middot; {t}" if t else ""
        n = len(rows) + 1
        native = "" if not dims else f" &middot; {dims[0]}x{dims[1]}"
        rows.append(f'<section><figcaption><b>{label}</b>{stamp} &middot; {f}{native} '
                    f'&middot; {note}</figcaption>'
                    f'<input type=checkbox class=zt id=z{n}><label class=zl for=z{n}></label>'
                    f'<figure><img src="data:image/jpeg;base64,{data}" alt="{label}"></figure>'
                    f'</section>')
    if not rows:
        raise SystemExit("none of the requested frames exist on disk")
    html = (f"<!doctype html><meta charset=utf-8><title>Marked moments - {rec.name}</title>"
            f"<style>{PAGE_CSS}</style>"
            f"<h1>Marked moments</h1><p class=sub>{rec.name} &middot; {len(items)} frame(s)</p>"
            + "".join(rows))
    out = rec / "markers.html"
    out.write_text(html, encoding="utf-8")
    sys.stderr.write("[marker_view] wrote %s - %d frame(s), %d KB, self-contained\n"
                     % (out, len(rows), out.stat().st_size // 1024))
    return out


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
    ap.add_argument("--page", action="store_true",
                    help="write markers.html into the recording and print its file:// URL, for "
                         "opening in the browser pane beside the conversation")
    ap.add_argument("--at", type=float,
                    help="show the full-screen frame nearest this timestamp in seconds - use "
                         "this for a moment with no marker, instead of picking a shot by index")
    ap.add_argument("--label", help="heading for a single-frame page")
    ap.add_argument("--also", action="append", default=[],
                    help="an extra shot to include in --page, as shots/003.jpg[:caption]")
    args = ap.parse_args()

    rec = args.recording.expanduser().resolve()

    if args.at is not None:
        t_ms = int(args.at * 1000)
        e = nearest_full(rec, t_ms)
        if not e:
            raise SystemExit("this recording has no full-screen frame to show")
        off = ((e.get("t") or 0) - t_ms) / 1000
        sys.stderr.write("[marker_view] nearest full frame to %.1fs is %s at %.1fs (%+.1fs)\n"
                         % (args.at, e["file"], (e.get("t") or 0) / 1000, off))
        args.shot = e["file"]
        if not args.label:
            args.label = "%.1fs" % args.at

    if args.shot:
        from PIL import Image
        w = Image.open(rec / args.shot).size[0] if (rec / args.shot).exists() else 0
        if 0 < w < MIN_USEFUL_WIDTH:
            sys.stderr.write("[marker_view] note: %s is only %dpx wide - a region crop. "
                             "For display prefer a full frame, e.g. --at <seconds>.\n"
                             % (args.shot, w))

    if args.page:
        if args.shot:
            print(write_one(rec, args.shot, args.label or args.shot, "",
                            "nearest frame, no marker recorded here",
                            "frame-%s.html" % Path(args.shot).stem).as_uri())
        elif args.index is not None:
            ms = [m for m in load_markers(rec) if m["index"] == args.index]
            if not ms:
                raise SystemExit(f"No marker {args.index}. Run without an index to list them.")
            m = ms[0]
            if not m.get("file"):
                raise SystemExit(f"Marker {args.index} has no image.")
            print(write_one(rec, m["file"], args.label or f"marker {args.index}",
                            f"{m['t'] / 1000:.1f}s", m.get("note") or "not described yet",
                            "marker-%d.html" % args.index).as_uri())
        else:
            print(write_page(rec, load_markers(rec), args.also).as_uri())
        return

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
