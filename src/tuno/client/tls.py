"""TLS helpers for the packaged terminal client."""

from __future__ import annotations

import ssl

try:
    import certifi
except Exception:  # pragma: no cover - fall back to platform trust store if certifi isn't present
    certifi = None


def build_client_ssl_context() -> ssl.SSLContext:
    """Build a TLS client context pinned to the bundled certifi CA bundle.

    PyInstaller builds on macOS do not always discover the platform trust store in the same
    way as an unfrozen Python environment. Using certifi gives the packaged client a stable CA
    bundle for `wss://` connections such as Cloudflare Workers.
    """
    ssl_context = ssl.create_default_context()
    if certifi is not None:
        ssl_context.load_verify_locations(certifi.where())
    return ssl_context
