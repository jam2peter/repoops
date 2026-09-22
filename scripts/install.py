#!/usr/bin/env python3
"""Install RepoOps templates into a control repository without overwriting by default."""

from __future__ import annotations

import argparse
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]


def copy_file(source: pathlib.Path, target: pathlib.Path, force: bool) -> None:
    if target.exists() and not force:
        raise SystemExit(f"ERROR: refusing to overwrite {target}; use --force explicitly")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"INSTALLED={target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default=".")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target = pathlib.Path(args.target).resolve()
    if not target.is_dir():
        raise SystemExit(f"ERROR: target directory not found: {target}")

    copy_file(
        ROOT / "templates/workflows/repository-admin.yml",
        target / ".github/workflows/repoops-repository-admin.yml",
        args.force,
    )
    copy_file(
        ROOT / "templates/workflows/project-sync.yml",
        target / ".github/workflows/repoops-project-sync.yml",
        args.force,
    )

    config_target = target / "repoops.json"
    if not config_target.exists():
        copy_file(ROOT / "repoops.example.json", config_target, False)
    else:
        print(f"PRESERVED={config_target}")

    scripts_target = target / "scripts"
    for name in ("repo_admin.py", "project_sync.py"):
        copy_file(ROOT / "scripts" / name, scripts_target / name, args.force)

    print("REPOOPS_INSTALL=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
