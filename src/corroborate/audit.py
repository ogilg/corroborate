"""Drift + staleness audit for the claims registry.

Reports:
  - Diff vs HEAD: added / removed / changed (value or statement).
  - Unverifiable by convention: source starting with ``manual:``, ``superseded:``,
    or ``frozen:``.
  - Producer/data integrity: orphans and staleness —
    * ORPHAN        — claim.source points at a file that doesn't exist.
    * NAME-ORPHAN   — source file exists but no longer mentions the claim name.
    * LOGIC-STALE   — source file's last-commit timestamp is newer than the
                      claim's computed_at.
    * DATA-STALE    — any data_path has mtime newer than computed_at.

The integrity checks are mechanical and cheap — they use only sidecar data
and git metadata, never re-running producers.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from corroborate.claims import Claim, load_all


_TAG_PREFIXES = ("manual:", "superseded:", "frozen:")


@dataclass
class AuditReport:
    total_live: int
    committed_baseline: int
    added: list[str]
    removed: list[str]
    changed: list[tuple[Claim, Claim]]  # (prior, live)
    manual: list[Claim]
    superseded: list[Claim]
    frozen: list[Claim]
    orphan: list[tuple[Claim, str]]        # (claim, reason)
    name_orphan: list[tuple[Claim, str]]
    logic_stale: list[tuple[Claim, str]]   # (claim, "producer edited YYYY-MM-DD")
    data_stale: list[tuple[Claim, str]]    # (claim, "<path> newer")

    @property
    def clean(self) -> bool:
        return not (
            self.added
            or self.removed
            or self.changed
            or self.orphan
            or self.name_orphan
            or self.logic_stale
            or self.data_stale
        )


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


def _source_is_tag(source: str) -> bool:
    """True for convention tags (manual:/superseded:/frozen:), which skip path checks."""
    return any(source.startswith(p) for p in _TAG_PREFIXES)


_NAME_SPLIT_RE = re.compile(r"[\s\-_]+")


def _name_registered(text: str, name: str) -> bool:
    """Heuristic: does the producer file appear to register this claim name?

    Accepts either:
      - The exact quoted form (producer uses a literal string), or
      - Most meaningful tokens appear (handles f-string names like
        ``f"Foo {persona} bar"`` where only static fragments survive).
    """
    if f'"{name}"' in text or f"'{name}'" in text:
        return True
    tokens = [t for t in _NAME_SPLIT_RE.split(name) if len(t) >= 4]
    if not tokens:
        return False
    present = sum(1 for t in tokens if t in text)
    return present / len(tokens) >= 0.5


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _check_integrity(
    c: Claim, repo_root: Path
) -> tuple[str | None, str | None, str | None, list[str]]:
    """Return (orphan_reason, name_orphan_reason, logic_stale_reason, data_stale_reasons)."""
    orphan_reason: str | None = None
    name_orphan_reason: str | None = None
    logic_stale_reason: str | None = None
    data_stale_reasons: list[str] = []

    computed = _parse_iso(c.computed_at)

    if not _source_is_tag(c.source):
        src_path = (repo_root / c.source).resolve() if not Path(c.source).is_absolute() else Path(c.source)
        if not src_path.exists():
            orphan_reason = f"source path not found: {c.source}"
        else:
            try:
                text = src_path.read_text()
            except (OSError, UnicodeDecodeError):
                text = ""
            if not _name_registered(text, c.name):
                name_orphan_reason = f"{c.source} does not register {c.name!r}"

            if computed is not None:
                # Use file mtime — catches local edits and is robust to the
                # "edit then run then commit" pattern where the commit timestamp
                # ends up later than computed_at but the file content is stable.
                try:
                    mtime = src_path.stat().st_mtime
                except OSError:
                    mtime = None
                if mtime is not None and mtime > computed.timestamp():
                    src_mtime = datetime.fromtimestamp(mtime, tz=computed.tzinfo)
                    logic_stale_reason = (
                        f"{c.source} mtime {src_mtime.isoformat()} "
                        f"is after claim computed_at {c.computed_at}"
                    )

    if computed is not None:
        computed_unix = computed.timestamp()
        for dp in c.data_paths:
            dp_path = (repo_root / dp).resolve() if not Path(dp).is_absolute() else Path(dp)
            if not dp_path.exists():
                continue
            try:
                mtime = dp_path.stat().st_mtime
            except OSError:
                continue
            if mtime > computed_unix:
                data_stale_reasons.append(
                    f"{dp} mtime={datetime.fromtimestamp(mtime, tz=computed.tzinfo).isoformat()}"
                )

    return orphan_reason, name_orphan_reason, logic_stale_reason, data_stale_reasons


def audit(claims_dir: Path | str, repo_root: Path | str | None = None) -> AuditReport:
    """Compare the current sidecars against git HEAD and check producer/data integrity."""
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
    frozen: list[Claim] = []
    orphan: list[tuple[Claim, str]] = []
    name_orphan: list[tuple[Claim, str]] = []
    logic_stale: list[tuple[Claim, str]] = []
    data_stale: list[tuple[Claim, str]] = []

    for name, c in sorted(live.items()):
        if name in committed:
            prior = committed[name]
            if prior.value != c.value or prior.statement != c.statement:
                changed.append((prior, c))
        if c.source.startswith("manual:"):
            manual.append(c)
        elif c.source.startswith("superseded:"):
            superseded.append(c)
        elif c.source.startswith("frozen:"):
            frozen.append(c)

        orph, name_orph, logic_s, data_s = _check_integrity(c, repo_root)
        if orph:
            orphan.append((c, orph))
        elif name_orph:
            name_orphan.append((c, name_orph))
        if logic_s:
            logic_stale.append((c, logic_s))
        for reason in data_s:
            data_stale.append((c, reason))

    return AuditReport(
        total_live=len(live),
        committed_baseline=len(committed),
        added=added,
        removed=removed,
        changed=changed,
        manual=manual,
        superseded=superseded,
        frozen=frozen,
        orphan=orphan,
        name_orphan=name_orphan,
        logic_stale=logic_stale,
        data_stale=data_stale,
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
    if report.orphan:
        print(f"ORPHAN ({len(report.orphan)}): producer file missing")
        for c, reason in report.orphan:
            print(f"  {c.name}  [{reason}]")
        print()
    if report.name_orphan:
        print(f"NAME-ORPHAN ({len(report.name_orphan)}): registration not found in producer")
        for c, reason in report.name_orphan:
            print(f"  {c.name}  [{reason}]")
        print()
    if report.logic_stale:
        print(f"LOGIC-STALE ({len(report.logic_stale)}): producer edited after claim")
        for c, reason in report.logic_stale:
            print(f"  {c.name}  [{reason}]")
        print()
    if report.data_stale:
        print(f"DATA-STALE ({len(report.data_stale)}): input newer than claim")
        for c, reason in report.data_stale:
            print(f"  {c.name}  [{reason}]")
        print()
    if report.superseded:
        print(f"SUPERSEDED ({len(report.superseded)}):")
        for c in report.superseded:
            print(f"  {c.name}  [{c.source}]")
        print()
    if report.frozen:
        print(f"FROZEN ({len(report.frozen)}): hardcoded; rerun pipeline to restore")
        for c in report.frozen:
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
