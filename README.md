```markdown
# 🔍 PhotoSleuth

**Ultimate Image Metadata & Location Analyzer**  
*Developed by IamG2*

---

## 🚀 What is PhotoSleuth?

PhotoSleuth is a powerful yet simple tool that extracts **every bit of metadata** from your images – EXIF, GPS coordinates, camera settings, timestamps, and more.  
It then **converts GPS data** into a human‑readable address and provides a **Google Maps link** to show exactly where the photo was taken.

---

## ✨ Features

- 📸 **Extract all EXIF tags** – camera model, shutter speed, ISO, date, etc.  
- 🌍 **GPS to address** – automatic reverse geocoding (with caching for speed)  
- 🗺️ **Google Maps link** – one‑click to view the location  
- 📋 **Verbose mode** – see every single metadata field  
- 📁 **Batch processing** – analyze all images in a folder at once  
- 💾 **Export reports** – save as JSON or plain text  
- 🖥️ **Interactive menu** – explore without command‑line arguments  
- ⚡ **Efficient** – geocoding results are cached to avoid repeated API calls  

---

## 📦 Installation

1. **Clone or download** this repository.
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. (Optional) Install the package locally:

```bash
pip install .
```

Now you can run it from anywhere with photosleuth.

---

🧭 Usage

Interactive Mode (Recommended)

Simply run the script without arguments:

```bash
python -m photosleuth.cli
```

or if installed:

```bash
photosleuth
```

You’ll see a menu with options to analyze images, view reports, and more.

Command‑Line Mode (for automation)

```bash
# Analyze a single image, show GPS and map link
photosleuth -i photo.jpg

# Show all EXIF tags
photosleuth -i photo.jpg -a

# Analyze all images in a folder
photosleuth -d ./vacation_photos

# Save a JSON report
photosleuth -i photo.jpg -o report.json

# Save a text report
photosleuth -i photo.jpg -o report.txt
```

---

⚠️ Disclaimer

· PhotoSleuth is intended for legitimate and ethical use only – e.g., your own photos, forensic analysis with permission, or educational purposes.
· Reverse geocoding uses the free Nominatim service. Please respect their usage policy (max 1 request per second, proper user_agent).
· The tool does not upload or share your images; all processing is done locally.

---

🛠️ Efficiency

· Geocoding cache: Once an address is fetched for a coordinate pair, it is stored in memory so subsequent analyses of the same location are instantaneous.
· Lightweight: Uses only two external libraries (exifread, geopy).
· No network I/O unless GPS data is found – perfect for offline use.

---

📄 License

MIT – free to use, modify, and distribute with credit to IamG2.

---

🙌 Contributing

Feel free to open issues or pull requests for improvements, new features, or bug fixes.

---

Happy sleuthing!
– IamG2

```