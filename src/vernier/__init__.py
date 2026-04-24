"""vernier — register, verify, and audit numeric claims in documents."""

from vernier.audit import AuditReport, audit
from vernier.build import BuildPaths, build
from vernier.claims import Claim, ClaimSet, load_all
from vernier.renderers import name_to_macro, write_claims_md, write_numbers_tex

__all__ = [
    "AuditReport",
    "BuildPaths",
    "Claim",
    "ClaimSet",
    "audit",
    "build",
    "load_all",
    "name_to_macro",
    "write_claims_md",
    "write_numbers_tex",
]

__version__ = "0.1.0"
