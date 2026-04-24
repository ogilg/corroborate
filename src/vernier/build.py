"""Merge per-producer sidecars into the audit surface + macro file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vernier.claims import load_all
from vernier.renderers import write_claims_md, write_numbers_tex


@dataclass
class BuildPaths:
    """Where sidecars live and where outputs go. Supply what applies to your project."""

    claims_dir: Path
    claims_md: Path | None = None
    numbers_tex: Path | None = None
    title: str = "Claims registry"


def build(paths: BuildPaths) -> int:
    """Load every sidecar, render the requested outputs. Returns claim count."""
    claims = load_all(paths.claims_dir)
    if paths.numbers_tex is not None:
        write_numbers_tex(claims, paths.numbers_tex)
    if paths.claims_md is not None:
        write_claims_md(claims, paths.claims_md, title=paths.title)
    return len(claims)
