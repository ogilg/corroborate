"""Audit integrity tests: ORPHAN / NAME-ORPHAN / LOGIC-STALE / DATA-STALE / FROZEN."""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from corroborate import ClaimSet
from corroborate.audit import audit


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, env=env, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )


def _init_repo(tmp_path: Path) -> Path:
    """Initialise a git repo with a deterministic author/committer env."""
    _run(["git", "init", "-b", "main"], tmp_path)
    _run(["git", "config", "user.email", "t@t.t"], tmp_path)
    _run(["git", "config", "user.name", "t"], tmp_path)
    (tmp_path / "paper" / "claims").mkdir(parents=True)
    return tmp_path


def _commit_all(repo: Path, message: str, commit_unix: int | None = None) -> None:
    _run(["git", "add", "-A"], repo)
    env = os.environ.copy()
    if commit_unix is not None:
        iso = datetime.fromtimestamp(commit_unix, tz=timezone.utc).isoformat()
        env["GIT_AUTHOR_DATE"] = iso
        env["GIT_COMMITTER_DATE"] = iso
    _run(["git", "commit", "-m", message], repo, env=env)


def _write_producer(repo: Path, rel: str, body: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _write_sidecar(repo: Path, name: str, claim: dict, source: str) -> None:
    path = repo / "paper" / "claims" / name
    path.write_text(json.dumps({"source": source, "claims": [claim]}, indent=2))


def _claim_dict(name, value, source, computed_at, data_paths=(), statement="s.", derivation=""):
    return {
        "name": name,
        "value": value,
        "statement": statement,
        "source": source,
        "used_in": [],
        "computed_at": computed_at,
        "data_paths": list(data_paths),
        "derivation": derivation,
    }


def test_orphan_when_source_file_missing(tmp_path):
    repo = _init_repo(tmp_path)
    _write_sidecar(
        repo, "sc.json",
        _claim_dict("X", 1, "scripts/gone.py", "2020-01-01T00:00:00+00:00"),
        "scripts/gone.py",
    )
    _commit_all(repo, "init")
    report = audit(repo / "paper" / "claims", repo)
    assert len(report.orphan) == 1
    assert report.orphan[0][0].name == "X"
    assert "scripts/gone.py" in report.orphan[0][1]


def test_name_orphan_when_producer_missing_registration(tmp_path):
    repo = _init_repo(tmp_path)
    _write_producer(repo, "scripts/p.py", "# producer that does not register anything")
    _write_sidecar(
        repo, "sc.json",
        _claim_dict("Target name", 1, "scripts/p.py", "2099-01-01T00:00:00+00:00"),
        "scripts/p.py",
    )
    _commit_all(repo, "init")
    report = audit(repo / "paper" / "claims", repo)
    assert len(report.name_orphan) == 1
    assert report.name_orphan[0][0].name == "Target name"


def test_healthy_when_name_appears_in_producer(tmp_path):
    repo = _init_repo(tmp_path)
    _write_producer(repo, "scripts/p.py", 'claims.register("X", 1, "s.")')
    _write_sidecar(
        repo, "sc.json",
        _claim_dict("X", 1, "scripts/p.py", "2099-01-01T00:00:00+00:00"),
        "scripts/p.py",
    )
    _commit_all(repo, "init")
    report = audit(repo / "paper" / "claims", repo)
    assert not report.orphan
    assert not report.name_orphan
    assert not report.logic_stale


def test_logic_stale_when_producer_modified_after_claim(tmp_path):
    repo = _init_repo(tmp_path)
    producer = _write_producer(repo, "scripts/p.py", 'claims.register("X", 1, "s.")')

    # Claim computed 1h ago; producer mtime = now (freshly edited).
    old_iso = datetime.fromtimestamp(time.time() - 3600, tz=timezone.utc).isoformat()
    _write_sidecar(
        repo, "sc.json",
        _claim_dict("X", 1, "scripts/p.py", old_iso),
        "scripts/p.py",
    )
    _commit_all(repo, "init")
    os.utime(producer, None)  # bump mtime to now

    report = audit(repo / "paper" / "claims", repo)
    stale_names = [c.name for c, _ in report.logic_stale]
    assert "X" in stale_names


def test_data_stale_when_input_mtime_newer(tmp_path):
    repo = _init_repo(tmp_path)
    _write_producer(repo, "scripts/p.py", 'claims.register("X", 1, "s.")')
    (repo / "data").mkdir()
    data = repo / "data" / "input.json"
    data.write_text("{}")
    _commit_all(repo, "init")

    # Claim computed in the past; then touch data to bump its mtime.
    old_iso = datetime.fromtimestamp(time.time() - 3600, tz=timezone.utc).isoformat()
    _write_sidecar(
        repo, "sc.json",
        _claim_dict("X", 1, "scripts/p.py", old_iso, data_paths=["data/input.json"]),
        "scripts/p.py",
    )
    os.utime(data, None)  # mtime = now

    report = audit(repo / "paper" / "claims", repo)
    stale_pairs = [(c.name, r) for c, r in report.data_stale]
    assert any(name == "X" for name, _ in stale_pairs)


def test_frozen_classification(tmp_path):
    repo = _init_repo(tmp_path)
    _write_sidecar(
        repo, "sc.json",
        _claim_dict("X", 0.751,
                    source="frozen: hoo_summary.json lacks mean_uniform_hoo_acc field",
                    computed_at="2020-01-01T00:00:00+00:00"),
        "scripts/some_producer.py",
    )
    _commit_all(repo, "init")
    report = audit(repo / "paper" / "claims", repo)
    names = [c.name for c in report.frozen]
    assert "X" in names
    # Frozen source must not trigger ORPHAN even if path-check would fail.
    assert not report.orphan
    assert not report.name_orphan
    assert not report.logic_stale


def test_manual_and_superseded_still_work(tmp_path):
    repo = _init_repo(tmp_path)
    _write_sidecar(
        repo, "a.json",
        _claim_dict("M", 1, "manual: constant", "2020-01-01T00:00:00+00:00"),
        "manual: constant",
    )
    _write_sidecar(
        repo, "b.json",
        _claim_dict("S", 2, "superseded: replaced on 2025-01-01", "2020-01-01T00:00:00+00:00"),
        "superseded: replaced on 2025-01-01",
    )
    _commit_all(repo, "init")
    report = audit(repo / "paper" / "claims", repo)
    assert [c.name for c in report.manual] == ["M"]
    assert [c.name for c in report.superseded] == ["S"]
    assert not report.orphan and not report.name_orphan
