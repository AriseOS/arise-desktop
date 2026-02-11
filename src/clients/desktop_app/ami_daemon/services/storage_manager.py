"""Local file system storage management

File format: YAML for recordings and snapshots (human-readable)
"""

import json
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
import datetime as _dt
from datetime import datetime

from src.common.timestamp_utils import get_current_timestamp


def _yaml_datetime_to_str(obj):
    """Recursively convert datetime/date objects from yaml.safe_load back to ISO strings.

    yaml.safe_load auto-converts ISO timestamps to datetime objects and bare dates
    (e.g. 2026-01-28) to date objects. Both cause json.dumps() failures.
    Convert them all back to strings.
    """
    # Check datetime BEFORE date because datetime is a subclass of date
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, _dt.date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _yaml_datetime_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_yaml_datetime_to_str(item) for item in obj]
    return obj


class StorageManager:
    """Manage local file storage for recordings

    Recording format (recording.yaml):
        session_id: session_xxx
        created_at: 2026-01-28T13:51:25
        ended_at: 2026-01-28T13:52:03
        task_metadata:
          name: Recording Name
          description: What this recording does
        operations:
          - type: click
            ref: e42
            text: Submit
            role: button
            timestamp: 2026-01-28T13:51:32
            url: https://example.com
          - type: type
            ref: e15
            text: search query
            value: hello world
            role: textbox

    Snapshot format (snapshots/*.yaml):
        url: https://example.com
        captured_at: 2026-01-28T13:51:35
        snapshot_text: |
          - button "Submit" [ref=e42]
          - textbox "Search" [ref=e15]
        elements:
          e42:
            role: button
            name: Submit
            tagName: button
          e15:
            role: textbox
            name: Search
            tagName: input
    """

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize storage manager

        Args:
            base_path: Base storage path (e.g., ~/.ami)
        """
        self.base_path = Path(base_path) if base_path else Path.home() / ".ami"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _user_path(self, user_id: str) -> Path:
        """Get user directory path"""
        path = self.base_path / "users" / user_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    # === Recording Management ===

    def save_recording(
        self,
        user_id: str,
        session_id: str,
        recording_data: dict,
        update_timestamp: bool = True,
    ):
        """Save recording data to YAML file

        Args:
            recording_data: Recording data dict with operations
            update_timestamp: Whether to update the updated_at timestamp (default True)
        """
        recording_path = self._user_path(user_id) / "recordings" / session_id
        recording_path.mkdir(parents=True, exist_ok=True)

        # Update timestamp on save
        if update_timestamp:
            recording_data["updated_at"] = get_current_timestamp()

        # Save as YAML
        file_path = recording_path / "recording.yaml"
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(
                recording_data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    def save_snapshot(
        self,
        user_id: str,
        session_id: str,
        url_hash: str,
        snapshot_data: dict,
    ):
        """Save page snapshot to YAML file

        The snapshot_text is saved as a literal block scalar (|) to preserve
        its multi-line format without escaping.

        Args:
            user_id: User ID
            session_id: Recording session ID
            url_hash: URL hash (12 char md5)
            snapshot_data: Snapshot data with url, snapshot_text
        """
        snapshot_path = (
            self._user_path(user_id) / "recordings" / session_id / "snapshots"
        )
        snapshot_path.mkdir(parents=True, exist_ok=True)

        file_path = snapshot_path / f"{url_hash}.yaml"

        url = snapshot_data.get("url", "")
        captured_at = snapshot_data.get("captured_at", "")
        snapshot_text = snapshot_data.get("snapshot_text", "")

        # Write YAML manually with literal block scalar (|)
        # In YAML literal block, the first content line sets the base indentation.
        # All subsequent lines must have >= that indentation. Since snapshot_text
        # lines have varying indentation (tree structure), we must ensure the
        # first line has the LEAST indentation. We achieve this by writing all
        # lines with a uniform prefix so the minimum indent is always the prefix.
        # Using 2-space prefix: even lines with 0 original indent get 2 spaces,
        # so the base indent is 2 and no line can violate it.
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"url: {url}\n")
            f.write(f"captured_at: {captured_at}\n")
            f.write("snapshot: |2\n")
            # Indent each line with 2 spaces for literal block.
            # The |2 indicator tells YAML the content indent is exactly 2,
            # so lines with deeper original indent are preserved correctly.
            for line in snapshot_text.split("\n"):
                f.write(f"  {line}\n")

    def get_recording(self, user_id: str, session_id: str) -> dict:
        """Read recording data from file

        Supports both new YAML format and legacy JSON format.
        Also loads snapshots if available.

        Returns:
            Recording dict with optional 'snapshots' field
        """
        recording_path = self._user_path(user_id) / "recordings" / session_id

        # Try new YAML format first
        yaml_path = recording_path / "recording.yaml"
        json_path = recording_path / "operations.json"

        if yaml_path.exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            # yaml.safe_load auto-converts +00:00 timestamps to datetime objects;
            # convert them all back to ISO strings for downstream JSON serialization
            data = _yaml_datetime_to_str(data)
        elif json_path.exists():
            # Legacy JSON format
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            raise FileNotFoundError(f"Recording not found: {session_id}")

        # Load snapshots (new YAML format)
        snapshot_dir = recording_path / "snapshots"
        if snapshot_dir.exists():
            snapshots = {}
            for snapshot_file in snapshot_dir.glob("*.yaml"):
                try:
                    with open(snapshot_file, "r", encoding="utf-8") as f:
                        snapshot_data = _yaml_datetime_to_str(yaml.safe_load(f))
                        url = snapshot_data.get("url")
                        if url:
                            snapshots[url] = snapshot_data
                except Exception:
                    continue

            if snapshots:
                data["snapshots"] = snapshots

        # Legacy: Load DOM snapshots (old JSON format)
        dom_dir = recording_path / "dom_snapshots"
        if dom_dir.exists() and "snapshots" not in data:
            dom_snapshots = {}
            for dom_file in dom_dir.glob("*.json"):
                try:
                    with open(dom_file, "r", encoding="utf-8") as f:
                        dom_data = json.load(f)
                        url = dom_data.get("url")
                        dom_dict = dom_data.get("dom")
                        if url and dom_dict:
                            dom_snapshots[url] = dom_dict
                except Exception:
                    continue

            if dom_snapshots:
                data["dom_snapshots"] = dom_snapshots

        return data

    def update_recording_metadata(
        self,
        user_id: str,
        session_id: str,
        task_description: str = None,
        user_query: str = None,
        name: str = None,
    ):
        """Update recording metadata

        Args:
            user_id: User ID
            session_id: Session ID
            task_description: Task description (what user did)
            user_query: User query (what user wants to achieve)
            name: Short name/title (optional)
        """
        recording_data = self.get_recording(user_id, session_id)

        # Update task_metadata
        if "task_metadata" not in recording_data:
            recording_data["task_metadata"] = {}

        if task_description is not None:
            recording_data["task_metadata"]["task_description"] = task_description
        if user_query is not None:
            recording_data["task_metadata"]["user_query"] = user_query
        if name is not None:
            recording_data["task_metadata"]["name"] = name

        # Save back (exclude snapshots - stored separately)
        save_data = {
            k: v for k, v in recording_data.items() if k not in ("snapshots", "dom_snapshots")
        }
        self.save_recording(user_id, session_id, save_data)

    def update_recording_from_cloud(
        self, user_id: str, session_id: str, cloud_data: dict
    ):
        """Update local recording with cloud data (for sync)

        Only updates metadata fields, not operations.
        """
        recording_data = self.get_recording(user_id, session_id)

        if cloud_data.get("task_description"):
            if "task_metadata" not in recording_data:
                recording_data["task_metadata"] = {}
            recording_data["task_metadata"]["task_description"] = cloud_data[
                "task_description"
            ]

        if cloud_data.get("user_query"):
            if "task_metadata" not in recording_data:
                recording_data["task_metadata"] = {}
            recording_data["task_metadata"]["user_query"] = cloud_data["user_query"]

        if cloud_data.get("updated_at"):
            recording_data["updated_at"] = cloud_data["updated_at"]

        save_data = {
            k: v for k, v in recording_data.items() if k not in ("snapshots", "dom_snapshots")
        }
        self.save_recording(user_id, session_id, save_data, update_timestamp=False)

    def list_recordings(self, user_id: str) -> List[Dict[str, Any]]:
        """List all recordings for user with metadata

        Returns:
            List of recording info dicts with session_id, task_metadata, etc.
        """
        recordings_path = self._user_path(user_id) / "recordings"
        if not recordings_path.exists():
            return []

        recordings = []
        for session_dir in recordings_path.iterdir():
            if not session_dir.is_dir():
                continue

            # Try YAML first, then JSON
            yaml_file = session_dir / "recording.yaml"
            json_file = session_dir / "operations.json"

            recording_file = None
            if yaml_file.exists():
                recording_file = yaml_file
            elif json_file.exists():
                recording_file = json_file
            else:
                continue

            try:
                with open(recording_file, "r", encoding="utf-8") as f:
                    if recording_file.suffix == ".yaml":
                        recording_data = _yaml_datetime_to_str(yaml.safe_load(f))
                    else:
                        recording_data = json.load(f)

                task_metadata = recording_data.get("task_metadata", {})
                operations = recording_data.get("operations", [])

                # Get file creation time
                created_at = datetime.fromtimestamp(
                    recording_file.stat().st_ctime
                ).isoformat()

                # Count actions
                action_count = sum(
                    1
                    for op in operations
                    if op.get("type") in ["click", "input", "type", "navigate"]
                )

                # Count snapshots (new format)
                snapshot_count = 0
                snapshot_dir = session_dir / "snapshots"
                if snapshot_dir.exists():
                    snapshot_count = sum(1 for f in snapshot_dir.glob("*.yaml"))

                # Legacy: count DOM snapshots
                if snapshot_count == 0:
                    dom_dir = session_dir / "dom_snapshots"
                    if dom_dir.exists():
                        snapshot_count = sum(
                            1
                            for f in dom_dir.glob("*.json")
                            if f.name != "url_index.json"
                        )

                recordings.append(
                    {
                        "session_id": session_dir.name,
                        "task_metadata": task_metadata,
                        "created_at": created_at,
                        "action_count": action_count,
                        "snapshot_count": snapshot_count,
                        # Legacy field name for backward compatibility
                        "dom_count": snapshot_count,
                    }
                )
            except Exception:
                continue

        # Sort by created_at descending (newest first)
        recordings.sort(key=lambda x: x["created_at"], reverse=True)
        return recordings

    def delete_recording(self, user_id: str, session_id: str) -> bool:
        """Delete a recording

        Returns:
            True if deleted successfully, False if not found
        """
        import shutil

        recording_path = self._user_path(user_id) / "recordings" / session_id
        if not recording_path.exists():
            return False

        shutil.rmtree(recording_path)
        return True

    def get_recording_detail(
        self, user_id: str, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed recording information including parsed operations

        Returns:
            Recording detail dict with operations timeline and task_metadata
        """
        try:
            recording_data = self.get_recording(user_id, session_id)
            operations = recording_data.get("operations", [])

            # Count actions
            action_count = sum(
                1
                for op in operations
                if op.get("type") in ["navigate", "click", "input", "type"]
            )

            # Get file creation time
            recording_path = self._user_path(user_id) / "recordings" / session_id
            yaml_file = recording_path / "recording.yaml"
            json_file = recording_path / "operations.json"

            if yaml_file.exists():
                created_at = datetime.fromtimestamp(
                    yaml_file.stat().st_ctime
                ).isoformat()
            elif json_file.exists():
                created_at = datetime.fromtimestamp(
                    json_file.stat().st_ctime
                ).isoformat()
            else:
                created_at = None

            task_metadata = recording_data.get("task_metadata", {})

            return {
                "session_id": session_id,
                "created_at": created_at,
                "updated_at": recording_data.get("updated_at"),
                "action_count": action_count,
                "task_metadata": task_metadata,
                "operations": operations,
                "snapshots": recording_data.get("snapshots", {}),
                # Legacy field
                "dom_snapshots": recording_data.get("dom_snapshots", {}),
            }
        except Exception:
            return None
