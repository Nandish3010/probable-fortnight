"""Seeded synthetic tenant generator. Entry point: `python -m data.generator`."""
from .generate import AS_OF, HISTORY_DAYS, Generator, generate

__all__ = ["AS_OF", "HISTORY_DAYS", "Generator", "generate"]
