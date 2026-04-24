"""corroborate — register, verify, and audit numeric claims in documents."""

from corroborate.audit import (
    AuditReport,
    ClassifiedDuplicate,
    DuplicateJudge,
    DuplicateVerdict,
    NearDuplicate,
    audit,
    classify_near_duplicates,
)
from corroborate.build import BuildPaths, build
from corroborate.claims import Claim, ClaimSet, Collision, load_all, scan_sidecars
from corroborate.renderers import name_to_macro, write_claims_md, write_numbers_tex

__all__ = [
    "AuditReport",
    "BuildPaths",
    "Claim",
    "ClaimSet",
    "ClassifiedDuplicate",
    "Collision",
    "DuplicateJudge",
    "DuplicateVerdict",
    "NearDuplicate",
    "audit",
    "build",
    "classify_near_duplicates",
    "load_all",
    "name_to_macro",
    "scan_sidecars",
    "write_claims_md",
    "write_numbers_tex",
]

__version__ = "0.1.0"
