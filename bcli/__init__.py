"""bcli — a small, dependency-free Bilibili CLI.

Design goals (the parts worth keeping from other implementations):
  * a stable output envelope: {ok, schema_version, data, error}
  * honest auth state (no "logged in" until a cookie actually works)
  * media downloads that survive CDN anti-scraping (Range requests)
  * zero third-party runtime dependencies
"""

__version__ = "0.1.0"
SCHEMA_VERSION = "1"
