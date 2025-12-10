"""
Resource Manager - Unified resource management for workflow resources

Key responsibility: Preserve timestamps during sync to avoid infinite loops
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

from src.common.resource_types import ResourceType, ResourceConfig

logger = logging.getLogger(__name__)


@dataclass
class ResourceInfo:
    """Resource metadata"""
    step_id: str
    resource_id: str
    resource_type: ResourceType
    files: List[str]
    created_at: str
    updated_at: str


@dataclass
class SyncResult:
    """Result of sync operation"""
    success: bool
    message: str
    synced_resources: List[ResourceInfo]
    errors: List[str]


class ResourceManager:
    """
    Universal resource manager for workflow-related resources

    CRITICAL: Timestamp preservation
    - Local changes: Use wall-clock time
    - Sync operations: Preserve source timestamp (no wall-clock update)
    """

    def __init__(self, config_service, storage_service=None):
        self.config_service = config_service
        self.storage_service = storage_service

    def get_local_workflow_path(self, user_id: str, workflow_id: str) -> Path:
        """Get local workflow directory path

        Path structure: ~/.ami/users/{user_id}/workflows/{workflow_id}/
        Resources are stored directly under workflow directory
        """
        # Get user home directory
        home_dir = Path.home()
        ami_root = home_dir / ".ami"
        return ami_root / "users" / user_id / "workflows" / workflow_id

    def get_local_resource_path(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type: ResourceType,
        resource_id: str
    ) -> Path:
        """Get local resource directory path"""
        workflow_path = self.get_local_workflow_path(user_id, workflow_id)
        return workflow_path / step_id / resource_id

    def save_resource_local(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type: ResourceType,
        resource_id: str,
        files: Dict[str, bytes],
        custom_timestamp: Optional[str] = None
    ) -> bool:
        """
        Save resource to local filesystem

        Args:
            custom_timestamp: If provided, use this instead of wall-clock (for sync)
        """
        try:
            resource_path = self.get_local_resource_path(
                user_id, workflow_id, step_id, resource_type, resource_id
            )
            resource_path.mkdir(parents=True, exist_ok=True)

            # Save files
            for filename, content in files.items():
                file_path = resource_path / filename
                if isinstance(content, str):
                    file_path.write_text(content, encoding='utf-8')
                else:
                    file_path.write_bytes(content)

            logger.info(f"Saved resource {resource_id} to {resource_path}")

            # Update metadata with correct timestamp
            self.update_workflow_metadata(
                user_id, workflow_id, step_id, resource_type, resource_id,
                list(files.keys()),
                custom_timestamp=custom_timestamp
            )

            return True

        except Exception as e:
            logger.error(f"Failed to save resource {resource_id}: {e}")
            return False

    def load_resource_local(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type: ResourceType,
        resource_id: str
    ) -> Optional[Dict[str, bytes]]:
        """Load resource from local filesystem"""
        try:
            resource_path = self.get_local_resource_path(
                user_id, workflow_id, step_id, resource_type, resource_id
            )

            if not resource_path.exists():
                logger.warning(f"Resource not found locally: {resource_path}")
                return None

            sync_files = ResourceConfig.get_sync_files(resource_type)
            files = {}

            for filename in sync_files:
                file_path = resource_path / filename
                if file_path.exists():
                    files[filename] = file_path.read_bytes()

            logger.info(f"Loaded {len(files)} files from {resource_path}")
            return files

        except Exception as e:
            logger.error(f"Failed to load resource {resource_id}: {e}")
            return None

    def update_workflow_metadata(
        self,
        user_id: str,
        workflow_id: str,
        step_id: str,
        resource_type: ResourceType,
        resource_id: str,
        files: List[str],
        custom_timestamp: Optional[str] = None
    ) -> bool:
        """
        Update workflow metadata with resource info and timestamp

        CRITICAL TIMESTAMP LOGIC:
        - If custom_timestamp is None: Use wall-clock (local change)
        - If custom_timestamp provided: Use it (sync operation, preserve source)
        """
        try:
            workflow_path = self.get_local_workflow_path(user_id, workflow_id)
            metadata_path = workflow_path / "metadata.json"

            # Load or create metadata
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            else:
                metadata = {
                    "workflow_id": workflow_id,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "resources": {}
                }

            # CRITICAL: Update timestamp
            if custom_timestamp:
                # Sync operation: preserve source timestamp
                metadata["updated_at"] = custom_timestamp
                logger.debug(f"Preserving timestamp from source: {custom_timestamp}")
            else:
                # Local modification: use wall-clock time
                metadata["updated_at"] = datetime.utcnow().isoformat() + "Z"
                logger.debug(f"Using wall-clock timestamp: {metadata['updated_at']}")

            # Update resource info
            resource_type_key = resource_type.value
            if resource_type_key not in metadata["resources"]:
                metadata["resources"][resource_type_key] = []

            # Find or create resource entry
            resource_list = metadata["resources"][resource_type_key]
            resource_entry = None
            for entry in resource_list:
                if entry["step_id"] == step_id and entry["resource_id"] == resource_id:
                    resource_entry = entry
                    break

            if resource_entry is None:
                resource_entry = {
                    "step_id": step_id,
                    "resource_id": resource_id,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
                resource_list.append(resource_entry)

            resource_entry["files"] = list(files)
            resource_entry["updated_at"] = metadata["updated_at"]

            # Save metadata
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            logger.info(f"Updated workflow metadata: {workflow_id}, timestamp: {metadata['updated_at']}")
            return True

        except Exception as e:
            logger.error(f"Failed to update workflow metadata: {e}")
            return False

    def get_local_metadata(self, user_id: str, workflow_id: str) -> Optional[Dict]:
        """Get local workflow metadata"""
        try:
            workflow_path = self.get_local_workflow_path(user_id, workflow_id)
            metadata_path = workflow_path / "metadata.json"

            if not metadata_path.exists():
                return None

            return json.loads(metadata_path.read_text(encoding='utf-8'))

        except Exception as e:
            logger.error(f"Failed to read local metadata: {e}")
            return None

    async def check_sync_needed(
        self,
        user_id: str,
        workflow_id: str
    ) -> tuple[bool, str]:
        """
        Check if sync is needed by comparing timestamps

        Returns:
            (needs_sync, direction) where direction is "download", "upload", or "none"
        """
        if not self.storage_service:
            return False, "none"

        try:
            local_metadata = self.get_local_metadata(user_id, workflow_id)
            local_updated_at = local_metadata.get("updated_at") if local_metadata else None

            cloud_metadata = await self.storage_service.get_workflow_metadata(user_id, workflow_id)
            cloud_updated_at = cloud_metadata.get("updated_at") if cloud_metadata else None

            if local_updated_at is None and cloud_updated_at is None:
                return False, "none"
            elif local_updated_at is None:
                return True, "download"
            elif cloud_updated_at is None:
                return True, "upload"
            elif cloud_updated_at > local_updated_at:
                return True, "download"
            elif local_updated_at > cloud_updated_at:
                return True, "upload"
            else:
                return False, "none"

        except Exception as e:
            logger.error(f"Failed to check sync status: {e}")
            return False, "none"

    async def sync_workflow_resources(
        self,
        user_id: str,
        workflow_id: str,
        direction: Optional[str] = None
    ) -> SyncResult:
        """
        Sync workflow resources between local and cloud

        Args:
            direction: "upload", "download", or None (auto-detect)
        """
        if not self.storage_service:
            return SyncResult(
                success=False,
                message="Storage service not available",
                synced_resources=[],
                errors=["No storage service configured"]
            )

        try:
            if direction is None:
                needs_sync, direction = await self.check_sync_needed(user_id, workflow_id)
                if not needs_sync:
                    return SyncResult(
                        success=True,
                        message="Already in sync",
                        synced_resources=[],
                        errors=[]
                    )

            if direction == "upload":
                return await self.upload_resources(user_id, workflow_id)
            elif direction == "download":
                return await self.download_resources(user_id, workflow_id)
            else:
                return SyncResult(
                    success=True,
                    message="No sync needed",
                    synced_resources=[],
                    errors=[]
                )

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return SyncResult(
                success=False,
                message=f"Sync failed: {str(e)}",
                synced_resources=[],
                errors=[str(e)]
            )

    async def upload_resources(
        self,
        user_id: str,
        workflow_id: str
    ) -> SyncResult:
        """Upload all workflow resources to cloud"""
        synced = []
        errors = []

        try:
            local_metadata = self.get_local_metadata(user_id, workflow_id)
            if not local_metadata:
                return SyncResult(
                    success=False,
                    message="No local metadata found",
                    synced_resources=[],
                    errors=["Local metadata not found"]
                )

            # CRITICAL: Get local timestamp before upload
            local_updated_at = local_metadata["updated_at"]
            logger.info(f"Uploading resources with timestamp: {local_updated_at}")

            # Upload each resource type
            for resource_type_key, resource_list in local_metadata.get("resources", {}).items():
                try:
                    resource_type = ResourceType(resource_type_key)
                except ValueError:
                    logger.warning(f"Unknown resource type: {resource_type_key}")
                    continue

                for resource_entry in resource_list:
                    try:
                        step_id = resource_entry["step_id"]
                        resource_id = resource_entry["resource_id"]

                        files = self.load_resource_local(
                            user_id, workflow_id, step_id, resource_type, resource_id
                        )

                        if not files:
                            errors.append(f"Failed to load resource {resource_id}")
                            continue

                        success = await self.storage_service.save_workflow_resource(
                            user_id, workflow_id, step_id, resource_type, resource_id, files
                        )

                        if success:
                            synced.append(ResourceInfo(
                                step_id=step_id,
                                resource_id=resource_id,
                                resource_type=resource_type,
                                files=list(files.keys()),
                                created_at=resource_entry.get("created_at", ""),
                                updated_at=resource_entry.get("updated_at", "")
                            ))
                        else:
                            errors.append(f"Failed to upload resource {resource_id}")

                    except Exception as e:
                        logger.error(f"Failed to upload resource: {e}")
                        errors.append(str(e))

            # CRITICAL: Upload metadata with PRESERVED timestamp
            await self.storage_service.save_workflow_metadata(
                user_id, workflow_id, local_metadata
            )
            logger.info(f"Uploaded metadata with preserved timestamp: {local_updated_at}")

            return SyncResult(
                success=len(errors) == 0,
                message=f"Uploaded {len(synced)} resources",
                synced_resources=synced,
                errors=errors
            )

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return SyncResult(
                success=False,
                message=f"Upload failed: {str(e)}",
                synced_resources=synced,
                errors=errors + [str(e)]
            )

    async def download_resources(
        self,
        user_id: str,
        workflow_id: str
    ) -> SyncResult:
        """Download all workflow resources from cloud"""
        synced = []
        errors = []

        try:
            cloud_metadata = await self.storage_service.get_workflow_metadata(user_id, workflow_id)
            if not cloud_metadata:
                return SyncResult(
                    success=False,
                    message="No cloud metadata found",
                    synced_resources=[],
                    errors=["Cloud metadata not found"]
                )

            # CRITICAL: Get cloud timestamp before download
            cloud_updated_at = cloud_metadata["updated_at"]
            logger.info(f"Downloading resources with timestamp: {cloud_updated_at}")

            # Download each resource type
            for resource_type_key, resource_list in cloud_metadata.get("resources", {}).items():
                try:
                    resource_type = ResourceType(resource_type_key)
                except ValueError:
                    logger.warning(f"Unknown resource type: {resource_type_key}")
                    continue

                for resource_entry in resource_list:
                    try:
                        step_id = resource_entry["step_id"]
                        resource_id = resource_entry["resource_id"]

                        files = await self.storage_service.load_workflow_resource(
                            user_id, workflow_id, step_id, resource_type, resource_id
                        )

                        if not files:
                            errors.append(f"Failed to download resource {resource_id}")
                            continue

                        # CRITICAL: Save to local with PRESERVED cloud timestamp
                        success = self.save_resource_local(
                            user_id, workflow_id, step_id, resource_type, resource_id, files,
                            custom_timestamp=cloud_updated_at
                        )

                        if success:
                            synced.append(ResourceInfo(
                                step_id=step_id,
                                resource_id=resource_id,
                                resource_type=resource_type,
                                files=list(files.keys()),
                                created_at=resource_entry.get("created_at", ""),
                                updated_at=resource_entry.get("updated_at", "")
                            ))
                        else:
                            errors.append(f"Failed to save resource {resource_id}")

                    except Exception as e:
                        logger.error(f"Failed to download resource: {e}")
                        errors.append(str(e))

            # Save metadata locally with preserved timestamp
            workflow_path = self.get_local_workflow_path(user_id, workflow_id)
            metadata_path = workflow_path / "metadata.json"
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps(cloud_metadata, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            logger.info(f"Downloaded metadata with preserved timestamp: {cloud_updated_at}")

            return SyncResult(
                success=len(errors) == 0,
                message=f"Downloaded {len(synced)} resources",
                synced_resources=synced,
                errors=errors
            )

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return SyncResult(
                success=False,
                message=f"Download failed: {str(e)}",
                synced_resources=synced,
                errors=errors + [str(e)]
            )
