<p align="center">
  <img src="photosleuth/assets/logo_256.png" alt="PhotoSleuth" width="128" height="128">
</p>

<h1 align="center">PhotoSleuth</h1>

<p align="center"><b>Image metadata, location and forensics toolkit — desktop app and CLI.</b></p>

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/g33l0/photosleuth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

Extract metadata, pinpoint locations, spot edited photos, reverse-search the web,
and scrub sensitive data — from a native Windows application or the command line.
Developed by **IamG2**.

---

## 📑 Table of Contents

- [Desktop Application](#-desktop-application)
- [Features](#-features)
- [Installation](#-installation)
- [Usage](#-usage)
  - [Desktop Workflow](#desktop-workflow)
  - [Keyboard Shortcuts](#keyboard-shortcuts)
  - [Interactive CLI](#interactive-cli)
  - [Command-Line Mode](#command-line-mode)
  - [Exit Codes](#exit-codes)
- [Configuration](#-configuration)
- [Building the Windows Installer](#-building-the-windows-installer)
- [Python API](#-python-api)
- [Testing](#-testing)
- [Disclaimer](#-disclaimer)
- [License](#-license)

---

## 🖥 Desktop Application

PhotoSleuth ships as a standalone PyQt (PySide6) desktop application that
installs on Windows with no Python required.

| Area | What you get |
| ---- | ------------ |
| **Library** | Drag-and-drop or open a folder; thumbnail grid with GPS and forensic badges; live search across every EXIF tag; filters for geotagged and flagged images |
| **Details** | Zoom/pan viewer with rotate and fit; grouped, searchable metadata tree; side-by-side comparison of any two images |
| **Location** | Address lookup, map links, manual geotagging (type, paste a Maps link, search a place, or copy from another photo), and map export |
| **Forensics** | Embedded-thumbnail vs. image comparison to reveal post-capture edits, perceptual hashes, SHA-256 |
| **Timeline** | Every photo arranged by capture date, grouped by day, month or year |
| **Reverse search** | Google Vision and TinEye via API; Google Lens, Yandex and Bing via browser hand-off |
| **Reports** | PDF, HTML, CSV, JSON and map exports with your own branding and templates |
| **Custody** | Tamper-evident, hash-chained log of every action taken |

Launch it with:

```bash
photosleuth-gui          # installed entry point
photosleuth --gui        # or via the CLI
python -m photosleuth.gui
```

---

## ✨ Features

- **Full EXIF extraction** – camera, lens, exposure, ISO, date, and hundreds of tags.
- **GPS geocoding** – converts coordinates (including altitude and S/W hemispheres) to a
  human-readable address, plus Google Maps and OpenStreetMap links.
- **Reverse image search** – Google Vision web detection and landmark detection.
- **EXIF stripping** – removes EXIF, IPTC, XMP and ICC data from a copy, or in place.
- **Interactive map** – plots all geotagged images on an HTML map (`folium`).
- **CSV export** – exports a metadata table for spreadsheets.
- **Batch processing** – analyse whole folders, optionally recursively; one bad file
  never aborts the run.
- **Persistent configuration & geocode cache** – stored in a per-user directory.
- **Forensics** – compares the embedded thumbnail with the image to reveal
  photos edited after capture; perceptual hashes and SHA-256 for every file.
- **Chain of custody** – tamper-evident, hash-chained log of every action.
- **Reports** – PDF, HTML, CSV and JSON with custom templates and branding.
- **Multi-language** – English, Spanish, French, German, Portuguese and Arabic
  (with right-to-left layout).
- **Interactive menu** – everything is menu-driven; no command-line fu required.

---

## 📦 Installation

1. **Clone** the repository:
   ```bash
   git clone https://github.com/g33l0/photosleuth.git
   cd photosleuth
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install, which puts `photosleuth` and `photosleuth-gui` on your PATH:
   ```bash
   pip install .            # CLI only
   pip install ".[gui]"     # CLI + desktop application
   ```

**Windows users:** grab the installer from the
[Releases page](https://github.com/g33l0/photosleuth/releases) instead — it
needs no Python at all. See
[Building the Windows Installer](#-building-the-windows-installer) to build it
yourself.

---

## 🧭 Usage

### Desktop Workflow

1. **Open** — drag images or a folder onto the window, use **File → Open**, or
   right-click a file in Explorer and choose *Analyze with PhotoSleuth*.
2. **Analyse** — metadata extraction runs in the background with a progress bar
   and a Cancel button; the window stays responsive and one unreadable file
   never stops the batch.
3. **Inspect** — click a thumbnail to fill the *Details*, *Metadata*,
   *Forensics* and *Reverse Search* tabs. Ctrl-click a second image and press
   **Ctrl+D** to compare them field by field.
4. **Investigate** — **Tools → Check All Images** compares every embedded
   thumbnail against its image and flags anything that looks edited. The
   *Timeline* tab arranges the set by capture date.
5. **Act** — set or remove locations (**Ctrl+G**), strip metadata
   (**Ctrl+Shift+S**), or open coordinates in your browser (**Ctrl+M**).
6. **Report** — **Ctrl+E** exports PDF, HTML, CSV, JSON or a map. Every action
   is appended to the chain-of-custody log (**Ctrl+L**).

### Keyboard Shortcuts

| Shortcut | Action |
| -------- | ------ |
| `Ctrl+O` / `Ctrl+Shift+O` | Open images / open a folder |
| `F5` / `Shift+F5` | Analyse pending / re-analyse selected |
| `F6` / `Shift+F6` | Forensics on all / on the selection |
| `Ctrl+D` | Compare the two selected images |
| `Ctrl+G` | Set location |
| `Ctrl+Shift+S` | Strip metadata |
| `Ctrl+M` | Open in Maps |
| `Ctrl+E` | Export report |
| `Ctrl+L` | Chain of custody |
| `Ctrl+,` | Settings |
| `Ctrl` `+` / `-` / `0` / `1` | Zoom in / out / fit / actual size |
| `Esc` | Cancel the running task |
| `Del` | Remove the selection from the library |

### Interactive CLI

```bash
python -m photosleuth        # or: python -m photosleuth.cli
```

or, if installed globally:

```bash
photosleuth
```

The menu covers: single-image and batch analysis, verbose metadata, map links,
saving reports, reverse image search, EXIF stripping, HTML maps, CSV export, and
configuration.

### Command-Line Mode

```bash
# Basic analysis (shows GPS, address, map link)
photosleuth -i vacation.jpg

# Verbose – all EXIF tags
photosleuth -i vacation.jpg -a

# Analyse a directory (add -r to recurse into subfolders)
photosleuth -d ./holiday_photos -r

# Generate an interactive map and CSV from a directory
photosleuth -d ./holiday_photos --map --csv

# Save a JSON or TXT report (a directory produces a JSON array)
photosleuth -d ./holiday_photos -o report.json

# Skip the address lookup (offline, and much faster for big batches)
photosleuth -d ./holiday_photos --no-geocode

# Reverse image search (prompts before uploading; --yes skips the prompt)
photosleuth -i mystery.jpg --search

# Strip EXIF (creates a copy with the _clean suffix)
photosleuth -i secret.jpg --strip

# Strip and overwrite the original (use with care)
photosleuth -i secret.jpg --strip --overwrite --yes

# Configuration
photosleuth --config                              # interactive editor
photosleuth --set-key google_vision=YOUR_KEY      # store an API key
photosleuth --show-config                         # print settings (keys redacted)
```

Run `photosleuth --help` for the full list.

### Exit Codes

| Code | Meaning |
| ---- | ------- |
| `0`  | Success |
| `1`  | Error (missing path, failed search, map with no geotags) |
| `2`  | No image files found |
| `130`| Interrupted with Ctrl+C |

---

## ⚙️ Configuration

Settings live in a per-user directory, so PhotoSleuth behaves the same wherever
you launch it from:

| Platform | Location |
| -------- | -------- |
| Windows  | `%APPDATA%\PhotoSleuth\config.json` |
| Portable | `PhotoSleuthData\config.json` next to the executable |
| Linux    | `~/.config/photosleuth/config.json` |
| macOS    | `~/.config/photosleuth/config.json` |

Set `PHOTOSLEUTH_HOME` to override the location (useful for portable installs).
`photosleuth --show-config` prints the active settings and the exact path.

Configurable options:

- Google Vision API key (required for reverse search)
- TinEye API key (planned – the backend is not implemented yet)
- Default search engine
- Output suffix for stripped images (default: `_clean`) and whether to overwrite
- Geocoding: on/off, request delay, timeout, and cache on/off

The geocode cache is stored next to `config.json` as `geocode_cache.json` and
persists between runs. Clear it from the Configuration menu.

---

## 📦 Building the Windows Installer

```powershell
# From the repository root, in PowerShell:
.\packaging\build_windows.ps1
```

The script creates a virtual environment, installs the build dependencies,
regenerates the icons, runs PyInstaller and then Inno Setup:

| Output | Description |
| ------ | ----------- |
| `dist\PhotoSleuth\` | One-folder application (`PhotoSleuth.exe` + `photosleuth-cli.exe`) |
| `dist\installer\PhotoSleuth-1.1.0-Setup.exe` | Signed-ready installer |

The installer offers optional Explorer integration, "Open with" registration
(it never hijacks your default image viewer) and adding the CLI to `PATH`. It
installs per-user by default, so no administrator prompt appears.

Expect roughly **200 MB installed** and a **~90 MB installer** — Qt, Pillow and
NumPy account for most of it. Pass `-SkipInstaller` to build only the
application folder.

**Portable mode:** drop an empty file named `portable.txt` next to
`PhotoSleuth.exe` and all settings, caches and logs live in a `PhotoSleuthData`
folder beside the program, leaving the host machine untouched.

> **Note on code signing:** the installer is not code-signed. Windows SmartScreen
> will warn on first run until you sign it with your own certificate.

---

## 🐍 Python API

```python
from photosleuth import extract_metadata, strip_exif, export_csv, generate_map
from photosleuth.core import analyze_path

meta = extract_metadata("vacation.jpg")
print(meta["gps"], meta.get("location"))

# Batch: yields (path, metadata, error) so a bad file never stops the loop
records = [m for _, m, err in analyze_path("./photos", recursive=True) if err is None]
export_csv(records, "photos.csv")
generate_map(records, "photos.html")

strip_exif("secret.jpg")  # -> secret_clean.jpg
```

---

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest                      # 262 tests, including offscreen GUI tests
pytest -W error::DeprecationWarning   # run strict
```

GUI tests run on Qt's `offscreen` platform, so they need no display and work in CI.

---

## ⚠️ Disclaimer

- **Ethical use only** – use on images you own or have permission to analyse.
- Reverse search uses the Google Vision API; you need a valid key and **the image
  is uploaded to Google**. Charges may apply – check Google's pricing.
- Geocoding uses Nominatim. PhotoSleuth enforces their one-request-per-second
  policy automatically and caches results to keep request volume low.
- Your images never leave your machine except when you explicitly use `--search`.

---

## 📄 License

MIT – free to use, modify, and distribute with credit to IamG2.

---

## 🙌 Contributing

Feedback, issues, and PRs are always welcome. Let's make PhotoSleuth even better together.

Happy sleuthing!
– IamG2
