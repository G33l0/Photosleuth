"""Utilities: banner, formatting, cache."""

BANNER = r"""
   ██████╗ ██╗  ██╗ ██████╗ ████████╗ ██████╗ ███████╗██╗     ███████╗██╗   ██╗████████╗██╗  ██╗
   ██╔══██╗██║  ██║██╔═══██╗╚══██╔══╝██╔═══██╗██╔════╝██║     ██╔════╝██║   ██║╚══██╔══╝██║  ██║
   ██████╔╝███████║██║   ██║   ██║   ██║   ██║█████╗  ██║     █████╗  ██║   ██║   ██║   ███████║
   ██╔═══╝ ██╔══██║██║   ██║   ██║   ██║   ██║██╔══╝  ██║     ██╔══╝  ██║   ██║   ██║   ██╔══██║
   ██║     ██║  ██║╚██████╔╝   ██║   ╚██████╔╝███████╗███████╗███████╗╚██████╔╝   ██║   ██║  ██║
   ╚═╝     ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚══════╝╚══════╝╚══════╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝
   
   🔍  PhotoSleuth v1.0  |  Developed by IamG2  |  Unleash the secrets of your images
"""

# Simple cache for geocoding to avoid repeated API calls
_geo_cache = {}

def get_cached_geocode(lat, lon):
    key = f"{lat:.6f},{lon:.6f}"
    return _geo_cache.get(key)

def set_cached_geocode(lat, lon, address):
    key = f"{lat:.6f},{lon:.6f}"
    _geo_cache[key] = address