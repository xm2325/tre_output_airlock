from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        value = tomllib.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a TOML table")
    return value


def _runtime_version(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != "__version__":
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise ValueError(f"{path} must define a literal __version__ string")


def _uv_project_version(path: Path) -> str:
    lock = _read_toml(path)
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise ValueError(f"{path} does not contain a package list")
    matches = [
        package.get("version")
        for package in packages
        if isinstance(package, dict) and package.get("name") == "tre-output-airlock-api"
    ]
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise ValueError(f"{path} must contain exactly one tre-output-airlock-api version")
    return matches[0]


def collect_versions(root: Path) -> dict[str, str]:
    expected = (root / "VERSION").read_text(encoding="utf-8").strip()
    backend_project = _read_toml(root / "backend" / "pyproject.toml")
    frontend_package = _read_json(root / "frontend" / "package.json")
    frontend_lock = _read_json(root / "frontend" / "package-lock.json")

    project_table = backend_project.get("project")
    if not isinstance(project_table, dict) or not isinstance(project_table.get("version"), str):
        raise ValueError("backend/pyproject.toml must define project.version")

    lock_packages = frontend_lock.get("packages")
    if not isinstance(lock_packages, dict):
        raise ValueError("frontend/package-lock.json must define packages")
    root_lock_package = lock_packages.get("")
    if not isinstance(root_lock_package, dict):
        raise ValueError("frontend/package-lock.json must define the root package")

    values = {
        "VERSION": expected,
        "backend runtime": _runtime_version(root / "backend" / "app" / "version.py"),
        "backend pyproject": str(project_table["version"]),
        "backend uv.lock": _uv_project_version(root / "backend" / "uv.lock"),
        "frontend package.json": str(frontend_package.get("version", "")),
        "frontend package-lock.json": str(frontend_lock.get("version", "")),
        "frontend package-lock root": str(root_lock_package.get("version", "")),
    }
    return values


def check_versions(root: Path) -> dict[str, str]:
    versions = collect_versions(root)
    expected = versions["VERSION"]
    if SEMVER_PATTERN.fullmatch(expected) is None:
        raise ValueError(f"VERSION must be a stable MAJOR.MINOR.PATCH value, got {expected!r}")

    mismatches = {name: value for name, value in versions.items() if value != expected}
    if mismatches:
        details = ", ".join(f"{name}={value!r}" for name, value in mismatches.items())
        raise ValueError(f"release version mismatch; expected {expected!r}: {details}")
    return versions


def main() -> int:
    parser = argparse.ArgumentParser(description="Check cross-stack Airlock release version metadata.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    args = parser.parse_args()

    try:
        versions = check_versions(args.root.resolve())
    except (OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError, SyntaxError) as exc:
        print(f"release-version check failed: {exc}", file=sys.stderr)
        return 1

    version = versions["VERSION"]
    print(f"release-version check passed: {version}")
    for name in sorted(versions):
        print(f"  {name}: {versions[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
