"""bili — a small, dependency-free Bilibili CLI.

Design goals (the parts worth keeping from other implementations):
  * a stable output envelope: {ok, schema_version, data, error}
  * honest auth state (no "logged in" until a cookie actually works)
  * media downloads that survive CDN anti-scraping (Range requests)
  * zero third-party runtime dependencies
"""

from importlib.metadata import PackageNotFoundError, version

try:  # single source of truth: pyproject.toml
    __version__ = version("bilicli")
except PackageNotFoundError:  # running from a source checkout without install
    __version__ = "0.0.0+source"

SCHEMA_VERSION = "1"
