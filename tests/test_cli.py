"""End-to-end CLI tests."""

import subprocess
import sys

import pytest

from photosleuth.cli import build_parser, main


def run_module(*args, env=None):
    """Run the CLI exactly the way the README tells users to."""
    import os

    environment = dict(os.environ)
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "photosleuth.cli", *args],
        capture_output=True,
        text=True,
        env=environment,
    )


def test_module_execution_produces_output(image_ne, isolated_config):
    """`python -m photosleuth.cli` printed nothing: there was no main guard."""
    result = run_module("-i", str(image_ne), "--no-geocode", env={"PHOTOSLEUTH_HOME": str(isolated_config)})
    assert result.returncode == 0
    assert "GPS" in result.stdout


def test_package_execution_works():
    """`python -m photosleuth` needs a __main__.py."""
    result = subprocess.run(
        [sys.executable, "-m", "photosleuth", "--version"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "PhotoSleuth" in result.stdout


def test_analyze_single_image(capsys, image_ne):
    assert main(["-i", str(image_ne), "--no-geocode", "--no-banner"]) == 0
    assert "48.858" in capsys.readouterr().out


def test_verbose_lists_all_tags(capsys, image_ne):
    main(["-i", str(image_ne), "-a", "--no-geocode", "--no-banner"])
    assert "All EXIF Tags" in capsys.readouterr().out


def test_missing_file_exits_nonzero(capsys, tmp_path):
    assert main(["-i", str(tmp_path / "nope.jpg"), "--no-banner"]) == 1


def test_missing_directory_exits_nonzero(tmp_path):
    assert main(["-d", str(tmp_path / "nope"), "--no-banner"]) == 1


def test_empty_directory_reports_nothing_found(tmp_path):
    assert main(["-d", str(tmp_path), "--no-banner", "-q"]) == 2


def test_batch_tolerates_non_image_files(capsys, tmp_path, image_ne, not_an_image):
    """A stray non-image in the folder must not stop the good files."""
    assert main(["-d", str(tmp_path), "--no-geocode", "--no-banner"]) == 0
    assert "48.858" in capsys.readouterr().out


def test_batch_continues_after_an_extraction_error(capsys, monkeypatch, tmp_path, image_ne, image_sw):
    """A file that genuinely fails to parse is reported and skipped, not fatal."""
    from photosleuth import core

    real = core.extract_metadata
    calls = {"n": 0}

    def flaky(path, geocode=True):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated read failure")
        return real(path, geocode=geocode)

    monkeypatch.setattr(core, "extract_metadata", flaky)
    assert main(["-d", str(tmp_path), "--no-geocode", "--no-banner"]) == 0
    captured = capsys.readouterr()
    assert "simulated read failure" in captured.err
    assert "could not be read" in captured.err


def test_directory_named_like_an_image_is_ignored(tmp_path, image_ne):
    (tmp_path / "album.jpg").mkdir()
    assert main(["-d", str(tmp_path), "--no-geocode", "--no-banner", "-q"]) == 0


def test_output_report_for_a_directory(tmp_path, image_ne, image_sw):
    target = tmp_path / "report.json"
    main(["-d", str(tmp_path), "-o", str(target), "--no-geocode", "--no-banner", "-q"])
    import json

    data = json.loads(target.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 2


def test_csv_and_map_flags(tmp_path, image_ne, image_sw):
    csv_file = tmp_path / "out.csv"
    map_file = tmp_path / "out.html"
    code = main(["-d", str(tmp_path), "--csv", str(csv_file), "--map", str(map_file),
                 "--no-geocode", "--no-banner", "-q"])
    assert code == 0
    assert csv_file.is_file() and map_file.is_file()


def test_map_flag_without_geotags_fails_cleanly(tmp_path, image_plain):
    assert main(["-d", str(tmp_path), "--map", str(tmp_path / "m.html"),
                 "--no-geocode", "--no-banner", "-q"]) == 1


def test_strip_flag(tmp_path, image_ne):
    assert main(["-i", str(image_ne), "--strip", "--no-banner", "-q"]) == 0
    assert (tmp_path / "eiffel_clean.jpg").is_file()


def test_strip_directory(tmp_path, image_ne, image_sw):
    main(["-d", str(tmp_path), "--strip", "--no-banner", "-q"])
    assert (tmp_path / "eiffel_clean.jpg").is_file()
    assert (tmp_path / "south_clean.jpg").is_file()


def test_search_without_key_fails_cleanly(capsys, image_ne):
    code = main(["-i", str(image_ne), "--search", "--yes", "--no-geocode", "--no-banner", "-q"])
    assert code == 1
    assert "API key" in capsys.readouterr().err


def test_set_key_round_trip(capsys):
    from photosleuth import config

    assert main(["--set-key", "google_vision=abc123", "--no-banner"]) == 0
    assert config.get_api_key("google_vision") == "abc123"


def test_set_key_rejects_bad_syntax():
    assert main(["--set-key", "nonsense", "--no-banner"]) == 1


def test_set_key_rejects_unknown_engine():
    assert main(["--set-key", "bing=abc", "--no-banner"]) == 1


def test_show_config_redacts_secrets(capsys):
    main(["--set-key", "google_vision=supersecret", "--no-banner"])
    capsys.readouterr()
    main(["--show-config", "--no-banner"])
    out = capsys.readouterr().out
    assert "supersecret" not in out
    assert "<set>" in out


@pytest.mark.parametrize("flag", ["--csv", "--map"])
def test_report_flags_have_defaults(flag):
    args = build_parser().parse_args([flag])
    assert getattr(args, flag.lstrip("-")) is not None


def test_version_flag_is_capital_v():
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["-V"])
    assert excinfo.value.code == 0
