"""Cloudflare Worker entrypoint shim."""

from __future__ import annotations

from tuno.cloudflare.worker import Default, TunoGame

__all__ = ["Default", "TunoGame"]
