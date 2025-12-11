"""
Metadata Generator for Existing Workflows

This script scans existing workflow directories and generates metadata.json files
for workflows that don't have them yet. This is needed for workflows created
before the resource sync feature was implemented.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.common.timestamp_utils import get_current_timestamp

logger = logging.getLogger(__name__)


class MetadataGenerator:
    """Generate metadata.json for existing workflows"""

    def __init__(self, ami_root: Path = None):
        """
        Args:
            ami_root: Root directory for Ami data (default: ~/.ami)
        """
        if ami_root is None:
            ami_root = Path.home() / ".ami"
        self.ami_root = ami_root

    def scan_workflow(self, user_id: str, workflow_id: str) -> Optional[Dict]:
        """
        Scan a workflow directory and generate metadata

        Args:
            user_id: User ID
            workflow_id: Workflow ID

        Returns:
            Generated metadata dict, or None if workflow doesn't exist
        """
        workflow_path = self.ami_root / "users" / user_id / "workflows" / workflow_id

        if not workflow_path.exists():
            logger.warning(f"Workflow directory not found: {workflow_path}")
            return None

        logger.info(f"Scanning workflow: {workflow_id}")

        # Get workflow.yaml modification time as base timestamp
        workflow_yaml = workflow_path / "workflow.yaml"
        if workflow_yaml.exists():
            base_timestamp = datetime.fromtimestamp(workflow_yaml.stat().st_mtime, tz=timezone.utc).isoformat()
        else:
            base_timestamp = get_current_timestamp()

        # Initialize metadata structure
        metadata = {
            "workflow_id": workflow_id,
            "version": "1.0.0",
            "created_at": base_timestamp,
            "updated_at": base_timestamp,
            "resources": {
                "scraper_scripts": [],
                "code_agent_scripts": [],
                "custom_prompts": []
            }
        }

        # Scan for scraper scripts
        scraper_scripts = self._scan_scraper_scripts(workflow_path)
        if scraper_scripts:
            metadata["resources"]["scraper_scripts"] = scraper_scripts
            logger.info(f"Found {len(scraper_scripts)} scraper scripts")

        return metadata

    def _scan_scraper_scripts(self, workflow_path: Path) -> List[Dict]:
        """Scan for scraper_script_* directories"""
        scraper_scripts = []

        # Iterate through step directories
        for step_dir in workflow_path.iterdir():
            if not step_dir.is_dir():
                continue

            # Skip special directories
            if step_dir.name in ["executions", "metadata.json"]:
                continue

            step_id = step_dir.name

            # Look for scraper_script_* subdirectories
            for resource_dir in step_dir.iterdir():
                if not resource_dir.is_dir():
                    continue

                if not resource_dir.name.startswith("scraper_script_"):
                    continue

                resource_id = resource_dir.name

                # Check for required files
                extraction_script = resource_dir / "extraction_script.py"
                requirement_json = resource_dir / "requirement.json"
                test_extraction = resource_dir / "test_extraction.py"

                if not extraction_script.exists():
                    logger.warning(f"Missing extraction_script.py in {resource_dir}")
                    continue

                files = []
                if extraction_script.exists():
                    files.append("extraction_script.py")
                if requirement_json.exists():
                    files.append("requirement.json")
                if test_extraction.exists():
                    files.append("test_extraction.py")

                # Get latest modification time from the files
                timestamps = []
                for file in [extraction_script, requirement_json, test_extraction]:
                    if file.exists():
                        timestamps.append(file.stat().st_mtime)

                if timestamps:
                    latest_mtime = max(timestamps)
                    updated_at = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()
                else:
                    updated_at = get_current_timestamp()

                scraper_scripts.append({
                    "step_id": step_id,
                    "resource_id": resource_id,
                    "files": files,
                    "created_at": updated_at,
                    "updated_at": updated_at
                })

                logger.info(f"  Found resource: {step_id}/{resource_id} with {len(files)} files")

        return scraper_scripts

    def generate_metadata_file(self, user_id: str, workflow_id: str, force: bool = False) -> bool:
        """
        Generate and save metadata.json file for a workflow

        Args:
            user_id: User ID
            workflow_id: Workflow ID
            force: If True, overwrite existing metadata.json

        Returns:
            True if metadata was generated and saved successfully
        """
        workflow_path = self.ami_root / "users" / user_id / "workflows" / workflow_id
        metadata_path = workflow_path / "metadata.json"

        if metadata_path.exists() and not force:
            logger.info(f"Metadata already exists for {workflow_id}, skipping (use force=True to overwrite)")
            return False

        metadata = self.scan_workflow(user_id, workflow_id)
        if metadata is None:
            return False

        # Update workflow timestamp to latest resource timestamp
        resource_timestamps = []
        for resource_list in metadata["resources"].values():
            for resource in resource_list:
                if "updated_at" in resource:
                    resource_timestamps.append(resource["updated_at"])

        if resource_timestamps:
            metadata["updated_at"] = max(resource_timestamps)

        # Save metadata
        try:
            metadata_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            logger.info(f"Generated metadata.json for {workflow_id}: {metadata_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
            return False

    def scan_all_workflows(self, user_id: str, force: bool = False) -> Dict[str, bool]:
        """
        Scan all workflows for a user and generate missing metadata

        Args:
            user_id: User ID
            force: If True, overwrite existing metadata.json files

        Returns:
            Dict mapping workflow_id to success status
        """
        workflows_path = self.ami_root / "users" / user_id / "workflows"

        if not workflows_path.exists():
            logger.warning(f"Workflows directory not found: {workflows_path}")
            return {}

        results = {}

        for workflow_dir in workflows_path.iterdir():
            if not workflow_dir.is_dir():
                continue

            workflow_id = workflow_dir.name
            success = self.generate_metadata_file(user_id, workflow_id, force=force)
            results[workflow_id] = success

        logger.info(f"Scanned {len(results)} workflows, generated {sum(results.values())} metadata files")
        return results


def main():
    """Command-line interface for metadata generation"""
    import argparse

    parser = argparse.ArgumentParser(description="Generate metadata.json for existing workflows")
    parser.add_argument("user_id", help="User ID")
    parser.add_argument("--workflow-id", help="Specific workflow ID (optional, scans all if not provided)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing metadata.json files")
    parser.add_argument("--ami-root", help="Ami root directory (default: ~/.ami)")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)8s] %(message)s"
    )

    # Create generator
    ami_root = Path(args.ami_root) if args.ami_root else None
    generator = MetadataGenerator(ami_root=ami_root)

    # Generate metadata
    if args.workflow_id:
        success = generator.generate_metadata_file(args.user_id, args.workflow_id, force=args.force)
        if success:
            logger.info(f"✅ Successfully generated metadata for {args.workflow_id}")
        else:
            logger.error(f"❌ Failed to generate metadata for {args.workflow_id}")
    else:
        results = generator.scan_all_workflows(args.user_id, force=args.force)
        logger.info(f"\n{'='*60}")
        logger.info(f"Generated metadata for {sum(results.values())}/{len(results)} workflows")
        logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
