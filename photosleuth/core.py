"""Core functionality: metadata extraction, GPS conversion, geocoding."""

import os
import json
from datetime import datetime
from pathlib import Path

try:
    import exifread
except ImportError:
    raise ImportError("Missing 'exifread'. Install: pip install exifread")

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
except ImportError:
    raise ImportError("Missing 'geopy'. Install: pip install geopy")

from .utils import get_cached_geocode, set_cached_geocode


def convert_to_decimal(coord):
    """Convert EXIF GPS coordinate (degrees, minutes, seconds) to decimal."""
    try:
        degrees = float(coord.values[0].num) / float(coord.values[0].den)
        minutes = float(coord.values[1].num) / float(coord.values[1].den)
        seconds = float(coord.values[2].num) / float(coord.values[2].den)
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    except (AttributeError, IndexError, ZeroDivisionError, ValueError):
        return None


def reverse_geocode(lat, lon):
    """Get human‑readable address from coordinates, with caching."""
    # Check cache first
    cached = get_cached_geocode(lat, lon)
    if cached:
        return cached

    geolocator = Nominatim(user_agent="photosleuth_iamg2")
    try:
        location = geolocator.reverse(f"{lat:.6f}, {lon:.6f}", timeout=5)
        address = location.address if location else "Address not found"
    except (GeocoderTimedOut, GeocoderUnavailable):
        address = "Geocoding service unavailable"
    except Exception:
        address = "Error during geocoding"

    set_cached_geocode(lat, lon, address)
    return address


def extract_metadata(image_path):
    """
    Extract all EXIF metadata, parse GPS, and return a structured dict.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"File not found: {image_path}")

    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f, details=False)

    metadata = {
        'file': str(image_path),
        'size': os.path.getsize(image_path),
        'modified': datetime.fromtimestamp(os.path.getmtime(image_path)).isoformat(),
        'exif': {}
    }

    # Convert tags to strings
    for tag, value in tags.items():
        try:
            metadata['exif'][tag] = str(value)
        except:
            metadata['exif'][tag] = repr(value)

    # GPS extraction
    gps_lat = tags.get('GPS GPSLatitude')
    gps_lon = tags.get('GPS GPSLongitude')
    lat_ref = tags.get('GPS GPSLatitudeRef')
    lon_ref = tags.get('GPS GPSLongitudeRef')

    if gps_lat and gps_lon:
        lat = convert_to_decimal(gps_lat)
        lon = convert_to_decimal(gps_lon)
        if lat is not None and lon is not None:
            if lat_ref and lat_ref.values == 'S':
                lat = -lat
            if lon_ref and lon_ref.values == 'W':
                lon = -lon
            metadata['gps'] = {'latitude': lat, 'longitude': lon}
            metadata['location'] = reverse_geocode(lat, lon)
            metadata['map_url'] = f"https://www.google.com/maps?q={lat},{lon}"

    return metadata


def format_output(metadata, show_all=False):
    """Return a formatted string for console output."""
    lines = []
    lines.append(f"\n📄 File: {metadata['file']}")
    lines.append(f"📦 Size: {metadata['size']} bytes")
    lines.append(f"🕒 Modified: {metadata['modified']}")

    if 'gps' in metadata:
        gps = metadata['gps']
        lines.append(f"📍 GPS: {gps['latitude']:.6f}, {gps['longitude']:.6f}")
        if 'location' in metadata:
            lines.append(f"🏠 Address: {metadata['location']}")
        if 'map_url' in metadata:
            lines.append(f"🗺️  Map: {metadata['map_url']}")
    else:
        lines.append("📍 GPS: Not found")

    if show_all and 'exif' in metadata:
        lines.append("\n📋 All EXIF Tags:")
        for tag, val in metadata['exif'].items():
            lines.append(f"   {tag}: {val}")

    return "\n".join(lines)


def save_report(metadata, output_file, fmt='json'):
    """Save metadata to JSON or plain text."""
    if fmt == 'json':
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
    elif fmt == 'txt':
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(format_output(metadata, show_all=True))
    else:
        raise ValueError("Unsupported format. Use 'json' or 'txt'.")