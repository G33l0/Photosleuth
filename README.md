<p align="center">
  <img src="photosleuth/assets/logo_256.png" alt="PhotoSleuth" width="128" height="128">
</p>

<h1 align="center">PhotoSleuth</h1>

<p align="center"><b>Image metadata, location and forensics toolkit — desktop app and CLI.</b></p>

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/G33l0/Photosleuth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

Extract metadata, pinpoint locations, spot edited photos, reverse-search the web,
and scrub sensitive data — from a native Windows application or the command line.
Developed by **IamG2**.

---

## 📑 Table of Contents

- [Desktop Application](#-desktop-application)
- [Working Offline](#-working-offline)
- [Geolocation](#-geolocation)
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
| **Geolocate** | The Evidence Board: shadow geometry, metadata cross-checks and landmark resection fused into one probability map |
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

## 📴 Working Offline

**PhotoSleuth is an offline tool that can use the internet, not an online tool
that breaks without it.** Everything below runs with no connection at all:

| Works offline | Needs the internet |
| ------------- | ------------------ |
| EXIF and metadata extraction | Address lookup (new coordinates) |
| Forensics: thumbnail comparison, hashes | Map tiles for areas you have not visited |
| Time-zone consistency, GPS quality, view cone | Reverse image search |
| Shadow and solar geolocation, resection | Place-name search when geotagging |
| Measurements, compare, timeline | Update checks |
| Metadata stripping and manual geotagging | |
| Every report: PDF, HTML, CSV, JSON, maps | |
| Chain of custody | |

### How it degrades

- **Nothing hangs.** A feature that needs the network finds out in
  milliseconds rather than waiting for a socket timeout inside a batch.
- **Caches keep working.** Addresses you have looked up before and map tiles
  you have already viewed are stored on disk and used offline. Pan around an
  area while connected and it is available later.
- **Exported maps are self-contained.** Leaflet is embedded in the HTML rather
  than pulled from a CDN, so an exported map opens and positions its markers
  with no connection; only the basemap needs one, and the page says so.
- **Static map PNGs still plot.** Without tiles the markers are drawn on a
  plain background rather than failing.
- **It recovers by itself.** Connectivity is re-checked in the background and
  features re-enable when it returns.

### Working offline on purpose

The status bar shows **Online**, **Offline** or **Working offline**, and
clicking it switches mode. **Work offline** is a privacy control as much as a
connectivity one: with it on, no image, coordinate or query leaves the machine
for any reason, and PhotoSleuth does not even probe for a connection.

That matters for the material this tool is pointed at. Reverse image search
uploads the picture to a third party; address lookup sends coordinates. Offline
mode guarantees neither happens.

---

## 🧭 Geolocation

Where was this photograph taken? No single technique answers that. Each one
rules territory **out**, and where several agree is where the picture was taken.
PhotoSleuth's **Evidence Board** is built around that idea: every analyser
contributes a *constraint* — a band, a circle, a cone — and the board multiplies
them into one probability surface, then tells you which evidence supports the
answer and which fights it.

### What each technique contributes

| Technique | What it measures | What it gives you |
| --------- | ---------------- | ----------------- |
| **Time-zone consistency** | GPS clock (UTC) vs camera clock (local) vs the real zone at those coordinates | Catches spoofed coordinates and mis-set clocks |
| **UTC-offset band** | The offset alone, even with no coordinates | A longitude band |
| **GPS quality** | DOP, satellite count, fix method | An honest error radius instead of a bare point |
| **View cone** | `GPSImgDirection` + the lens field of view | What the camera was *looking at*, not just where it stood |
| **Shadow → sun elevation** | A vertical object and its shadow | The sun's height above the horizon |
| **Circle of equal altitude** | Sun elevation at a known UTC instant | Every point on Earth that saw the sun that high |
| **Latitude from shadow** | Sun elevation at a local *solar* time | A latitude band (longitude cancels out) |
| **Time of day** | Sun elevation at a known place and date | The one or two moments it could have been |
| **North arrow** | Shadow direction + solar position | Which way is north *in the photograph* |
| **Three-point resection** | Angles between three identified landmarks | The camera's position, often to within metres |

### How to use it

1. Select an analysed image and open **Tools → Geolocate** (`F7`).
2. **Metadata** tab → *Read metadata evidence*. Instant, offline, and it will
   tell you straight away if the coordinates and the clock disagree.
3. **Shadow** tab → *Measure shadow on photo* (`F8`), then click three points:
   the top of a vertical object, its base, and the tip of its shadow. Set the
   capture time in UTC and press *Add to board*.
4. **Landmarks** tab → mark a landmark in the photo, then click the same place
   on the map. Three pairs and *Solve position* fixes the camera.
5. Press **Fuse evidence**. The map shows the probability surface and ranked
   candidates; selecting one breaks down how every constraint scored there.

### Honest limits

- **Shadows rarely produce a point.** They produce bands, and above all they
  *disprove*. A shadow is at its most powerful when it shows a claimed place
  and time cannot both be true.
- **Clock time is not solar time.** France runs about 1.9 h ahead of its own
  sun and western China about 3 h. PhotoSleuth requires a UTC instant for the
  exact techniques and converts explicitly for the rest, because feeding wall
  clock time into a solar calculation gives a confidently wrong latitude.
- **A time-zone mismatch is graded, not binary.** Up to three hours is reported
  as *questionable* rather than *inconsistent*: a camera left on the previous
  zone after travelling looks exactly like that.
- **Resection needs a known lens.** The angles come from the field of view, so
  a file with no focal length cannot be resected.
- **Confidence is not truth.** A high score means the constraints you supplied
  agree — no more. The per-constraint breakdown is there so the reasoning can
  be checked rather than trusted.

The map is drawn from OpenStreetMap tiles, cached on disk and fetched only as
you pan. Map data © OpenStreetMap contributors.

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
- **Offline-first** – everything but address lookup, map tiles, reverse search
  and update checks works with no connection; a one-click "work offline" mode
  guarantees nothing leaves the machine.
- **Persistent configuration & geocode cache** – stored in a per-user directory.
- **Geolocation** – shadow geometry, solar position, EXIF cross-checks and
  landmark resection, fused into a single probability map with a per-constraint
  audit trail.
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
   git clone https://github.com/G33l0/Photosleuth.git
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
[Releases page](https://github.com/G33l0/Photosleuth/releases) instead — it
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
| `F7` | Open the Evidence Board |
| `F8` | Measure a shadow on the photo |
| `F9` | Reverse image search (needs a connection) |
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

Caches live beside it: `geocode_cache.json` for looked-up addresses and
`tile_cache/` for map tiles. Both are used offline and can be cleared from
**Settings → Network**.
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

Expect roughly **220 MB installed** and an installer around **80–90 MB**. Qt
(119 MB) and NumPy (41 MB) are the bulk and both are load-bearing: Qt is the
interface, NumPy is the geolocation fusion engine. Measured on Linux; a Windows
build is slightly smaller because the GTK and X11 libraries are not needed.
Pass `-SkipInstaller` to build only the application folder.

Three things keep it from being larger than that:

- **The time-zone check ships a 43 KB raster, not a 32 MB library.**
  `timezonefinder`'s boundary polygons are baked down to a quarter-degree grid
  by `tools/build_timezone_raster.py`. It agrees with the full library on 98.9%
  of random points, and *every* disagreement is flagged as near-a-border rather
  than reported as fact.
- **Maps use a vendored Leaflet (160 KB), not the folium stack**, which also
  makes exported maps work offline.
- **Unused Qt libraries are dropped from the bundle.** Excluding a PySide6
  module does not remove the Qt library behind it, so the QML, Quick and PDF
  stacks are filtered out explicitly — about 20 MB.

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

Geolocation works headlessly too:

```python
from datetime import datetime, timezone
from photosleuth.geolocation import solar, shadow, exif_geo
from photosleuth.geolocation.constraints import EvidenceBoard

when = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)

# A 1 m pole casting a 0.8 m shadow puts the sun about 51 degrees up.
observation = shadow.ShadowObservation(object_length=1.0, shadow_length=0.8)

board = EvidenceBoard(shadow.constraints(observation, moment=when))
board.constraints += exif_geo.analyze(meta)["constraints"]

for candidate in board.candidates(count=3):
    print(candidate.rank, candidate.latitude, candidate.longitude, candidate.score)
```

---

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest                      # 420 tests, including offscreen GUI tests
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
