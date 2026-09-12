#!/usr/bin/env python3
"""Command-line interface and interactive menu for PhotoSleuth."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __author__, __version__
from . import config as config_module
from .core import analyze_path, extract_metadata, format_for_file, format_output, save_report
from .privacy import default_output_path, strip_exif
from .reports import export_csv, generate_map, geotagged
from .utils import banner, find_images, safe_print

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOTHING_FOUND = 2


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def _collect(target: str, recursive: bool, geocode: bool, show_all: bool, quiet: bool) -> List[Dict[str, Any]]:
    """Analyse a file or directory, printing as it goes, skipping bad files."""
    records: List[Dict[str, Any]] = []
    failures = 0
    for path, metadata, error in analyze_path(target, recursive=recursive, geocode=geocode):
        if error is not None:
            failures += 1
            safe_print(f"⚠️  Skipped {path.name}: {error}", stream=sys.stderr)
            continue
        records.append(metadata)
        if not quiet:
            safe_print(f"\n--- {path.name} ---")
            safe_print(format_output(metadata, show_all=show_all))
    if failures and not quiet:
        safe_print(f"\n⚠️  {failures} file(s) could not be read.", stream=sys.stderr)
    return records


def _prompt(text: str) -> str:
    try:
        return input(text).strip().strip('"').strip("'")
    except EOFError:
        return ""


def _confirm(text: str) -> bool:
    return _prompt(f"{text} (y/n): ").lower().startswith("y")


# --------------------------------------------------------------------------
# interactive menus
# --------------------------------------------------------------------------

def config_menu() -> None:
    """Interactive configuration editor."""
    while True:
        config = config_module.load_config()
        keys = config.get("api_keys", {})
        privacy = config.get("privacy", {})
        safe_print("\n=== Configuration ===")
        safe_print(f"  Config file: {config_module.config_path()}")
        safe_print(f"  1. Google Vision API key  [{'set' if keys.get('google_vision') else 'not set'}]")
        safe_print(f"  2. TinEye API key         [{'set' if keys.get('tineye') else 'not set'}] (planned)")
        safe_print(f"  3. Default search engine  [{config.get('default_search_engine')}]")
        safe_print(f"  4. Privacy options        [suffix '{privacy.get('output_suffix')}', "
                   f"overwrite {privacy.get('overwrite')}]")
        safe_print(f"  5. Geocoding options      [{'on' if config.get('geocoding', {}).get('enabled') else 'off'}]")
        safe_print("  6. Clear geocode cache")
        safe_print("  0. Back to main menu")

        choice = _prompt("Select: ")
        try:
            if choice == "0":
                return
            elif choice == "1":
                config_module.set_api_key("google_vision", _prompt("Google Vision API key: "))
                safe_print("✅ Key saved.")
            elif choice == "2":
                config_module.set_api_key("tineye", _prompt("TinEye API key: "))
                safe_print("✅ Key saved.")
            elif choice == "3":
                engine = _prompt(f"Engine ({'/'.join(config_module.SEARCH_ENGINES)}): ")
                config_module.set_default_engine(engine)
                safe_print("✅ Default engine set.")
            elif choice == "4":
                suffix = _prompt("Suffix for cleaned images (blank = keep current): ")
                overwrite = _confirm("Overwrite originals when stripping?")
                config_module.set_privacy_options(output_suffix=suffix or None, overwrite=overwrite)
                safe_print("✅ Privacy options saved.")
            elif choice == "5":
                enabled = _confirm("Enable reverse geocoding (address lookup)?")
                config_module.update_config(geocoding={"enabled": enabled})
                from .core import reset_geocoder
                from .utils import reset_default_cache
                reset_geocoder()
                reset_default_cache()
                safe_print("✅ Geocoding options saved.")
            elif choice == "6":
                from .utils import default_cache
                default_cache().clear()
                safe_print("✅ Geocode cache cleared.")
            else:
                safe_print("Invalid choice.")
        except ValueError as exc:
            safe_print(f"❌ {exc}")
        except OSError as exc:
            safe_print(f"❌ Could not write config: {exc}")


def interactive_menu() -> None:
    """Run the interactive menu."""
    while True:
        safe_print("\n" + "=" * 60)
        safe_print("  PHOTOSLEUTH - Interactive Mode")
        safe_print("=" * 60)
        safe_print("  1. Analyze a single image")
        safe_print("  2. Analyze all images in a directory")
        safe_print("  3. Show all metadata (verbose)")
        safe_print("  4. Generate map link for GPS")
        safe_print("  5. Save report to file")
        safe_print("  6. Reverse image search")
        safe_print("  7. Strip EXIF from an image")
        safe_print("  8. Generate interactive map from a directory")
        safe_print("  9. Export directory metadata to CSV")
        safe_print("  c. Configuration")
        safe_print("  0. Exit")
        safe_print("=" * 60)

        choice = _prompt("Select an option: ").lower()
        try:
            if choice == "0":
                safe_print("👋 Goodbye!")
                return
            elif choice == "c":
                config_menu()
            elif choice in ("1", "3", "4"):
                _menu_single_image(choice)
            elif choice == "2":
                path = _prompt("Enter directory path: ")
                if not os.path.isdir(path):
                    safe_print("❌ Directory not found.")
                    continue
                recursive = _confirm("Include subdirectories?")
                records = _collect(path, recursive, True, False, quiet=False)
                safe_print(f"\n✅ Analysed {len(records)} image(s); {len(geotagged(records))} geotagged.")
            elif choice == "5":
                _menu_save_report()
            elif choice == "6":
                _menu_search()
            elif choice == "7":
                _menu_strip()
            elif choice in ("8", "9"):
                _menu_directory_report(choice)
            else:
                safe_print("Invalid option. Try again.")
        except KeyboardInterrupt:
            safe_print("\nCancelled.")
        except Exception as exc:  # noqa: BLE001 - the menu must survive any single action
            safe_print(f"❌ {type(exc).__name__}: {exc}")


def _menu_single_image(choice: str) -> None:
    path = _prompt("Enter image path: ")
    if not os.path.isfile(path):
        safe_print("❌ File not found.")
        return
    metadata = extract_metadata(path)
    if choice == "4":
        if metadata.get("map_url"):
            safe_print(f"🗺️  Google Maps: {metadata['map_url']}")
            safe_print(f"🔗 OpenStreetMap: {metadata['osm_url']}")
            if metadata.get("location"):
                safe_print(f"🏠 Address: {metadata['location']}")
        else:
            safe_print("No GPS data in this image.")
        return
    safe_print(format_output(metadata, show_all=(choice == "3")))


def _menu_save_report() -> None:
    path = _prompt("Enter image or directory path: ")
    if not os.path.exists(path):
        safe_print("❌ Path not found.")
        return
    out_file = _prompt("Output file path (e.g., report.json): ")
    if not out_file:
        safe_print("No file name provided.")
        return
    records = _collect(path, recursive=False, geocode=True, show_all=False, quiet=True)
    if not records:
        safe_print("❌ Nothing to report.")
        return
    payload = records[0] if len(records) == 1 else records
    saved = save_report(payload, out_file, format_for_file(out_file))
    safe_print(f"✅ Report saved to {saved}")


def _menu_search() -> None:
    from .search import SearchError, format_search_results, reverse_image_search

    path = _prompt("Enter image path: ")
    if not os.path.isfile(path):
        safe_print("❌ File not found.")
        return
    safe_print("⚠️  This uploads the image to Google Vision.")
    if not _confirm("Continue?"):
        safe_print("Cancelled.")
        return
    try:
        safe_print("Searching…")
        safe_print(format_search_results(reverse_image_search(path)))
    except SearchError as exc:
        safe_print(f"❌ {exc}")


def _menu_strip() -> None:
    path = _prompt("Enter image path: ")
    if not os.path.isfile(path):
        safe_print("❌ File not found.")
        return
    overwrite = _confirm("Overwrite the original (destructive)?")
    if overwrite and not _confirm(f"This permanently removes metadata from {Path(path).name}. Are you sure?"):
        safe_print("Cancelled.")
        return
    destination, removed = strip_exif(path, overwrite=overwrite)
    safe_print(f"🧹 Removed {removed} metadata tag(s) → {destination}")


def _menu_directory_report(choice: str) -> None:
    path = _prompt("Enter directory path: ")
    if not os.path.isdir(path):
        safe_print("❌ Directory not found.")
        return
    recursive = _confirm("Include subdirectories?")
    images = find_images(path, recursive=recursive)
    if not images:
        safe_print("No image files found.")
        return
    safe_print(f"Analysing {len(images)} image(s)…")
    records = _collect(path, recursive, True, False, quiet=True)

    if choice == "8":
        out_file = _prompt("Output HTML file (default: photosleuth_map.html): ") or "photosleuth_map.html"
        try:
            safe_print(f"🗺️  Map saved to {generate_map(records, out_file)}")
        except ValueError as exc:
            safe_print(f"❌ {exc}")
    else:
        out_file = _prompt("Output CSV file (default: photosleuth.csv): ") or "photosleuth.csv"
        safe_print(f"✅ CSV saved to {export_csv(records, out_file)}")


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photosleuth",
        description="PhotoSleuth - Analyze image metadata and GPS location",
        epilog=f"Developed by {__author__}",
    )
    source = parser.add_argument_group("input")
    source.add_argument("-i", "--image", help="Path to a single image file")
    source.add_argument("-d", "--directory", help="Path to a directory of images")
    source.add_argument("-r", "--recursive", action="store_true", help="Recurse into subdirectories")

    output = parser.add_argument_group("output")
    output.add_argument("-o", "--output", help="Save report to file (.json or .txt)")
    output.add_argument("-a", "--all", action="store_true", help="Show all EXIF tags")
    output.add_argument("--csv", nargs="?", const="photosleuth.csv", metavar="FILE",
                        help="Export metadata to CSV (default: photosleuth.csv)")
    output.add_argument("--map", nargs="?", const="photosleuth_map.html", metavar="FILE",
                        help="Plot geotagged images on an interactive map (default: photosleuth_map.html)")
    output.add_argument("-q", "--quiet", action="store_true", help="Suppress per-image console output")
    output.add_argument("--no-banner", action="store_true", help="Do not print the ASCII banner")

    actions = parser.add_argument_group("actions")
    actions.add_argument("--search", action="store_true", help="Reverse image search (uploads the image)")
    actions.add_argument("--strip", action="store_true", help="Write a copy with all metadata removed")
    actions.add_argument("--overwrite", action="store_true", help="With --strip, replace the original in place")
    actions.add_argument("--no-geocode", action="store_true", help="Skip the address lookup (offline / faster)")
    actions.add_argument("--yes", action="store_true", help="Assume yes for confirmation prompts")

    settings = parser.add_argument_group("configuration")
    settings.add_argument("--config", action="store_true", help="Open the interactive configuration menu")
    settings.add_argument("--set-key", metavar="ENGINE=KEY", help="Store an API key, e.g. google_vision=abc123")
    settings.add_argument("--show-config", action="store_true", help="Print the active configuration and exit")

    parser.add_argument("-V", "--version", action="version", version=f"PhotoSleuth {__version__}")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.no_banner and not args.quiet:
        safe_print(banner())

    # --- configuration-only actions -------------------------------------
    if args.set_key:
        if "=" not in args.set_key:
            safe_print("❌ Expected ENGINE=KEY, e.g. --set-key google_vision=abc123", stream=sys.stderr)
            return EXIT_ERROR
        engine, _, key = args.set_key.partition("=")
        try:
            config_module.set_api_key(engine.strip(), key)
        except ValueError as exc:
            safe_print(f"❌ {exc}", stream=sys.stderr)
            return EXIT_ERROR
        safe_print(f"✅ Saved {engine.strip()} key to {config_module.config_path()}")
        return EXIT_OK

    if args.show_config:
        import json

        safe_print(f"Config file: {config_module.config_path()}")
        redacted = config_module.load_config()
        redacted["api_keys"] = {
            name: ("<set>" if value else "") for name, value in redacted.get("api_keys", {}).items()
        }
        safe_print(json.dumps(redacted, indent=2))
        return EXIT_OK

    if args.config:
        config_menu()
        return EXIT_OK

    # No input given: fall back to the interactive menu.
    if not args.image and not args.directory:
        interactive_menu()
        return EXIT_OK

    target = args.image or args.directory
    if args.image and not os.path.isfile(args.image):
        safe_print(f"❌ File not found: {args.image}", stream=sys.stderr)
        return EXIT_ERROR
    if args.directory and not os.path.isdir(args.directory):
        safe_print(f"❌ Directory not found: {args.directory}", stream=sys.stderr)
        return EXIT_ERROR

    # --- strip is destructive-ish: handle it before analysis -------------
    if args.strip:
        return _run_strip(args, target)

    records = _collect(
        target,
        recursive=args.recursive,
        geocode=not args.no_geocode,
        show_all=args.all,
        quiet=args.quiet,
    )
    if not records:
        safe_print("No image files found.", stream=sys.stderr)
        return EXIT_NOTHING_FOUND

    exit_code = EXIT_OK

    if args.output:
        payload = records[0] if len(records) == 1 else records
        saved = save_report(payload, args.output, format_for_file(args.output))
        safe_print(f"✅ Report saved to {saved}")

    if args.csv:
        safe_print(f"✅ CSV saved to {export_csv(records, args.csv)}")

    if args.map:
        try:
            safe_print(f"🗺️  Map saved to {generate_map(records, args.map)}")
        except (ValueError, ImportError) as exc:
            safe_print(f"❌ Map not generated: {exc}", stream=sys.stderr)
            exit_code = EXIT_ERROR

    if args.search:
        exit_code = _run_search(args, records) or exit_code

    return exit_code


def _run_strip(args, target: str) -> int:
    paths = [Path(target)] if args.image else find_images(target, recursive=args.recursive)
    if not paths:
        safe_print("No image files found.", stream=sys.stderr)
        return EXIT_NOTHING_FOUND

    if args.overwrite and not args.yes:
        safe_print(f"⚠️  --overwrite permanently removes metadata from {len(paths)} file(s).")
        if not _confirm("Continue?"):
            safe_print("Cancelled.")
            return EXIT_OK

    failures = 0
    for path in paths:
        try:
            destination, removed = strip_exif(path, overwrite=args.overwrite)
            safe_print(f"🧹 {path.name}: removed {removed} tag(s) → {destination}")
        except (OSError, ValueError) as exc:
            failures += 1
            safe_print(f"⚠️  {path.name}: {exc}", stream=sys.stderr)
    return EXIT_ERROR if failures else EXIT_OK


def _run_search(args, records: List[Dict[str, Any]]) -> int:
    from .search import SearchError, format_search_results, reverse_image_search

    if not args.yes:
        safe_print(f"\n⚠️  Reverse search uploads {len(records)} image(s) to a third-party service.")
        if not _confirm("Continue?"):
            safe_print("Cancelled.")
            return EXIT_OK

    failures = 0
    for metadata in records:
        try:
            safe_print(format_search_results(reverse_image_search(metadata["file"])))
        except (SearchError, OSError) as exc:
            failures += 1
            safe_print(f"❌ {Path(metadata['file']).name}: {exc}", stream=sys.stderr)
    return EXIT_ERROR if failures else EXIT_OK


def run() -> int:
    """Console-script entry point with friendly interrupt handling."""
    try:
        return main()
    except KeyboardInterrupt:
        safe_print("\nInterrupted.", stream=sys.stderr)
        return 130
    except BrokenPipeError:  # e.g. `photosleuth -d imgs | head`
        try:
            sys.stdout.close()
        except Exception:
            pass
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(run())
