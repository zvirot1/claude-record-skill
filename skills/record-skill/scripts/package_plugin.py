#!/usr/bin/env python3
"""
package_plugin.py - wrap a local skill folder as an installable Cowork plugin.

Claude Code loads skills from ~/.claude/skills. Cowork does not read that path at all:
it loads skills from plugins. This turns one skill folder into a .plugin file (a zip
with the manifest at its root) that Cowork installs with its "Save plugin" button, so
a skill built once runs in both places without going through the cloud account.

Encodes the constraints found the hard way:
  * Cowork's validator rejects XML tags in a skill description.
  * Skills under skills/ are NOT exposed as slash commands in Cowork - only
    commands/*.md are - so a thin command wrapper is generated unless --no-command.
  * A command description over 60 characters is truncated in the UI.

Usage:
  python package_plugin.py <skill-dir> [--plugin-name NAME] [--out DIR]
                           [--version X.Y.Z] [--author NAME] [--no-command]

Example:
  python package_plugin.py ~/.claude/skills/calc-exercise
  -> ./dist/calc-exercise.plugin
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
XML_TAG_RE = re.compile(r"<[^>\s][^>]*>")
SKIP_NAMES = {".DS_Store", "__pycache__"}


def parse_frontmatter(md: Path) -> dict:
    text = md.read_text(encoding="utf-8")
    m = re.match(r"^﻿?---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        raise SystemExit(f"{md} must start with a YAML frontmatter block")
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def lint_frontmatter(raw: str) -> list:
    """Catch frontmatter that a strict YAML parser rejects.

    The regex parsers here and in Claude Code are lenient, but `claude plugin validate`
    is not, and a skill whose frontmatter fails to parse "loads with empty metadata
    (all frontmatter fields silently dropped)" - it installs and then never triggers.
    The usual cause is a colon followed by a space inside an unquoted value, which YAML
    reads as a nested mapping.
    """
    problems = []
    for line in raw.splitlines():
        if ":" not in line or line.startswith((" ", "\t")) or line.strip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        quoted = (len(value) > 1 and value[0] == value[-1] and value[0] in "\"'")
        if quoted:
            continue
        if ": " in value:
            problems.append(
                f"{key.strip()!r} contains a colon followed by a space, which YAML reads as a "
                f"nested mapping. Replace it with a dash, or quote the whole value."
            )
        if value.startswith(("*", "&", "!", "%", "@", "`")):
            problems.append(f"{key.strip()!r} starts with {value[0]!r}, which YAML treats specially; quote the value.")
        if " #" in value:
            problems.append(f"{key.strip()!r} contains ' #', which YAML reads as a comment; quote the value.")
    return problems


def validate(skill_name: str, description: str, plugin_name: str, version: str) -> None:
    problems = []
    if not NAME_RE.match(skill_name):
        problems.append(f"skill name {skill_name!r} must be kebab-case")
    if not NAME_RE.match(plugin_name):
        problems.append(f"plugin name {plugin_name!r} must be kebab-case")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        problems.append(f"version {version!r} must be semver, e.g. 0.1.0")
    if not description:
        problems.append("the skill has no description; Cowork needs one to trigger it")
    if len(description) > 1024:
        problems.append(f"description is {len(description)} chars; the limit is 1024")
    tags = XML_TAG_RE.findall(description)
    if tags:
        problems.append(
            "Cowork rejects XML tags in a description: %s - rewrite them without angle brackets"
            % ", ".join(tags))
    if problems:
        raise SystemExit("Cannot package:\n" + "\n".join("  - " + p for p in problems))


def short_description(description: str, limit: int = 240) -> str:
    """A manifest blurb that ends on a sentence or a word, never mid-token."""
    first = description.split(". ")[0].strip().rstrip(".")
    if len(first) <= limit:
        return first + "."
    return first[:limit].rsplit(" ", 1)[0].rstrip(",;-") + "..."


def command_stub(skill_name: str, description: str) -> str:
    short = description.split(".")[0].strip()
    if len(short) > 59:
        short = short[:56].rstrip() + "..."
    return f"""---
description: {short}
argument-hint: [what to work on]
---

Read `${{CLAUDE_PLUGIN_ROOT}}/skills/{skill_name}/SKILL.md` and follow it exactly. It is the
authoritative instructions for this task; this command exists only so the skill is reachable as a
slash command, which is the one thing a skills/ folder does not provide in Cowork.

The user said: $ARGUMENTS

If that is empty, ask for what the skill needs rather than guessing.
"""


def readme(plugin_name: str, skill_name: str, description: str) -> str:
    return f"""# {plugin_name}

A Cowork plugin wrapping the local skill `{skill_name}`.

{description}

## Install

Accept the `.plugin` file in chat (press **Save plugin**), then start a **new** session - plugins
load at session start.

Two ways to invoke it:
- `/{skill_name}` - the slash command.
- Just describe the task; the skill triggers from its description, which is the more reliable
  route in Cowork.

## Where it runs

Cowork executes tools in a Linux VM, so any step in this skill that needs the user's own desktop
is host-only. Steps that work on files, APIs or the shell run anywhere.

Built with `package_plugin.py` from the record-skill toolkit. The skill itself stays on the user's
machine; nothing here is stored in a cloud account.
"""


def copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*SKIP_NAMES, "*.pyc"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skill_dir", type=Path, help="folder containing SKILL.md")
    ap.add_argument("--plugin-name", help="plugin name (default: the skill name)")
    ap.add_argument("--out", type=Path, default=Path("dist"), help="output folder (default ./dist)")
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--author", default=None, help="author name for the manifest")
    ap.add_argument("--no-command", action="store_true",
                    help="do not generate commands/<name>.md (no slash command in Cowork)")
    args = ap.parse_args()

    skill_dir = args.skill_dir.expanduser().resolve()
    if skill_dir.is_file():
        skill_dir = skill_dir.parent
    md = skill_dir / "SKILL.md"
    if not md.exists():
        raise SystemExit(f"No SKILL.md in {skill_dir}")

    fm = parse_frontmatter(md)
    raw = re.match(r"^\ufeff?---\r?\n(.*?)\r?\n---\r?\n", md.read_text(encoding="utf-8"), re.S).group(1)
    bad = lint_frontmatter(raw)
    if bad:
        raise SystemExit("Cannot package - SKILL.md frontmatter is not valid YAML:\n"
                         + "\n".join("  - " + b for b in bad))
    skill_name = fm.get("name") or skill_dir.name
    description = fm.get("description", "")
    plugin_name = args.plugin_name or skill_name
    validate(skill_name, description, plugin_name, args.version)

    manifest = {
        "name": plugin_name,
        "version": args.version,
        "description": short_description(description),
    }
    if args.author:
        manifest["author"] = {"name": args.author}

    tmp = Path(tempfile.mkdtemp()) / plugin_name
    (tmp / ".claude-plugin").mkdir(parents=True)
    (tmp / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp / "skills").mkdir()
    copy_tree(skill_dir, tmp / "skills" / skill_name)
    if not args.no_command:
        (tmp / "commands").mkdir()
        (tmp / "commands" / f"{skill_name}.md").write_text(
            command_stub(skill_name, description), encoding="utf-8")
    (tmp / "README.md").write_text(readme(plugin_name, skill_name, description), encoding="utf-8")

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{plugin_name}.plugin"
    # Zip into a temporary file first: writing straight into a synced or
    # permission-restricted output folder can fail halfway and leave a broken archive.
    staged = Path(tempfile.mkdtemp()) / f"{plugin_name}.plugin"
    with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(tmp.rglob("*")):
            if path.is_file() and path.name not in SKIP_NAMES:
                z.write(path, str(path.relative_to(tmp)).replace("\\", "/"))
    shutil.move(str(staged), out_file)

    with zipfile.ZipFile(out_file) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"archive is corrupt at {bad}")
        names = z.namelist()
    print(f"[package] {out_file}  ({out_file.stat().st_size} bytes)")
    for n in names:
        print(f"           {n}")
    print(f"[package] install it in Cowork with Save plugin, then start a new session and use "
          f"/{skill_name} or just describe the task.")


if __name__ == "__main__":
    main()
