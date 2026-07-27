
---

### `setup.py` (optional, for pip install)
```python
from setuptools import setup, find_packages

setup(
    name="photosleuth",
    version="1.0.0",
    author="IamG2",
    description="Ultimate Image Metadata & Location Analyzer",
    packages=find_packages(),
    install_requires=["exifread>=2.3.0", "geopy>=2.2.0"],
    entry_points={"console_scripts": ["photosleuth=photosleuth.cli:main"]},
    classifiers=["Programming Language :: Python :: 3"],
)