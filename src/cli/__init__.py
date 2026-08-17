"""tapedeck: the entrypoint that orchestrates ingest, transcribe, archive,
index, ask and wiki into one executable (SPEC-cli-001)."""

from .main import main

__all__ = ["main"]
