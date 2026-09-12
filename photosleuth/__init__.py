"""PhotoSleuth - Ultimate Image Metadata & Location Analyzer."""

__version__ = "1.1.0"
__author__ = "IamG2"

__all__ = [
    "__version__",
    "__author__",
    "extract_metadata",
    "format_output",
    "save_report",
    "reverse_geocode",
    "analyze_path",
    "strip_exif",
    "export_csv",
    "generate_map",
]


def __getattr__(name):
    """Import submodules lazily so `import photosleuth` stays cheap."""
    if name in ("extract_metadata", "format_output", "save_report", "reverse_geocode", "analyze_path"):
        from . import core

        return getattr(core, name)
    if name == "strip_exif":
        from .privacy import strip_exif

        return strip_exif
    if name in ("export_csv", "generate_map"):
        from . import reports

        return getattr(reports, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
