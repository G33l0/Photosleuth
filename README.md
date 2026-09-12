# 🔍 PhotoSleuth

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/g33l0/photosleuth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

**The all‑in‑one image analysis toolkit** – extract metadata, pinpoint locations, reverse‑search the web, and scrub sensitive data.
Developed by **IamG2**.

---

## 📑 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Usage](#-usage)
  - [Interactive Mode](#interactive-mode)
  - [Command-Line Mode](#command-line-mode)
  - [Exit Codes](#exit-codes)
- [Configuration](#-configuration)
- [Python API](#-python-api)
- [Testing](#-testing)
- [Disclaimer](#-disclaimer)
- [License](#-license)

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

3. (Optional) Install globally, which puts a `photosleuth` command on your PATH:
   ```bash
   pip install .
   ```

---

## 🧭 Usage

### Interactive Mode

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
pytest
```

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
