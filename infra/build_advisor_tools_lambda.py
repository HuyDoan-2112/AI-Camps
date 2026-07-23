"""Build the Python 3.12 ZIP for the AgentCore Gateway Lambda tools."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "agentcore" / "lambda_tools"
DEFAULT_OUTPUT = ROOT / "dist" / "agentcore-advisor-tools-lambda.zip"

_RUNTIME_DATA = (
    ROOT / "config" / "majors.csv",
    ROOT / "config" / "transfer_ge_policies.csv",
    ROOT / "data" / "processed" / "structured_store" / "articulation.json",
    ROOT / "data" / "processed" / "structured_store" / "courses.json",
    ROOT / "data" / "processed" / "structured_store" / "ge_certification.json",
    ROOT / "data" / "processed" / "structured_store" / "offering_pattern.json",
    ROOT / "data" / "processed" / "structured_store" / "prereq_graph.json",
)


def _install_dependencies(package_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "312",
            "--only-binary=:all:",
            "--no-compile",
            "--target",
            str(package_dir),
            "--requirement",
            str(TOOLS_DIR / "requirements.txt"),
        ],
        check=True,
    )


def _copy_project_files(package_dir: Path) -> None:
    shutil.copy2(TOOLS_DIR / "lambda_handler.py", package_dir / "lambda_handler.py")
    for source in sorted((ROOT / "src" / "transfer_advisor").rglob("*.py")):
        destination = package_dir / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for source in _RUNTIME_DATA:
        if not source.is_file():
            raise FileNotFoundError(f"Required Lambda runtime file is missing: {source}")
        destination = package_dir / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _write_zip(package_dir: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(path for path in package_dir.rglob("*") if path.is_file()):
            relative = source.relative_to(package_dir)
            info = zipfile.ZipInfo.from_file(source, arcname=str(relative))
            info.external_attr = (0o644 & 0xFFFF) << 16
            with source.open("rb") as file:
                archive.writestr(info, file.read(), compress_type=zipfile.ZIP_DEFLATED)


def build_advisor_tools_package(
    output_path: Path = DEFAULT_OUTPUT,
    *,
    install_dependencies: bool = True,
) -> Path:
    """Package tool adapters, application code, and reviewed runtime data."""
    with tempfile.TemporaryDirectory(prefix="advisor-tools-lambda-") as temp_dir:
        package_dir = Path(temp_dir)
        if install_dependencies:
            _install_dependencies(package_dir)
        _copy_project_files(package_dir)
        _write_zip(package_dir, output_path)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build_advisor_tools_package(args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
