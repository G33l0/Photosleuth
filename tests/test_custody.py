"""Tests for the tamper-evident chain-of-custody log."""

import json

from photosleuth import custody


def test_entries_are_appended_with_hashes(image_ne):
    custody.record("analyze", image_ne, {"note": "first"})
    custody.record("strip", image_ne, {"note": "second"})
    entries = custody.read_log()
    assert len(entries) == 2
    assert all(len(entry["sha256"]) == 64 for entry in entries)
    assert entries[1]["previous_hash"] == entries[0]["entry_hash"]


def test_chain_verifies(image_ne):
    for index in range(4):
        custody.record("analyze", image_ne, {"index": index})
    result = custody.verify_log()
    assert result["valid"] is True
    assert result["entries"] == 4


def test_edited_entry_breaks_the_chain(image_ne):
    custody.record("analyze", image_ne)
    custody.record("export", image_ne)
    path = custody.log_path()

    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["action"] = "something-else"
    lines[0] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = custody.verify_log()
    assert result["valid"] is False
    assert result["broken_at"] == 0


def test_removed_entry_breaks_the_chain(image_ne):
    for _ in range(3):
        custody.record("analyze", image_ne)
    path = custody.log_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

    result = custody.verify_log()
    assert result["valid"] is False
    assert result["broken_at"] == 1


def test_logging_can_be_disabled(image_ne):
    from photosleuth import config

    config.update_config(custody={"enabled": False})
    custody.record("analyze", image_ne)
    assert custody.read_log() == []


def test_csv_export(tmp_path, image_ne):
    custody.record("analyze", image_ne, {"k": "v"})
    target = custody.export_csv(tmp_path / "log.csv")
    text = target.read_text(encoding="utf-8-sig")
    assert "timestamp,action,file,sha256" in text
    assert "analyze" in text


def test_summarise(image_ne, image_sw):
    custody.record("analyze", image_ne)
    custody.record("analyze", image_sw)
    custody.record("strip", image_ne)
    stats = custody.summarise()
    assert stats["total_entries"] == 3
    assert stats["unique_files"] == 2
    assert stats["actions"]["analyze"] == 2


def test_empty_log_is_valid():
    assert custody.verify_log()["valid"] is True
