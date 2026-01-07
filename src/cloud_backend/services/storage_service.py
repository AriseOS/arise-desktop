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
                {run_id}.json

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

    # ===== Recording 管理 =====
    
    def save_recording(
        self,
        user_id: str,
        recording_id: str,
        operations: List[Dict],
        task_description: Optional[str] = None,
        user_query: Optional[str] = None,
        dom_snapshots: Optional[Dict[str, Dict]] = None
    ) -> str:
        """
        Save recording data to server filesystem

        Args:
            task_description: User's description of what they did
            user_query: User's description of what they want to do
            dom_snapshots: URL -> DOM dict mapping for pre-generating scripts

        Returns:
            File path
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
                    json.dump(dom_data, f, ensure_ascii=False)

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
        """Read recording data"""
        recording_path = self._user_path(user_id) / "recordings" / recording_id
        file_path = recording_path / "operations.json"

        if not file_path.exists():
            logger.warning(f"Recording not found: {recording_id}")
            return None

        with open(file_path, 'r') as f:
            data = json.load(f)

        # Load metadata if exists
        metadata_path = recording_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
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
        resource_type,  # ResourceType enum
        resource_id: str
    ) -> Path:
        """Get cloud resource directory path

        Path structure matches local structure:
        ~/ami-server/users/{user_id}/workflows/{workflow_id}/{step_id}/{resource_id}/

        Note: resource_type parameter is kept for API compatibility but not used in path
        """
        workflow_path = self.get_workflow_path(user_id, workflow_id)
        return workflow_path / step_id / resource_id

    async def save_workflow_resource(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type,  # ResourceType enum
        resource_id: str,
        files: Dict[str, bytes]
    ) -> bool:
        """Save resource files to cloud"""
        try:
            resource_path = self.get_resource_path(
                user_id, workflow_id, step_id, resource_type, resource_id
            )
            resource_path.mkdir(parents=True, exist_ok=True)

            for filename, content in files.items():
                file_path = resource_path / filename
                if isinstance(content, str):
                    file_path.write_text(content, encoding='utf-8')
                else:
                    file_path.write_bytes(content)

            logger.info(f"Saved resource {resource_id} to cloud: {resource_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save resource to cloud: {e}")
            return False

    async def load_workflow_resource(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type,  # ResourceType enum
        resource_id: str
    ) -> Optional[Dict[str, bytes]]:
        """Load resource files from cloud"""
        try:
            from src.common.resource_types import ResourceConfig, ResourceType

            resource_path = self.get_resource_path(
                user_id, workflow_id, step_id, resource_type, resource_id
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

    async def update_workflow_resources(
        self,
        user_id: str,
        workflow_id: str
    ) -> bool:
        """
        Scan workflow directory and update metadata.json with resources info.

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
            resources = {"scraper_scripts": []}

            # Scan each step directory for scraper_script_* folders
            for step_dir in workflow_path.iterdir():
                if not step_dir.is_dir():
                    continue
                if step_dir.name in ["executions", ".claude"]:
                    continue

                step_id = step_dir.name

                # Look for scraper_script_* directories
                for resource_dir in step_dir.iterdir():
                    if not resource_dir.is_dir():
                        continue

                    if resource_dir.name.startswith("scraper_script_"):
                        resource_id = resource_dir.name

                        # Get list of files to sync
                        files = []
                        extraction_script = resource_dir / "extraction_script.py"
                        if extraction_script.exists():
                            files.append("extraction_script.py")
                        # Include dom_tools.py (required for script execution)
                        dom_tools = resource_dir / "dom_tools.py"
                        if dom_tools.exists():
                            files.append("dom_tools.py")

                        if files:
                            resources["scraper_scripts"].append({
                                "step_id": step_id,
                                "resource_id": resource_id,
                                "files": files
                            })
                            logger.info(f"Found resource: {step_id}/{resource_id} with {len(files)} files")

            # Update metadata with resources
            metadata["resources"] = resources

            # Update updated_at timestamp
            from datetime import datetime, timezone
            metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

            # Save updated metadata
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"Updated metadata with {len(resources.get('scraper_scripts', []))} scraper_scripts")
            return True

        except Exception as e:
            logger.error(f"Failed to update workflow resources: {e}")
            return False
