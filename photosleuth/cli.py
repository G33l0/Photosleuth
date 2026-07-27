#!/usr/bin/env python3
"""Command‑line interface and interactive menu for PhotoSleuth."""

import sys
import os
import argparse
from pathlib import Path

from . import __version__, __author__
from .utils import BANNER
from .core import extract_metadata, format_output, save_report


def interactive_menu():
    """Run the interactive menu."""
    while True:
        print("\n" + "="*60)
        print("  PHOTOSLEUTH - Interactive Mode")
        print("="*60)
        print("  1. Analyze a single image")
        print("  2. Analyze all images in a directory")
        print("  3. Show all metadata (verbose)")
        print("  4. Generate map link for GPS")
        print("  5. Save report to file")
        print("  0. Exit")
        print("="*60)

        choice = input("Select an option: ").strip()
        if choice == '0':
            print("👋 Goodbye!")
            break
        elif choice == '1':
            img_path = input("Enter image path: ").strip()
            if not os.path.isfile(img_path):
                print("❌ File not found.")
                continue
            meta = extract_metadata(img_path)
            print(format_output(meta, show_all=False))
        elif choice == '2':
            dir_path = input("Enter directory path: ").strip()
            if not os.path.isdir(dir_path):
                print("❌ Directory not found.")
                continue
            img_exts = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif')
            files = [f for f in Path(dir_path).iterdir() if f.suffix.lower() in img_exts]
            if not files:
                print("No image files found.")
                continue
            for f in files:
                print(f"\n--- Processing {f.name} ---")
                meta = extract_metadata(f)
                print(format_output(meta, show_all=False))
        elif choice == '3':
            img_path = input("Enter image path to view all metadata: ").strip()
            if not os.path.isfile(img_path):
                print("❌ File not found.")
                continue
            meta = extract_metadata(img_path)
            print(format_output(meta, show_all=True))
        elif choice == '4':
            img_path = input("Enter image path with GPS: ").strip()
            if not os.path.isfile(img_path):
                print("❌ File not found.")
                continue
            meta = extract_metadata(img_path)
            if 'map_url' in meta:
                print(f"🗺️  Google Maps: {meta['map_url']}")
            else:
                print("No GPS data in this image.")
        elif choice == '5':
            img_path = input("Enter image path to save report: ").strip()
            if not os.path.isfile(img_path):
                print("❌ File not found.")
                continue
            out_file = input("Output file path (e.g., report.json): ").strip()
            if not out_file:
                print("No file name provided.")
                continue
            meta = extract_metadata(img_path)
            fmt = 'json' if out_file.endswith('.json') else 'txt'
            try:
                save_report(meta, out_file, fmt)
                print(f"✅ Report saved to {out_file}")
            except Exception as e:
                print(f"❌ Error saving: {e}")
        else:
            print("Invalid option. Try again.")


def main():
    parser = argparse.ArgumentParser(
        description="PhotoSleuth – Analyze image metadata and GPS location",
        epilog=f"Developed by {__author__}"
    )
    parser.add_argument("-i", "--image", help="Path to a single image file")
    parser.add_argument("-d", "--directory", help="Path to a directory of images")
    parser.add_argument("-o", "--output", help="Save report to file (JSON or TXT)")
    parser.add_argument("-a", "--all", action="store_true", help="Show all EXIF tags")
    parser.add_argument("-v", "--version", action="version", version=f"PhotoSleuth {__version__}")
    args = parser.parse_args()

    # Print banner
    print(BANNER)

    # If no arguments, launch interactive
    if not any(vars(args).values()):
        interactive_menu()
        return

    # Single image
    if args.image:
        if not os.path.isfile(args.image):
            print(f"❌ File not found: {args.image}")
            sys.exit(1)
        meta = extract_metadata(args.image)
        print(format_output(meta, show_all=args.all))
        if args.output:
            fmt = 'json' if args.output.endswith('.json') else 'txt'
            save_report(meta, args.output, fmt)
            print(f"✅ Report saved to {args.output}")

    # Directory
    if args.directory:
        if not os.path.isdir(args.directory):
            print(f"❌ Directory not found: {args.directory}")
            sys.exit(1)
        img_exts = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif')
        files = [f for f in Path(args.directory).iterdir() if f.suffix.lower() in img_exts]
        if not files:
            print("No image files found.")
            sys.exit(0)
        for f in files:
            print(f"\n--- {f.name} ---")
            meta = extract_metadata(f)
            print(format_output(meta, show_all=args.all))
        # Optionally, if output is given, we could save per file or combine;
        # for simplicity, we only handle single image output.