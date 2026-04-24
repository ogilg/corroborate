"""Drift audit: diff live sidecars against committed state in git HEAD.

Reports: claims whose `value` or `statement` changed, claims added or
removed, claims flagged `source="manual:..."` or `"superseded:..."` (which
cannot be auto-verified).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from vernier.claims import Claim, load_all


@dataclass
class AuditReport:
    total_live: int
    committed_baseline: int
    added: list[str]
    removed: list[str]
    changed: list[tuple[Claim, Claim]]  # (prior, live)
    manual: list[Claim]
    superseded: list[Claim]

    @property
    def clean(self) -> bool:
        return not (self.added or self.removed or self.changed)


def _load_committed(claims_dir: Path, repo_root: Path) -> dict[str, Claim]:
    """Load every sidecar as it appears in HEAD."""
    try:
        rel_dir = claims_dir.relative_to(repo_root)
    except ValueError:
        rel_dir = claims_dir
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", str(rel_dir)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    committed: dict[str, Claim] = {}
    for rel in result.stdout.splitlines():
        if not rel.endswith(".json"):
            continue
        blob = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        if not blob:
            continue
        payload = json.loads(blob)
        for raw in payload["claims"]:
            c = Claim.from_dict(raw)
            committed[c.name] = c
    return committed


def audit(claims_dir: Path | str, repo_root: Path | str | None = None) -> AuditReport:
    """Compare the current sidecars against what is committed to git."""
    claims_dir = Path(claims_dir).resolve()
    if repo_root is None:
        repo_root = claims_dir
    repo_root = Path(repo_root).resolve()

    live = {c.name: c for c in load_all(claims_dir)}
    committed = _load_committed(claims_dir, repo_root)

    added = sorted(set(live) - set(committed))
    removed = sorted(set(committed) - set(live))
    changed: list[tuple[Claim, Claim]] = []
    manual: list[Claim] = []
    superseded: list[Claim] = []
    for name, c in sorted(live.items()):
        if name in committed:
            prior = committed[name]
            if prior.value != c.value or prior.statement != c.statement:
                changed.append((prior, c))
        if c.source.startswith("manual:"):
            manual.append(c)
        elif c.source.startswith("superseded:"):
            superseded.append(c)

    return AuditReport(
        total_live=len(live),
        committed_baseline=len(committed),
        added=added,
        removed=removed,
        changed=changed,
        manual=manual,
        superseded=superseded,
    )


def print_report(report: AuditReport) -> None:
    print(f"Total live claims: {report.total_live}")
    print(f"Committed baseline: {report.committed_baseline}")
    print()
    if report.changed:
        print(f"CHANGED ({len(report.changed)}):")
        for prior, live in report.changed:
            print(f"  {live.name}")
            if prior.value != live.value:
                print(f"    value: {prior.value!r} -> {live.value!r}")
            if prior.statement != live.statement:
                print(f"    statement changed")
        print()
    if report.added:
        print(f"ADDED ({len(report.added)}): {', '.join(report.added[:20])}"
              + (" ..." if len(report.added) > 20 else ""))
        print()
    if report.removed:
        print(f"REMOVED ({len(report.removed)}): {', '.join(report.removed)}")
        print()
    if report.superseded:
        print(f"SUPERSEDED ({len(report.superseded)}):")
        for c in report.superseded:
            print(f"  {c.name}  [{c.source}]")
        print()
    if report.manual:
        print(f"MANUAL ({len(report.manual)}): not auto-verifiable")
        for c in report.manual[:10]:
            print(f"  {c.name}  [{c.source}]")
        if len(report.manual) > 10:
            print(f"  ... {len(report.manual) - 10} more")
        print()
    if report.clean:
        print("No drift.")
