#!/usr/bin/env python3
"""
save_skill.py - install a drafted skill LOCALLY (never to the cloud account).

Works on macOS, Windows and Linux. Skills are plain folders with a SKILL.md:

  user scope    ->  ~/.claude/skills/<name>/SKILL.md
                    (Windows: %USERPROFILE%\\.claude\\skills\\<name>\\SKILL.md)
  project scope ->  <cwd>/.claude/skills/<name>/SKILL.md

Usage:
  python save_skill.py <path-to-skill-dir-or-SKILL.md> [--scope user|project] [--name NAME] [--force]
  python save_skill.py --list [--scope user|project|all]
  python save_skill.py --where [--scope user|project]
  python save_skill.py --open <name>          # reveal the skill folder in Finder / Explorer
"""
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def skills_root(scope: str) -> Path:
    if scope == "project":
        return Path.cwd() / ".claude" / "skills"
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
    return home / "skills"


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^\ufeff?---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        raise SystemExit("SKILL.md must start with a YAML frontmatter block (--- name/description ---)")
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def validate(skill_dir: Path, name_override: str | None) -> str:
    md = skill_dir / "SKILL.md"
    if not md.exists():
        raise SystemExit(f"No SKILL.md in {skill_dir}")
    fm = parse_frontmatter(md.read_text(encoding="utf-8"))
    name = name_override or fm.get("name") or skill_dir.name
    if not NAME_RE.match(name):
        raise SystemExit(f"Invalid skill name {name!r}: use lowercase letters, digits and dashes only")
    if not fm.get("description"):
        raise SystemExit("frontmatter is missing 'description' (this is what triggers the skill)")
    if len(fm["description"]) > 1024:
        raise SystemExit("description is longer than 1024 chars; shorten it")
    if fm.get("name") and fm["name"] != name:
        print(f"[save] note: frontmatter name {fm['name']!r} != folder name {name!r}; folder name wins")
    return name


def reveal(path: Path) -> None:
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sysname == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        print(f"[save] could not open folder: {e}")


def list_skills(scope: str) -> None:
    scopes = ["user", "project"] if scope == "all" else [scope]
    for sc in scopes:
        root = skills_root(sc)
        print(f"== {sc}: {root}")
        if not root.exists():
            print("   (none)")
            continue
        for d in sorted(p for p in root.iterdir() if (p / "SKILL.md").exists()):
            try:
                desc = parse_frontmatter((d / "SKILL.md").read_text(encoding="utf-8")).get("description", "")
            except SystemExit:
                desc = "(invalid frontmatter)"
            print(f"   /{d.name:<28} {desc[:90]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", help="skill folder or SKILL.md to install")
    ap.add_argument("--scope", default="user", choices=["user", "project", "all"])
    ap.add_argument("--name", help="override skill (folder) name")
    ap.add_argument("--force", action="store_true", help="overwrite an existing skill with the same name")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--where", action="store_true", help="print the skills folder for the scope")
    ap.add_argument("--open", metavar="NAME", help="reveal an installed skill folder")
    args = ap.parse_args()

    if args.list:
        return list_skills(args.scope)
    scope = "user" if args.scope == "all" else args.scope
    if args.where:
        print(skills_root(scope))
        return
    if args.open:
        return reveal(skills_root(scope) / args.open)
    if not args.source:
        ap.error("source is required (or use --list / --where / --open)")

    src = Path(args.source).expanduser().resolve()
    if src.is_file():
        src = src.parent
    name = validate(src, args.name)
    dest = skills_root(scope) / name
    if dest.exists():
        if dest.resolve() == src.resolve():
            print(f"[save] already installed at {dest}")
            return
        if not args.force:
            raise SystemExit(f"{dest} already exists. Re-run with --force to overwrite.")
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", "*.pyc"))
    print(f"[save] installed skill '{name}' ({scope} scope) -> {dest}")
    print(f"[save] use it with: /{name}   (new Claude Code sessions pick it up automatically)")


if __name__ == "__main__":
    main()
