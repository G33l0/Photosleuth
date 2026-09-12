"""Chain-of-custody logging.

Every action that touches an image is appended to a tamper-evident JSON Lines
log: each entry carries the file's SHA-256 at the time of the action and a
hash chain linking it to the previous entry, so a deleted or edited line can be
detected afterwards.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import platform
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import config_home, load_config

GENESIS = "0" * 64
_lock = threading.Lock()


def log_path() -> Path:
    configured = load_config().get("custody", {}).get("log_file")
    if configured:
        return Path(configured).expanduser()
    return config_home() / "chain_of_custody.jsonl"


def _actor() -> Dict[str, str]:
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return {"user": user, "host": host, "platform": platform.platform()}


def _entry_digest(entry: Dict[str, Any]) -> str:
    """Hash the entry's content together with the previous digest."""
    payload = {key: entry[key] for key in sorted(entry) if key != "entry_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.is_file():
        return GENESIS
    previous = GENESIS
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    previous = json.loads(line).get("entry_hash", previous)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return GENESIS
    return previous


def record(
    action: str,
    file_path=None,
    details: Optional[Dict[str, Any]] = None,
    sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Append an action to the custody log and return the stored entry."""
    if not load_config().get("custody", {}).get("enabled", True):
        return {}

    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "actor": _actor(),
        "details": details or {},
    }

    if file_path is not None:
        path = Path(file_path)
        entry["file"] = str(path)
        entry["file_name"] = path.name
        if sha256 is not None:
            entry["sha256"] = sha256
        else:
            try:
                from .forensics import file_hashes

                entry["sha256"] = file_hashes(path, ("sha256",))["sha256"]
                entry["size"] = path.stat().st_size
            except (OSError, ValueError):
                entry["sha256"] = None

    target = log_path()
    with _lock:
        entry["previous_hash"] = _last_hash(target)
        entry["entry_hash"] = _entry_digest(entry)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            # Logging must never take the application down.
            return entry
    return entry


def read_log(path=None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    target = Path(path) if path else log_path()
    entries: List[Dict[str, Any]] = []
    if not target.is_file():
        return entries
    try:
        with open(target, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({"action": "UNPARSEABLE-LINE", "raw": line[:200]})
    except OSError:
        return entries
    return entries[-limit:] if limit else entries


def verify_log(path=None) -> Dict[str, Any]:
    """Re-walk the hash chain and report the first entry that breaks it."""
    entries = read_log(path)
    previous = GENESIS
    for index, entry in enumerate(entries):
        if entry.get("action") == "UNPARSEABLE-LINE":
            return {"valid": False, "entries": len(entries), "broken_at": index,
                    "reason": "Line is not valid JSON."}
        if entry.get("previous_hash") != previous:
            return {"valid": False, "entries": len(entries), "broken_at": index,
                    "reason": "Entry does not link to the previous one; a line was removed or reordered."}
        if _entry_digest(entry) != entry.get("entry_hash"):
            return {"valid": False, "entries": len(entries), "broken_at": index,
                    "reason": "Entry content does not match its hash; it was edited."}
        previous = entry["entry_hash"]
    return {"valid": True, "entries": len(entries), "broken_at": None, "reason": "Chain intact."}


def export_csv(output_file, path=None) -> Path:
    """Flatten the log to CSV for hand-off."""
    import csv

    target = Path(output_file)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    columns = ["timestamp", "action", "file", "sha256", "user", "host", "details", "entry_hash"]
    with open(target, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for entry in read_log(path):
            actor = entry.get("actor", {}) or {}
            writer.writerow({
                "timestamp": entry.get("timestamp", ""),
                "action": entry.get("action", ""),
                "file": entry.get("file", ""),
                "sha256": entry.get("sha256", "") or "",
                "user": actor.get("user", ""),
                "host": actor.get("host", ""),
                "details": json.dumps(entry.get("details", {}), default=str),
                "entry_hash": entry.get("entry_hash", ""),
            })
    return target


def clear_log(path=None) -> None:
    target = Path(path) if path else log_path()
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass


def summarise(entries: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    entries = list(entries if entries is not None else read_log())
    actions: Dict[str, int] = {}
    files = set()
    for entry in entries:
        actions[entry.get("action", "?")] = actions.get(entry.get("action", "?"), 0) + 1
        if entry.get("file"):
            files.add(entry["file"])
    return {
        "total_entries": len(entries),
        "unique_files": len(files),
        "actions": actions,
        "first": entries[0]["timestamp"] if entries else None,
        "last": entries[-1]["timestamp"] if entries else None,
    }
