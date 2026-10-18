"""Compatibility entry point for the combined FoxWatch API."""

if __package__ == "api.foxwatch":
    from ..main import app
else:
    from main import app

__all__ = ["app"]
