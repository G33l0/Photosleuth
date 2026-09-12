#!/usr/bin/env python3
"""Propagate photosleuth.__version__ into the files that hard-code it.

Run after bumping the version in photosleuth/__init__.py:

    python tools/sync_version.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from photosleuth import __version__  # noqa: E402


def sync_installer() -> bool:
    path = ROOT / "packaging" / "installer.iss"
    text = path.read_text(encoding="utf-8")
    updated = re.sub(
        r'(#define\s+AppVersion\s+")[^"]*(")',
        rf"\g<1>{__version__}\g<2>",
        text,
        count=1,
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def sync_pyproject() -> bool:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    updated = re.sub(
        r'(?m)^(version\s*=\s*")[^"]*(")',
        rf"\g<1>{__version__}\g<2>",
        text,
        count=1,
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def sync_version_info() -> bool:
    path = ROOT / "packaging" / "version_info.txt"
    parts = [int(p) for p in re.findall(r"\d+", __version__)][:3]
    parts += [0] * (4 - len(parts))
    tuple_text = ", ".join(str(p) for p in parts)

    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = re.sub(r"filevers=\([^)]*\)", f"filevers=({tuple_text})", text)
    updated = re.sub(r"prodvers=\([^)]*\)", f"prodvers=({tuple_text})", updated)
    updated = re.sub(
        r"(StringStruct\('(?:File|Product)Version', ')[^']*(')",
        rf"\g<1>{__version__}\g<2>",
        updated,
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def installer_version() -> str:
    path = ROOT / "packaging" / "installer.iss"
    match = re.search(r'#define\s+AppVersion\s+"([^"]+)"', path.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def pyproject_version() -> str:
    path = ROOT / "pyproject.toml"
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def main() -> int:
    changed = [
        name
        for name, changed_flag in (
            ("packaging/installer.iss", sync_installer()),
            ("pyproject.toml", sync_pyproject()),
            ("packaging/version_info.txt", sync_version_info()),
        )
        if changed_flag
    ]
    print(f"PhotoSleuth {__version__}")
    if changed:
        for name in changed:
            print(f"  updated {name}")
    else:
        print("  everything already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
