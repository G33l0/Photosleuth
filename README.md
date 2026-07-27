# 🔍 PhotoSleuth

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/IamG2/photosleuth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)

**The all‑in‑one image analysis toolkit** – extract metadata, pinpoint locations, reverse‑search the web, and scrub sensitive data.  
Developed by **IamG2**.

---

## 📑 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Usage](#-usage)
  - [Interactive Mode](#interactive-mode)
  - [Command‑Line Mode](#command-line-mode)
- [Configuration](#-configuration)
- [Examples](#-examples)
- [Disclaimer](#-disclaimer)
- [Efficiency](#-efficiency)
- [License](#-license)
- [Contributing](#-contributing)

---

## ✨ Features

- **Full EXIF extraction** – camera, lens, exposure, ISO, date, and hundreds of tags.
- **GPS geocoding** – converts coordinates to a human‑readable address and generates a Google Maps link.
- **Reverse image search** – uses Google Vision API to find web entities and matching pages (configurable).
- **EXIF stripping** – removes all metadata from a copy, protecting your privacy.
- **Interactive map** – plots all geotagged images on an HTML map (using `folium`).
- **CSV export** – exports metadata tables for further analysis in spreadsheets.
- **Batch processing** – analyse entire folders at once.
- **Persistent configuration** – API keys and privacy settings stored in `config.json`.
- **Interactive menu** – no command‑line fu required; everything is menu‑driven.

---

## 📦 Installation

1. **Clone** the repository:
   ```bash
   git clone https://github.com/IamG2/photosleuth.git
   cd photosleuth
```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Install globally:
   ```bash
   pip install .
   ```

---

🧭 Usage

Interactive Mode

Just run:

```bash
python -m photosleuth.cli
```

or, if installed globally:

```bash
photosleuth
```

You’ll see a menu with options for:

· Analysing images (single or batch)
· Viewing verbose metadata
· Generating a map or CSV report
· Reverse image searching
· Stripping EXIF
· Configuring API keys and preferences

Command‑Line Mode

For scripting and automation:

```bash
# Basic analysis (shows GPS, address, map link)
photosleuth -i vacation.jpg

# Verbose – all EXIF tags
photosleuth -i vacation.jpg -a

# Analyse a directory
photosleuth -d ./holiday_photos

# Generate an interactive map and CSV from a directory
photosleuth -d ./holiday_photos --map --csv

# Reverse image search
photosleuth -i mystery.jpg --search

# Strip EXIF (creates a copy with _clean suffix)
photosleuth -i secret.jpg --strip

# Strip and overwrite the original (use with care)
photosleuth -i secret.jpg --strip --overwrite
```

---

⚙️ Configuration

API keys and privacy settings are stored in config.json (created automatically on first run).
Use the Interactive Menu → Configuration to set:

· Google Vision API key (required for reverse search)
· TinEye API key (planned)
· Default search engine
· Output suffix for stripped images (default: _clean)
· Whether to overwrite originals when stripping

You can also edit config.json manually.

---

📸 Examples

Reverse Search Output:

```
Entities found:
  - Eiffel Tower (score: 0.92)
  - Paris (score: 0.85)
Pages with matching images: 124
Full matching images: 3
```

EXIF stripping:

· Input: vacation.jpg
· Output: vacation_clean.jpg (no EXIF)

---

⚠️ Disclaimer

· Ethical use only – use on images you own or have permission to analyse.
· Reverse search uses Google Vision API; you need a valid API key. Charges may apply – check Google’s pricing.
· Geocoding uses Nominatim – respect their usage policy (1 req/sec).
· Your images never leave your machine except when explicitly using the reverse search API (image is sent to Google).

---

⚡ Efficiency

· Geocoding cache – addresses are stored to avoid repeated network calls.
· Batch processing – optimised to handle large folders.
· Minimal dependencies – only essential libraries.

---

📄 License

MIT – free to use, modify, and distribute with credit to IamG2.

---

🙌 Contributing

Feedback, issues, and PRs are always welcome. Let’s make PhotoSleuth even better together.

---

Happy sleuthing!
– IamG2