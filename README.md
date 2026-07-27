```markdown
# 🔍 PhotoSleuth

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/IamG2/photosleuth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)

**Ultimate Image Metadata & Location Analyzer** – developed by **IamG2**

PhotoSleuth is a lightweight yet powerful command‑line tool that extracts every scrap of metadata from your images – EXIF, GPS coordinates, camera settings, timestamps, and more. It then turns raw GPS data into a human‑readable address and a Google Maps link, so you can see exactly where the photo was taken.

---

## 📑 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Usage](#-usage)
  - [Interactive Mode](#interactive-mode-recommended)
  - [Command‑Line Mode](#command-line-mode)
- [Examples](#-examples)
- [Disclaimer](#-disclaimer)
- [Efficiency](#-efficiency)
- [License](#-license)
- [Contributing](#-contributing)

---

## ✨ Features

- **Full EXIF extraction** – camera model, shutter speed, ISO, date, lens, flash, and hundreds of other tags.
- **GPS to address** – automatic reverse geocoding using OpenStreetMap (with built‑in caching to avoid rate limits).
- **Google Maps link** – generates a direct URL to view the location in your browser.
- **Verbose mode** – dump every single metadata field for forensic or deep‑dive analysis.
- **Batch processing** – scan all images in a folder at once.
- **Export reports** – save results as structured JSON or plain text.
- **Interactive menu** – no command‑line fu required; just run and explore.
- **Fast & lightweight** – only two dependencies; geocoding results are cached for instant reuse.

---

## 📦 Installation

1. **Clone the repository** (or download the ZIP):
   ```bash
   git clone https://github.com/IamG2/photosleuth.git
   cd photosleuth
```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Install as a global command:
   ```bash
   pip install .
   ```
   Now you can run photosleuth from anywhere.

---

🧭 Usage

Interactive Mode (Recommended)

If you just want to poke around without memorising flags, run:

```bash
python -m photosleuth.cli
```

or, if installed globally:

```bash
photosleuth
```

You’ll see a friendly menu:

```
============================================================
  PHOTOSLEUTH - Interactive Mode
============================================================
  1. Analyze a single image
  2. Analyze all images in a directory
  3. Show all metadata (verbose)
  4. Generate map link for GPS
  5. Save report to file
  0. Exit
============================================================
```

Choose an option, provide the requested paths, and PhotoSleuth does the rest.

---

Command‑Line Mode

For scripting or quick one‑offs, use the CLI arguments:

```bash
# Basic analysis (shows GPS, address, map link if available)
photosleuth -i vacation.jpg

# Show every EXIF tag (verbose)
photosleuth -i vacation.jpg -a

# Analyze an entire folder
photosleuth -d ./holiday_photos

# Save a JSON report (or .txt for plain text)
photosleuth -i vacation.jpg -o report.json
photosleuth -i vacation.jpg -o report.txt
```

---

📸 Examples

Input: A photo taken with a smartphone that has GPS enabled.

Output (summary):

```
📄 File: beach_sunset.jpg
📦 Size: 2456789 bytes
🕒 Modified: 2025-07-20T18:32:11
📍 GPS: 34.052235, -118.243683
🏠 Address: 123 Ocean Ave, Santa Monica, CA 90401, USA
🗺️  Map: https://www.google.com/maps?q=34.052235,-118.243683
```

Verbose output adds dozens of EXIF fields like Image Make, Model, Exposure Time, F-Number, ISO, Date/Time Original, etc.

---

⚠️ Disclaimer

· Ethical use only – use PhotoSleuth on images you own, have explicit permission to analyse, or for legitimate forensic/educational purposes.
· Geocoding relies on the free Nominatim service. Please respect their usage policy – limit to 1 request per second and provide a proper User-Agent (we already do).
· Privacy – your images stay on your machine; no data is ever uploaded or shared.

---

⚡ Efficiency

· Geocoding cache – once an address is resolved for a coordinate pair, it’s stored in memory. Any subsequent photo with the same location returns the address instantly – no repeated network calls.
· Minimal dependencies – only exifread and geopy; the tool is light and starts fast.
· Offline‑friendly – if an image lacks GPS, no external requests are made; you can use it entirely offline.

---

📄 License

This project is licensed under the MIT License – feel free to use, modify, and distribute, provided you retain the original author credit (IamG2).

---

🙌 Contributing

Found a bug? Have an idea for a new feature? Open an issue or submit a pull request – contributions are always welcome!

---

Happy sleuthing!
– IamG2

```