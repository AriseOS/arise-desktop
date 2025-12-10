"""
Simple File Synchronization with Ignore Patterns

Uses pathspec library for .gitignore-style pattern matching.
Install: pip install pathspec
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional, Dict
import pathspec

logger = logging.getLogger(__name__)


class SimpleSync:
    """
    Simple bidirectional file sync with ignore patterns

    Features:
    - Gitignore-style pattern matching
    - Preserves file timestamps
    - Simple and reliable
    """

    # Default ignore patterns for workflow sync
    DEFAULT_IGNORE_PATTERNS = [
        # Debug artifacts
        "dom_data.json",
        "dom_snapshots/",

        # Python cache
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*.pyd",

        # Execution results
        "executions/",

        # OS files
        ".DS_Store",
        "Thumbs.db",

        # Temporary files
        "*.tmp",
        "*.temp",
        "*~",
    ]

    def __init__(self, ignore_patterns: Optional[List[str]] = None):
        """
        Args:
            ignore_patterns: List of gitignore-style patterns to ignore
        """
        if ignore_patterns is None:
            ignore_patterns = self.DEFAULT_IGNORE_PATTERNS

        self.spec = pathspec.PathSpec.from_lines('gitwildmatch', ignore_patterns)
        logger.info(f"Initialized SimpleSync with {len(ignore_patterns)} ignore patterns")

    def should_ignore(self, path: Path, base_path: Path) -> bool:
        """
        Check if a path should be ignored

        Args:
            path: Absolute path to check
            base_path: Base directory for relative path calculation

        Returns:
            True if should ignore, False otherwise
        """
        try:
            rel_path = path.relative_to(base_path)
            # pathspec needs posix-style paths with / separator
            posix_path = rel_path.as_posix()

            # Check if directory
            if path.is_dir():
                posix_path = posix_path + "/"

            return self.spec.match_file(posix_path)
        except ValueError:
            # path is not relative to base_path
            return False

    def collect_files(self, source_dir: Path) -> Dict[str, Path]:
        """
        Collect all files that should be synced

        Args:
            source_dir: Source directory to scan

        Returns:
            Dict mapping relative path (str) to absolute path (Path)
        """
        files = {}

        if not source_dir.exists():
            logger.warning(f"Source directory does not exist: {source_dir}")
            return files

        for path in source_dir.rglob("*"):
            if not path.is_file():
                continue

            if self.should_ignore(path, source_dir):
                logger.debug(f"Ignoring: {path.relative_to(source_dir)}")
                continue

            rel_path = path.relative_to(source_dir).as_posix()
            files[rel_path] = path

        logger.info(f"Collected {len(files)} files from {source_dir}")
        return files

    def sync_directory(
        self,
        source_dir: Path,
        target_dir: Path,
        preserve_timestamp: bool = True
    ) -> Dict[str, any]:
        """
        Sync files from source to target directory

        Args:
            source_dir: Source directory
            target_dir: Target directory
            preserve_timestamp: If True, preserve file modification times

        Returns:
            Dict with sync statistics:
            {
                "copied": 5,
                "updated": 3,
                "skipped": 2,
                "errors": 0,
                "copied_files": [...],
                "error_files": [...]
            }
        """
        stats = {
            "copied": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "copied_files": [],
            "error_files": []
        }

        source_files = self.collect_files(source_dir)

        for rel_path, source_path in source_files.items():
            target_path = target_dir / rel_path

            try:
                # Create parent directory
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Check if file needs update
                if target_path.exists():
                    source_mtime = source_path.stat().st_mtime
                    target_mtime = target_path.stat().st_mtime

                    if source_mtime <= target_mtime:
                        stats["skipped"] += 1
                        logger.debug(f"Skipped (up-to-date): {rel_path}")
                        continue

                    action = "updated"
                    stats["updated"] += 1
                else:
                    action = "copied"
                    stats["copied"] += 1

                # Copy file
                shutil.copy2(source_path, target_path)
                stats["copied_files"].append(rel_path)
                logger.info(f"{action.capitalize()}: {rel_path}")

                # Preserve timestamp if requested
                if preserve_timestamp:
                    shutil.copystat(source_path, target_path)

            except Exception as e:
                stats["errors"] += 1
                stats["error_files"].append({"file": rel_path, "error": str(e)})
                logger.error(f"Failed to sync {rel_path}: {e}")

        logger.info(
            f"Sync complete: {stats['copied']} copied, {stats['updated']} updated, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )

        return stats

    def bidirectional_sync(
        self,
        dir_a: Path,
        dir_b: Path,
        direction: str = "auto"
    ) -> Dict[str, any]:
        """
        Bidirectional sync based on file timestamps

        Args:
            dir_a: First directory (typically local)
            dir_b: Second directory (typically cloud)
            direction: "auto", "a_to_b", or "b_to_a"
                - "auto": sync newer files in both directions
                - "a_to_b": only sync from A to B
                - "b_to_a": only sync from B to A

        Returns:
            Dict with sync statistics for both directions
        """
        result = {
            "a_to_b": None,
            "b_to_a": None,
            "direction": direction
        }

        if direction in ["auto", "a_to_b"]:
            logger.info(f"Syncing {dir_a} → {dir_b}")
            result["a_to_b"] = self.sync_directory(dir_a, dir_b)

        if direction in ["auto", "b_to_a"]:
            logger.info(f"Syncing {dir_b} → {dir_a}")
            result["b_to_a"] = self.sync_directory(dir_b, dir_a)

        return result


def sync_workflow_directory(
    local_path: Path,
    cloud_path: Path,
    direction: str = "auto"
) -> Dict[str, any]:
    """
    Convenience function to sync workflow directories

    Args:
        local_path: Local workflow directory (~/.ami/users/{user_id}/workflows/{workflow_id})
        cloud_path: Cloud workflow directory (~/ami-server/users/{user_id}/workflows/{workflow_id})
        direction: "upload" (local→cloud), "download" (cloud→local), or "auto" (bidirectional)

    Returns:
        Sync statistics
    """
    sync = SimpleSync()

    # Map direction names
    direction_map = {
        "upload": "a_to_b",
        "download": "b_to_a",
        "auto": "auto"
    }

    sync_direction = direction_map.get(direction, "auto")

    return sync.bidirectional_sync(local_path, cloud_path, sync_direction)


if __name__ == "__main__":
    # Example usage
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)8s] %(message)s"
    )

    if len(sys.argv) < 3:
        print("Usage: python simple_sync.py <source_dir> <target_dir> [direction]")
        print("  direction: upload, download, or auto (default)")
        sys.exit(1)

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    direction = sys.argv[3] if len(sys.argv) > 3 else "auto"

    result = sync_workflow_directory(source, target, direction)
    print("\nSync Result:")
    print(f"Direction: {result['direction']}")
    if result['a_to_b']:
        print(f"  {source} → {target}: {result['a_to_b']['copied']} files")
    if result['b_to_a']:
        print(f"  {target} → {source}: {result['b_to_a']['copied']} files")
