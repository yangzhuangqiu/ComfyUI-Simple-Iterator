import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def _run_step(
    title: str,
    command: list[str],
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> None:
    print(f"[release-gate] {title}: {' '.join(command)}")
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    subprocess.run(command, cwd=str(cwd), check=True, env=env)


def _read_project_version(pyproject_path: Path) -> str:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    version = str(project.get("version", "")).strip()
    if not version:
        raise RuntimeError("project.version is missing in pyproject.toml")
    return version


def _ensure_changelog_contains_version(changelog_path: Path, version: str) -> None:
    content = changelog_path.read_text(encoding="utf-8")
    pattern = rf"^## \[{re.escape(version)}\] - "
    if not re.search(pattern, content, flags=re.MULTILINE):
        raise RuntimeError(
            f"CHANGELOG.md missing release heading for version {version}. "
            f"Expected: '## [{version}] - YYYY-MM-DD'"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Release quality gate: lint/test/version check")
    parser.add_argument("--skip-lint", action="store_true", help="Skip lint check")
    parser.add_argument("--skip-tests", action="store_true", help="Skip tests")
    parser.add_argument(
        "--skip-version-check", action="store_true", help="Skip pyproject/changelog version check"
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    pyproject_path = root / "pyproject.toml"
    changelog_path = root / "CHANGELOG.md"

    if not args.skip_version_check:
        version = _read_project_version(pyproject_path)
        _ensure_changelog_contains_version(changelog_path, version)
        print(f"[release-gate] version-check: OK ({version})")

    if not args.skip_lint:
        _run_step("lint", [sys.executable, "-m", "ruff", "check", "."], cwd=root)

    if not args.skip_tests:
        _run_step(
            "tests-core",
            [sys.executable, "-m", "pytest", "tests/core", "-q", "-m", "core"],
            cwd=root,
            env_overrides={"SIMPLE_ITERATOR_SKIP_NODE_IMPORT": "1"},
        )

    print("[release-gate] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
