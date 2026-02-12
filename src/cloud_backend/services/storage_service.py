"""
Storage Service - Server local filesystem management (Cloud Backend)

Storage paths:
- Development: ~/ami-server
- Production: /var/lib/ami-server/ (or via STORAGE_PATH env var)

Directory structure:
~/ami-server/
├── users/{user_id}/
│   ├── recordings/              # Recording data
│   │   └── {recording_id}/
│   │       ├── operations.json
│   │       └── metadata.json    # Contains workflow_id association
│   ├── workflows/               # Workflows
│   │   └── {workflow_id}/
│   │       ├── workflow.yaml
│   │       └── metadata.json    # Contains association info
│   └── intent_builder/          # Agent working directory
│       └── {session_id}/
└── logs/

Association:
Recording → Workflow (direct, no intermediate MetaFlow)
"""

from pathlib import Path
import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging

from src.common.timestamp_utils import get_current_timestamp

logger = logging.getLogger(__name__)

class StorageService:
    """服务器本地文件系统管理器"""
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize Cloud Backend storage service

        Args:
            base_path: Base path (optional)
                Development: ~/ami-server (default)
                Production: /var/lib/ami-server/ (via STORAGE_PATH env var)

        Note:
            Cloud Backend uses ~/ami-server (server-side data)
            App Backend uses ~/.ami (local client data)
        """
        if base_path:
            self.base_path = Path(base_path).expanduser()
        else:
            # Default path for Cloud Backend (server-side storage)
            default_path = os.getenv("STORAGE_PATH", "~/ami-server")
            self.base_path = Path(default_path).expanduser()

        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Cloud Backend Storage initialized: {self.base_path}")
    
    def _user_path(self, user_id: str) -> Path:
        """获取用户目录"""
        path = self.base_path / "users" / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_user_intent_graph_path(self, user_id: str) -> str:
        """Get path to user's Intent Memory Graph file"""
        return str(self._user_path(user_id) / "intent_graph.json")

    def get_user_intent_builder_path(self, user_id: str, session_id: str) -> Path:
        """Get working directory for Intent Builder Agent session"""
        path = self._user_path(user_id) / "intent_builder" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_user_workflow_logs_path(self, user_id: str, workflow_id: str) -> Path:
        """Get path for storing workflow execution logs.

        Storage structure:
            {base_path}/users/{user_id}/workflow_logs/{workflow_id}/
                {task_id}.json

        Args:
            user_id: User identifier
            workflow_id: Workflow identifier

        Returns:
            Path to workflow logs directory
        """
        return self._user_path(user_id) / "workflow_logs" / workflow_id

    def get_session_info(self, user_id: str, session_id: str, timeout_minutes: int = 30) -> Optional[Dict]:
        """
        Get session information including age and expiry time

        Args:
            user_id: User ID
            session_id: Session ID
            timeout_minutes: Session timeout in minutes

        Returns:
            Dict with session info, or None if session doesn't exist
        """
        import time

        session_path = self._user_path(user_id) / "intent_builder" / session_id
        if not session_path.exists():
            return None

        try:
            last_modified = session_path.stat().st_mtime
            current_time = time.time()
            age_seconds = current_time - last_modified
            age_minutes = age_seconds / 60
            timeout_seconds = timeout_minutes * 60

            # Calculate expiry
            minutes_until_expiry = timeout_minutes - age_minutes
            is_expired = age_seconds > timeout_seconds

            return {
                "session_id": session_id,
                "user_id": user_id,
                "working_dir": str(session_path),
                "last_active_at": datetime.fromtimestamp(last_modified, timezone.utc).isoformat(),
                "age_minutes": round(age_minutes, 2),
                "minutes_until_expiry": round(max(0, minutes_until_expiry), 2),
                "status": "expired" if is_expired else "active"
            }
        except Exception as e:
            logger.error(f"Failed to get session info: {e}")
            return None

    def cleanup_expired_sessions(self, timeout_minutes: int = 30) -> int:
        """
        Clean up expired Intent Builder sessions across all users

        Args:
            timeout_minutes: Session timeout in minutes (default: 30)

        Returns:
            Number of sessions cleaned up
        """
        import shutil
        import time

        cleaned_count = 0
        current_time = time.time()
        timeout_seconds = timeout_minutes * 60

        users_dir = self.base_path / "users"
        if not users_dir.exists():
            return 0

        # Scan all users
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir():
                continue

            intent_builder_dir = user_dir / "intent_builder"
            if not intent_builder_dir.exists():
                continue

            # Scan all sessions for this user
            for session_dir in intent_builder_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                try:
                    # Check directory last modified time
                    last_modified = session_dir.stat().st_mtime
                    age_seconds = current_time - last_modified

                    if age_seconds > timeout_seconds:
                        # Session expired, delete it
                        shutil.rmtree(session_dir)
                        cleaned_count += 1
                        logger.info(f"🗑️  Cleaned expired session: {session_dir.name} (age: {age_seconds/60:.1f} min)")
                except Exception as e:
                    logger.error(f"Failed to cleanup session {session_dir}: {e}")

        if cleaned_count > 0:
            logger.info(f"✅ Session cleanup complete: {cleaned_count} sessions removed")
        else:
            logger.debug(f"✅ Session cleanup complete: no expired sessions")

        return cleaned_count

    # ===== Workflow Modification Session 管理 =====

    def get_modification_session_path(self, user_id: str, session_id: str) -> Path:
        """Get working directory for Workflow Modification Session.

        Storage structure:
            {base_path}/sessions/{user_id}/{session_id}/

        This is different from intent_builder sessions as it contains
        full workflow directory copies including step subdirectories.
        """
        path = self.base_path / "sessions" / str(user_id) / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copy_workflow_to_session(
        self,
        user_id: str,
        workflow_id: str,
        session_id: str
    ) -> Path:
        """Copy entire workflow directory to session working directory.

        Args:
            user_id: User ID
            workflow_id: Source workflow ID
            session_id: Target session ID

        Returns:
            Path to the session working directory

        Copies:
            - workflow.yaml
            - metadata.json
            - {step_id}/ directories (containing scripts directly)
            - dom_snapshots/ (if exists)

        Post-copy processing:
            - Copies latest DOM from dom_snapshots/ to each step's dom_data.json
              based on step_id mapping in url_index.json
        """
        import shutil

        source_path = self.get_workflow_path(user_id, workflow_id)
        session_path = self.get_modification_session_path(user_id, session_id)

        if not source_path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_id}")

        # Copy workflow directory contents (not the directory itself)
        for item in source_path.iterdir():
            dest = session_path / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Save session metadata for tracking
        session_meta = {
            "user_id": user_id,
            "workflow_id": workflow_id,
            "session_id": session_id,
            "source_path": str(source_path),
            "created_at": get_current_timestamp()
        }
        session_meta_file = session_path / ".session_metadata.json"
        with open(session_meta_file, 'w', encoding='utf-8') as f:
            json.dump(session_meta, f, indent=2)

        # Copy latest DOM from dom_snapshots to each step's script directory
        self._populate_dom_data_from_snapshots(session_path)

        logger.info(f"Copied workflow {workflow_id} to session {session_id}")
        return session_path

    def _populate_dom_data_from_snapshots(self, session_path: Path) -> None:
        """Copy DOM snapshots to each step directory based on step_id mapping.

        Reads dom_snapshots/url_index.json to find step_id -> DOM file mapping,
        then copies each DOM file to the corresponding step's dom_data.json.

        This ensures modification sessions have up-to-date DOM data for script testing.

        Args:
            session_path: Path to session working directory
        """
        dom_snapshots_dir = session_path / "dom_snapshots"
        url_index_file = dom_snapshots_dir / "url_index.json"

        if not url_index_file.exists():
            logger.debug(f"No url_index.json found in {dom_snapshots_dir}")
            return

        try:
            with open(url_index_file, 'r', encoding='utf-8') as f:
                url_index = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load url_index.json: {e}")
            return

        if not isinstance(url_index, list):
            logger.warning(f"url_index.json is not a list: {type(url_index)}")
            return

        # Build step_id -> DOM file mapping
        step_dom_map = {}
        for entry in url_index:
            step_id = entry.get("step_id")
            dom_file = entry.get("file")
            if step_id and dom_file:
                # Keep latest entry for each step_id (last one wins)
                step_dom_map[step_id] = dom_file

        logger.info(f"Found {len(step_dom_map)} step -> DOM mappings: {list(step_dom_map.keys())}")

        # Copy DOM to each step directory (scripts are now directly in step directory)
        for step_id, dom_filename in step_dom_map.items():
            step_dir = session_path / step_id
            if not step_dir.exists():
                logger.debug(f"Step directory not found: {step_id}")
                continue

            # Read DOM snapshot
            dom_snapshot_file = dom_snapshots_dir / dom_filename
            if not dom_snapshot_file.exists():
                logger.warning(f"DOM snapshot not found: {dom_filename}")
                continue

            try:
                with open(dom_snapshot_file, 'r', encoding='utf-8') as f:
                    dom_data = json.load(f)

                # Save directly to step directory (no hash subdirectory)
                dom_data_file = step_dir / "dom_data.json"
                with open(dom_data_file, 'w', encoding='utf-8') as f:
                    json.dump(dom_data, f, indent=2, ensure_ascii=False)

                logger.info(f"Copied DOM to {step_id}/{dom_data_file.name}")

            except Exception as e:
                logger.warning(f"Failed to copy DOM for step {step_id}: {e}")

    def sync_session_to_workflow(
        self,
        user_id: str,
        session_id: str
    ) -> List[str]:
        """Sync modified files from session back to original workflow.

        Only syncs specific file patterns:
            - workflow.yaml
            - */extraction_script.py
            - */dom_tools.py

        Updates workflow metadata.json timestamp.

        Returns:
            List of synced file paths (relative), empty list if nothing synced
        """
        import shutil

        session_path = self.get_modification_session_path(user_id, session_id)
        session_meta_file = session_path / ".session_metadata.json"

        if not session_meta_file.exists():
            logger.error(f"Session metadata not found: {session_id}")
            return []

        with open(session_meta_file, 'r') as f:
            session_meta = json.load(f)

        workflow_id = session_meta["workflow_id"]
        workflow_path = self.get_workflow_path(user_id, workflow_id)

        # Sync patterns - scripts are now directly in step directories (no hash subdirectory)
        # Include requirement.json and task.json for cache validation
        sync_patterns = [
            "workflow.yaml",
            "*/extraction_script.py",
            "*/dom_tools.py",
            "*/requirement.json",  # For scraper cache validation
            "*/task.json",         # For browser cache validation
            "*/find_element.py",   # Browser agent script
        ]

        synced_files = []
        for pattern in sync_patterns:
            for src_file in session_path.glob(pattern):
                rel_path = src_file.relative_to(session_path)
                dst_file = workflow_path / rel_path

                # Copy if modified or new
                if not dst_file.exists() or src_file.stat().st_mtime > dst_file.stat().st_mtime:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    synced_files.append(str(rel_path))

        # Update workflow metadata timestamp and resources if any files were synced
        if synced_files:
            workflow_yaml_path = workflow_path / "workflow.yaml"
            if workflow_yaml_path.exists():
                self.update_workflow_yaml(
                    user_id,
                    workflow_id,
                    workflow_yaml_path.read_text(encoding='utf-8')
                )

                # Update requirement.json for scraper_agent steps based on workflow.yaml
                # This ensures cache validation uses the latest data_requirements
                req_synced = self._sync_requirement_json_from_workflow(
                    workflow_yaml_path, workflow_path
                )
                if req_synced:
                    synced_files.extend(req_synced)

            # Update resources in metadata.json to include synced files
            self._update_workflow_resources_sync(user_id, workflow_id)
            logger.info(f"Synced {len(synced_files)} files from session {session_id}: {synced_files}")

        return synced_files

    def _sync_requirement_json_from_workflow(
        self,
        workflow_yaml_path: Path,
        workflow_path: Path
    ) -> List[str]:
        """Update requirement.json files based on workflow.yaml step definitions.

        When workflow.yaml is modified (e.g., via AI dialogue), the data_requirements
        in scraper_agent steps may change. This method ensures the corresponding
        requirement.json files are updated to match, which is critical for cache
        validation in scraper_agent.

        Args:
            workflow_yaml_path: Path to workflow.yaml
            workflow_path: Path to workflow directory

        Returns:
            List of updated requirement.json paths (relative)
        """
        import yaml

        updated_files = []

        try:
            workflow_yaml = workflow_yaml_path.read_text(encoding='utf-8')
            workflow = yaml.safe_load(workflow_yaml)
            if not workflow:
                return []

            # Extract all scraper_agent steps (including nested ones in foreach/if/while)
            scraper_steps = self._extract_scraper_steps(workflow.get("steps", []))

            for step in scraper_steps:
                step_id = step.get("id")
                if not step_id:
                    continue

                inputs = step.get("inputs", {})
                data_req = inputs.get("data_requirements", {})

                # Build requirement.json content
                requirement_data = {
                    "user_description": data_req.get("user_description", ""),
                    "output_format": data_req.get("output_format", {}),
                    "xpath_hints": data_req.get("xpath_hints"),
                    "sample_data": data_req.get("sample_data", [])
                }

                # Write to step directory
                step_dir = workflow_path / step_id
                if not step_dir.exists():
                    step_dir.mkdir(parents=True, exist_ok=True)

                requirement_file = step_dir / "requirement.json"

                # Check if content changed
                needs_update = True
                if requirement_file.exists():
                    try:
                        existing = json.loads(requirement_file.read_text(encoding='utf-8'))
                        if existing == requirement_data:
                            needs_update = False
                    except Exception:
                        pass  # File corrupted, update it

                if needs_update:
                    requirement_file.write_text(
                        json.dumps(requirement_data, indent=2, ensure_ascii=False),
                        encoding='utf-8'
                    )
                    rel_path = f"{step_id}/requirement.json"
                    updated_files.append(rel_path)
                    logger.info(f"Updated {rel_path} from workflow.yaml")

        except Exception as e:
            logger.warning(f"Failed to sync requirement.json from workflow: {e}")

        return updated_files

    def _extract_scraper_steps(self, steps: List[Dict]) -> List[Dict]:
        """Extract all scraper_agent steps from workflow steps (including nested).

        Recursively processes foreach, if, while control flow to find all
        scraper_agent steps.

        Args:
            steps: List of workflow steps

        Returns:
            List of scraper_agent step definitions
        """
        result = []

        for step in steps:
            # Check for control flow (foreach, if, while)
            if any(k in step for k in ["foreach", "if", "while"]):
                # Process nested steps
                for key in ["do", "then", "else", "steps"]:
                    if key in step:
                        nested = step[key]
                        if isinstance(nested, list):
                            result.extend(self._extract_scraper_steps(nested))
                continue

            # Check if this is a scraper_agent step
            agent = step.get("agent") or step.get("agent_type")
            if agent == "scraper_agent":
                result.append(step)

        return result

    def cleanup_modification_session(self, user_id: str, session_id: str) -> bool:
        """Clean up a workflow modification session directory.

        Returns:
            True if cleanup successful, False if not found
        """
        import shutil

        session_path = self.get_modification_session_path(user_id, session_id)
        if not session_path.exists():
            return False

        shutil.rmtree(session_path)
        logger.info(f"Cleaned up modification session: {session_id}")
        return True

    def cleanup_expired_modification_sessions(self, timeout_minutes: int = 60) -> int:
        """Clean up expired Workflow Modification sessions.

        Args:
            timeout_minutes: Session timeout in minutes (default: 60)

        Returns:
            Number of sessions cleaned up
        """
        import shutil
        import time

        cleaned_count = 0
        current_time = time.time()
        timeout_seconds = timeout_minutes * 60

        sessions_dir = self.base_path / "sessions"
        if not sessions_dir.exists():
            return 0

        # Scan all users
        for user_dir in sessions_dir.iterdir():
            if not user_dir.is_dir():
                continue

            # Scan all sessions for this user
            for session_dir in user_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                try:
                    # Check directory last modified time
                    last_modified = session_dir.stat().st_mtime
                    age_seconds = current_time - last_modified

                    if age_seconds > timeout_seconds:
                        shutil.rmtree(session_dir)
                        cleaned_count += 1
                        logger.info(f"🗑️  Cleaned expired modification session: {session_dir.name} (age: {age_seconds/60:.1f} min)")
                except Exception as e:
                    logger.error(f"Failed to cleanup modification session {session_dir}: {e}")

        return cleaned_count

    # ===== Recording 管理 =====
    
    def save_recording(
        self,
        user_id: str,
        recording_id: str,
        operations: List[Dict],
        task_description: Optional[str] = None,
        user_query: Optional[str] = None,
        dom_snapshots: Optional[Dict[str, Dict]] = None,
        graph: Optional[Dict] = None
    ) -> str:
        """Save recording data to server filesystem.

        Args:
            user_id: User ID
            recording_id: Recording ID
            operations: List of operations
            task_description: User's description of what they did
            user_query: User's description of what they want to do
            dom_snapshots: URL -> DOM dict mapping for pre-generating scripts
            graph: State/Action Graph (optional)

        Returns:
            File path to operations.json
        """
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        recording_path.mkdir(parents=True, exist_ok=True)

        file_path = recording_path / "operations.json"
        current_time = get_current_timestamp()
        data = {
            "recording_id": recording_id,
            "user_id": user_id,
            "created_at": current_time,
            "updated_at": current_time,  # Track updates for sync
            "operations_count": len(operations),
            "operations": operations
        }

        if task_description:
            data["task_description"] = task_description

        if user_query:
            data["user_query"] = user_query

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Save DOM snapshots if provided
        if dom_snapshots:
            import hashlib
            dom_snapshots_dir = recording_path / "dom_snapshots"
            dom_snapshots_dir.mkdir(parents=True, exist_ok=True)

            # Save each DOM snapshot as separate file (URL hash as filename)
            url_index = []
            captured_at = get_current_timestamp()

            for url, dom_dict in dom_snapshots.items():
                url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
                dom_filename = f"{url_hash}.json"
                dom_file = dom_snapshots_dir / dom_filename
                dom_data = {
                    "url": url,
                    "dom": dom_dict,
                    "captured_at": captured_at
                }
                with open(dom_file, 'w', encoding='utf-8') as f:
                    json.dump(dom_data, f, indent=2, ensure_ascii=False)

                url_index.append({
                    "url": url,
                    "file": dom_filename,
                    "captured_at": captured_at
                })

            # Save URL index file
            index_file = dom_snapshots_dir / "url_index.json"
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(url_index, f, indent=2, ensure_ascii=False)

            logger.info(f"  DOM snapshots saved: {len(dom_snapshots)} URLs (with url_index.json)")

        # Save graph separately if provided
        if graph:
            graph_path = recording_path / "graph.json"
            with open(graph_path, 'w', encoding='utf-8') as f:
                json.dump(graph, f, indent=2, ensure_ascii=False)
            logger.info(f"  Graph saved: {len(graph.get('states', {}))} states, "
                       f"{len(graph.get('edges', []))} edges")

        logger.info(f"Recording saved: {recording_id} ({len(operations)} ops)")
        if task_description:
            logger.info(f"  Task: {task_description}")
        if user_query:
            logger.info(f"  User query: {user_query}")
        return str(file_path)

    def update_recording(
        self,
        user_id: str,
        recording_id: str,
        task_description: Optional[str] = None,
        user_query: Optional[str] = None
    ):
        """Update recording with task_description and/or user_query

        Args:
            user_id: User ID
            recording_id: Recording ID
            task_description: Task description to update (optional)
            user_query: User query to update (optional)
        """
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        file_path = recording_path / "operations.json"

        if not file_path.exists():
            logger.warning(f"Recording not found: {recording_id}")
            return

        # Read existing data
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Update fields
        if task_description is not None:
            data["task_description"] = task_description
            logger.info(f"Updated task_description for {recording_id}")

        if user_query is not None:
            data["user_query"] = user_query
            logger.info(f"Updated user_query for {recording_id}")

        # Update timestamp
        data["updated_at"] = get_current_timestamp()

        # Save back
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_recording(self, user_id: str, recording_id: str) -> Optional[Dict]:
        """Read recording data.

        Args:
            user_id: User ID
            recording_id: Recording ID

        Returns:
            Recording data dict with operations and optionally graph
        """
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        file_path = recording_path / "operations.json"

        if not file_path.exists():
            logger.warning(f"Recording not found: {recording_id}")
            return None

        with open(file_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        # Load graph if exists
        graph_path = recording_path / "graph.json"
        if graph_path.exists():
            with open(graph_path, 'r', encoding='utf-8-sig') as f:
                data["graph"] = json.load(f)

        # Load metadata if exists
        metadata_path = recording_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                metadata = json.load(f)
                data["workflow_id"] = metadata.get("workflow_id")

        # Check if DOM snapshots exist
        dom_snapshots_dir = recording_path / "dom_snapshots"
        if dom_snapshots_dir.exists():
            data["has_dom_snapshots"] = True
            data["dom_snapshot_count"] = len(list(dom_snapshots_dir.glob("*.json")))
        else:
            data["has_dom_snapshots"] = False
            data["dom_snapshot_count"] = 0

        return data

    def get_recording_dom_snapshots(self, user_id: str, recording_id: str) -> Dict[str, Dict]:
        """Load DOM snapshots for a recording

        Args:
            user_id: User ID
            recording_id: Recording ID

        Returns:
            Dict mapping dom_id to DOM data (includes url and dom dict)
        """
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        dom_snapshots_dir = recording_path / "dom_snapshots"

        if not dom_snapshots_dir.exists():
            return {}

        dom_snapshots = {}
        for dom_file in dom_snapshots_dir.glob("*.json"):
            if dom_file.name == "url_index.json":
                continue
            try:
                dom_id = dom_file.stem  # filename without extension
                with open(dom_file, 'r', encoding='utf-8') as f:
                    dom_data = json.load(f)
                    # Return full data including url for matching
                    dom_snapshots[dom_id] = dom_data
            except Exception as e:
                logger.warning(f"Failed to load DOM snapshot {dom_file}: {e}")

        return dom_snapshots

    def update_recording_workflow(self, user_id: str, recording_id: str, workflow_id: str):
        """Update recording with associated workflow_id"""
        recording_path = self._user_path(user_id) / "recordings" / recording_id

        # Ensure recording directory exists
        if not recording_path.exists():
            logger.warning(f"Recording directory not found: {recording_path}")
            recording_path.mkdir(parents=True, exist_ok=True)

        current_time = get_current_timestamp()

        # Update metadata.json
        metadata_path = recording_path / "metadata.json"
        metadata = {}
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

        metadata["workflow_id"] = workflow_id
        metadata["updated_at"] = current_time

        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Also update operations.json updated_at for sync
        operations_path = recording_path / "operations.json"
        if operations_path.exists():
            with open(operations_path, 'r') as f:
                data = json.load(f)
            data["updated_at"] = current_time
            with open(operations_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Recording {recording_id} linked to Workflow {workflow_id}")

    def list_recordings(self, user_id: str) -> List[Dict]:
        """List all recordings for user with metadata"""
        recordings_path = self._user_path(user_id) / "recordings"

        if not recordings_path.exists():
            return []

        result = []
        for recording_dir in recordings_path.iterdir():
            if recording_dir.is_dir():
                recording_id = recording_dir.name
                recording = self.get_recording(user_id, recording_id)
                if recording:
                    result.append({
                        "recording_id": recording_id,
                        "task_description": recording.get("task_description"),
                        "created_at": recording.get("created_at"),
                        "operations_count": recording.get("operations_count"),
                        "workflow_id": recording.get("workflow_id")
                    })

        # Sort by created_at, handling None values
        return sorted(result, key=lambda x: x.get("created_at") or "", reverse=True)

    def delete_recording(self, user_id: str, recording_id: str) -> bool:
        """Delete a recording and all its associated files

        Args:
            user_id: User ID
            recording_id: Recording ID to delete

        Returns:
            True if deleted, False if not found
        """
        import shutil

        recording_path = self._user_path(user_id) / "recordings" / recording_id

        if not recording_path.exists():
            logger.warning(f"Recording not found for deletion: {recording_id}")
            return False

        try:
            shutil.rmtree(recording_path)
            logger.info(f"Deleted recording: {recording_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete recording {recording_id}: {e}")
            raise

    # ===== Workflow Management =====

    def save_workflow(
        self,
        user_id: str,
        workflow_id: str,
        workflow_yaml: str,
        workflow_name: str,
        source_recording_id: str = None,
        metaflow_id: str = None  # Deprecated, kept for backward compatibility
    ) -> str:
        """
        Save Workflow to server filesystem

        Args:
            user_id: User ID
            workflow_id: Workflow ID
            workflow_yaml: Workflow YAML content
            workflow_name: Display name for the workflow
            source_recording_id: Original recording ID (for traceability)
            metaflow_id: Deprecated, ignored

        Returns:
            workflow.yaml file path
        """
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        workflow_path.mkdir(parents=True, exist_ok=True)

        # Save workflow.yaml
        yaml_file = workflow_path / "workflow.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        # Save metadata.json with source information for traceability
        metadata = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "source_recording_id": source_recording_id,
            "created_at": get_current_timestamp(),
            "updated_at": get_current_timestamp()
        }
        metadata_file = workflow_path / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Workflow saved: {workflow_id} ({workflow_name})")
        if source_recording_id:
            logger.info(f"  Source recording: {source_recording_id}")
        return str(yaml_file)

    def get_workflow(self, user_id: str, workflow_id: str) -> Optional[Dict]:
        """Read Workflow data with metadata"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        yaml_file = workflow_path / "workflow.yaml"

        if not yaml_file.exists():
            logger.warning(f"Workflow not found: {workflow_id}")
            return None

        with open(yaml_file, 'r', encoding='utf-8') as f:
            workflow_yaml = f.read()

        # Load metadata
        metadata = {}
        metadata_file = workflow_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

        return {
            "workflow_id": workflow_id,
            "workflow_name": metadata.get("workflow_name", workflow_id),
            "workflow_yaml": workflow_yaml,
            "source_recording_id": metadata.get("source_recording_id"),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at")
        }

    def update_workflow_yaml(self, user_id: str, workflow_id: str, workflow_yaml: str):
        """Update Workflow YAML content"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        yaml_file = workflow_path / "workflow.yaml"

        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        # Update timestamp in metadata
        metadata_file = workflow_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            metadata["updated_at"] = get_current_timestamp()
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        logger.info(f"Workflow updated: {workflow_id}")

    def list_workflows(self, user_id: str) -> List[Dict]:
        """List all Workflows for user with metadata"""
        workflows_path = self._user_path(user_id) / "workflows"

        if not workflows_path.exists():
            return []

        result = []
        for workflow_dir in workflows_path.iterdir():
            if workflow_dir.is_dir():
                workflow_id = workflow_dir.name
                workflow = self.get_workflow(user_id, workflow_id)
                if workflow:
                    result.append({
                        "workflow_id": workflow_id,
                        "workflow_name": workflow.get("workflow_name"),
                        "created_at": workflow.get("created_at"),
                        "updated_at": workflow.get("updated_at")
                    })

        # Sort by created_at, handling None values
        return sorted(result, key=lambda x: x.get("created_at") or "", reverse=True)

    def workflow_exists(self, user_id: str, workflow_id: str) -> bool:
        """Check if Workflow exists"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id
        return (workflow_path / "workflow.yaml").exists()

    def delete_workflow(self, user_id: str, workflow_id: str) -> bool:
        """Delete Workflow directory completely

        Returns:
            True if deleted, False if not found
        """
        import shutil
        workflow_path = self._user_path(user_id) / "workflows" / workflow_id

        if not workflow_path.exists():
            logger.warning(f"Workflow not found for deletion: {workflow_id}")
            return False

        shutil.rmtree(workflow_path)
        logger.info(f"Workflow deleted: {workflow_id}")
        return True

    # ===== Workflow Resource Sync =====

    def get_workflow_path(self, user_id: str, workflow_id: str) -> Path:
        """Get workflow directory path"""
        return self._user_path(user_id) / "workflows" / workflow_id

    async def get_workflow_metadata(self, user_id: str, workflow_id: str) -> Optional[Dict]:
        """Get workflow metadata from cloud"""
        try:
            metadata_path = self.get_workflow_path(user_id, workflow_id) / "metadata.json"
            if not metadata_path.exists():
                return None

            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read cloud metadata: {e}")
            return None

    async def save_workflow_metadata(
        self,
        user_id: str,
        workflow_id: str,
        metadata: Dict
    ) -> bool:
        """
        Save workflow metadata to cloud

        CRITICAL: This method should preserve the updated_at timestamp in metadata
        """
        try:
            metadata_path = self.get_workflow_path(user_id, workflow_id) / "metadata.json"
            metadata_path.parent.mkdir(parents=True, exist_ok=True)

            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved workflow metadata to cloud: {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cloud metadata: {e}")
            return False

    def get_resource_path(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type  # ResourceType enum
    ) -> Path:
        """Get cloud resource directory path

        Path structure:
        ~/ami-server/users/{user_id}/workflows/{workflow_id}/{step_id}/

        Scripts are stored directly in step directory (no hash subdirectory).
        """
        workflow_path = self.get_workflow_path(user_id, workflow_id)
        return workflow_path / step_id

    async def save_workflow_resource(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type,  # ResourceType enum
        files: Dict[str, bytes]
    ) -> bool:
        """Save resource files to cloud"""
        try:
            resource_path = self.get_resource_path(
                user_id, workflow_id, step_id, resource_type
            )
            resource_path.mkdir(parents=True, exist_ok=True)

            for filename, content in files.items():
                file_path = resource_path / filename
                if isinstance(content, str):
                    file_path.write_text(content, encoding='utf-8')
                else:
                    file_path.write_bytes(content)

            logger.info(f"Saved resource for step {step_id} to cloud: {resource_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save resource to cloud: {e}")
            return False

    async def load_workflow_resource(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type  # ResourceType enum
    ) -> Optional[Dict[str, bytes]]:
        """Load resource files from cloud"""
        try:
            from src.common.resource_types import ResourceConfig, ResourceType

            resource_path = self.get_resource_path(
                user_id, workflow_id, step_id, resource_type
            )

            if not resource_path.exists():
                logger.warning(f"Resource not found in cloud: {resource_path}")
                return None

            # Convert to ResourceType if needed
            if not isinstance(resource_type, ResourceType):
                resource_type = ResourceType(resource_type)

            sync_files = ResourceConfig.get_sync_files(resource_type)
            files = {}

            for filename in sync_files:
                file_path = resource_path / filename
                if file_path.exists():
                    files[filename] = file_path.read_bytes()

            logger.info(f"Loaded {len(files)} files from cloud: {resource_path}")
            return files

        except Exception as e:
            logger.error(f"Failed to load resource from cloud: {e}")
            return None

    def _update_workflow_resources_sync(
        self,
        user_id: str,
        workflow_id: str
    ) -> bool:
        """
        Scan workflow directory and update metadata.json with resources info (sync version).

        This method scans the workflow directory for generated scripts and other
        resources, then updates the metadata.json to include them in the resources
        field. This is essential for client sync to download the generated files.

        Returns:
            True if successful, False otherwise
        """
        try:
            workflow_path = self.get_workflow_path(user_id, workflow_id)
            metadata_path = workflow_path / "metadata.json"

            if not metadata_path.exists():
                logger.warning(f"Metadata not found for workflow {workflow_id}")
                return False

            # Load existing metadata
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # Scan for resources
            resources = {"scraper_scripts": [], "browser_scripts": []}

            # Scan each step directory for script files (now directly in step directory)
            for step_dir in workflow_path.iterdir():
                if not step_dir.is_dir():
                    continue
                if step_dir.name in ["executions", ".claude", "dom_snapshots"]:
                    continue

                step_id = step_dir.name

                # Check for extraction_script.py (scraper_agent)
                extraction_script = step_dir / "extraction_script.py"
                if extraction_script.exists():
                    files = ["extraction_script.py"]
                    # Include dom_tools.py (required for script execution)
                    if (step_dir / "dom_tools.py").exists():
                        files.append("dom_tools.py")
                    # Include requirement.json (for cache validation)
                    if (step_dir / "requirement.json").exists():
                        files.append("requirement.json")

                    resources["scraper_scripts"].append({
                        "step_id": step_id,
                        "files": files
                    })
                    logger.info(f"Found scraper resource: {step_id} with {len(files)} files")

                # Check for find_element.py (browser_agent)
                find_element_script = step_dir / "find_element.py"
                if find_element_script.exists():
                    files = ["find_element.py"]
                    # Include element_tools.py (required for script execution)
                    if (step_dir / "element_tools.py").exists():
                        files.append("element_tools.py")
                    # Include task.json (for cache validation)
                    if (step_dir / "task.json").exists():
                        files.append("task.json")

                    resources["browser_scripts"].append({
                        "step_id": step_id,
                        "files": files
                    })
                    logger.info(f"Found browser resource: {step_id} with {len(files)} files")

            # Check if resources actually changed
            old_resources = metadata.get("resources", {})
            resources_changed = old_resources != resources

            # Update metadata with resources
            metadata["resources"] = resources

            # Only update updated_at if resources actually changed
            if resources_changed:
                from datetime import datetime, timezone
                metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
                logger.info(f"Resources changed, updated timestamp to {metadata['updated_at']}")

            # Save updated metadata
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"Updated metadata with {len(resources.get('scraper_scripts', []))} scraper_scripts, {len(resources.get('browser_scripts', []))} browser_scripts (changed: {resources_changed})")
            return True

        except Exception as e:
            logger.error(f"Failed to update workflow resources: {e}")
            return False

    async def update_workflow_resources(
        self,
        user_id: str,
        workflow_id: str
    ) -> bool:
        """
        Scan workflow directory and update metadata.json with resources info (async wrapper).

        Returns:
            True if successful, False otherwise
        """
        return self._update_workflow_resources_sync(user_id, workflow_id)
