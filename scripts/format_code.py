#!/usr/bin/env python3
"""Code formatting and quality checking script for the Memory project.

This script runs various code quality tools including black, isort, pylint,
and mypy to ensure the codebase follows code style guidelines.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


def run_command(command: List[str], description: str) -> bool:
    """Runs a command and returns True if successful.

    Args:
        command: List of command parts to execute.
        description: Human-readable description of what the command does.

    Returns:
        True if the command succeeded, False otherwise.
    """
    print(f"\n🔧 {description}")
    print(f"Running: {' '.join(command)}")

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def format_code(src_dir: Path, check_only: bool = False) -> bool:
    """Formats code using black and isort.

    Args:
        src_dir: Path to the source directory.
        check_only: If True, only check formatting without making changes.

    Returns:
        True if formatting is correct or was successful, False otherwise.
    """
    success = True

    # Black formatting
    black_cmd = ["black"]
    if check_only:
        black_cmd.append("--check")
    black_cmd.append(str(src_dir))

    success &= run_command(
        black_cmd, f"{'Checking' if check_only else 'Applying'} black formatting"
    )

    # isort import sorting
    isort_cmd = ["isort"]
    if check_only:
        isort_cmd.append("--check-only")
    isort_cmd.append(str(src_dir))

    success &= run_command(
        isort_cmd, f"{'Checking' if check_only else 'Applying'} import sorting"
    )

    return success


def lint_code(src_dir: Path) -> bool:
    """Runs pylint on the source code.

    Args:
        src_dir: Path to the source directory.

    Returns:
        True if linting passed, False otherwise.
    """
    return run_command(["pylint", str(src_dir)], "Running pylint code analysis")


def type_check(src_dir: Path) -> bool:
    """Runs mypy type checking.

    Args:
        src_dir: Path to the source directory.

    Returns:
        True if type checking passed, False otherwise.
    """
    return run_command(["mypy", str(src_dir)], "Running mypy type checking")


def main() -> int:
    """Main function to orchestrate code quality checks.

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    parser = argparse.ArgumentParser(
        description="Format and check code quality for the Memory project"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check formatting without making changes",
    )
    parser.add_argument("--skip-lint", action="store_true", help="Skip pylint analysis")
    parser.add_argument(
        "--skip-mypy", action="store_true", help="Skip mypy type checking"
    )

    args = parser.parse_args()

    # Get the project root directory
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        print(f"❌ Source directory not found: {src_dir}")
        return 1

    print("🚀 Starting code quality checks for Memory project")
    print(f"📁 Source directory: {src_dir}")

    success = True

    # Format code
    success &= format_code(src_dir, check_only=args.check_only)

    # Run pylint if not skipped
    if not args.skip_lint:
        success &= lint_code(src_dir)
    else:
        print("\n⏭️  Skipping pylint analysis")

    # Run mypy if not skipped
    if not args.skip_mypy:
        success &= type_check(src_dir)
    else:
        print("\n⏭️  Skipping mypy type checking")

    # Summary
    print("\n" + "=" * 50)
    if success:
        print("🎉 All code quality checks passed!")
        return 0
    else:
        print("❌ Some code quality checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
