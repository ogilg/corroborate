"""Command-line entry point: `vernier build` and `vernier audit`.

Intended to be called from project-local scripts that know the project's
paths; this CLI supplies generic defaults but configurable via flags.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from vernier.audit import audit, print_report
from vernier.build import BuildPaths, build


def main() -> int:
    parser = argparse.ArgumentParser(prog="vernier", description="Claims registry tooling.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build claims.md + numbers.tex from sidecars.")
    b.add_argument("--claims-dir", type=Path, default=Path("paper/claims"))
    b.add_argument("--claims-md", type=Path, default=Path("paper/claims.md"))
    b.add_argument("--numbers-tex", type=Path, default=Path("paper/numbers.tex"),
                   help="Set to '' to skip LaTeX macro generation.")
    b.add_argument("--title", default="Claims registry")

    a = sub.add_parser("audit", help="Diff live sidecars against git HEAD.")
    a.add_argument("--claims-dir", type=Path, default=Path("paper/claims"))
    a.add_argument("--repo-root", type=Path, default=Path("."))

    args = parser.parse_args()
    if args.cmd == "build":
        numbers_tex = args.numbers_tex if str(args.numbers_tex) else None
        paths = BuildPaths(
            claims_dir=args.claims_dir,
            claims_md=args.claims_md,
            numbers_tex=numbers_tex,
            title=args.title,
        )
        n = build(paths)
        outputs = []
        if paths.numbers_tex is not None:
            outputs.append(str(paths.numbers_tex))
        if paths.claims_md is not None:
            outputs.append(str(paths.claims_md))
        print(f"Wrote {' and '.join(outputs)} ({n} claims).")
        return 0
    if args.cmd == "audit":
        report = audit(args.claims_dir, args.repo_root)
        print_report(report)
        return 0 if report.clean else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
