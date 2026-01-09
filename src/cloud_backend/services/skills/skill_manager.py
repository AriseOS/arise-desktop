"""Centralized Skills management for Claude Agent workflows."""

import logging
import shutil
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SKILLS_REPOSITORY = Path(__file__).parent / "repository"


class SkillManager:
    """Centralized management of Skills copying and preparation."""

    # Pre-defined skill groups for different use cases
    WORKFLOW_SKILLS = [
        "agent-specs",
        "workflow-generation",
        "workflow-optimizations",
        "workflow-validation",
    ]
    BROWSER_SCRIPT_SKILLS = ["element-finder"]
    SCRAPER_SCRIPT_SKILLS = ["dom-extraction"]

    # Skills for workflow modification session (can modify workflow.yaml and scripts)
    MODIFICATION_SKILLS = [
        "agent-specs",
        "workflow-generation",
        "workflow-validation",
        "workflow-optimizations",
        "dom-extraction",
        "scraper-fix",
    ]

    @classmethod
    def prepare_skills(
        cls,
        working_dir: Path,
        skills: Optional[List[str]] = None,
        use_symlink: bool = False,
    ) -> Path:
        """
        Copy specified skills to the working directory.

        Args:
            working_dir: Target working directory
            skills: List of skill names to copy. None means all skills.
            use_symlink: Whether to use symlink (may fail on Windows)

        Returns:
            Path to the skills destination directory
        """
        skills_dest = working_dir / ".claude" / "skills"
        skills_dest.mkdir(parents=True, exist_ok=True)

        if skills is None:
            skills_to_copy = [
                d.name for d in SKILLS_REPOSITORY.iterdir() if d.is_dir()
            ]
        else:
            skills_to_copy = skills

        for skill_name in skills_to_copy:
            src = SKILLS_REPOSITORY / skill_name
            dst = skills_dest / skill_name
            if not src.exists():
                logger.warning(f"Skill not found: {skill_name}")
                continue
            if dst.exists():
                continue  # Already exists

            if use_symlink:
                try:
                    dst.symlink_to(src)
                    logger.debug(f"Symlinked skill: {skill_name}")
                except OSError:
                    # Fallback to copy on Windows or permission issues
                    shutil.copytree(src, dst)
                    logger.debug(f"Copied skill (symlink failed): {skill_name}")
            else:
                shutil.copytree(src, dst)
                logger.debug(f"Copied skill: {skill_name}")

        logger.info(f"Prepared {len(skills_to_copy)} skills in {skills_dest}")
        return skills_dest

    @classmethod
    def prepare_workflow_skills(cls, working_dir: Path) -> Path:
        """Prepare skills needed for workflow generation."""
        return cls.prepare_skills(working_dir, cls.WORKFLOW_SKILLS)

    @classmethod
    def prepare_browser_skills(
        cls, working_dir: Path, use_symlink: bool = False
    ) -> Path:
        """Prepare skills needed for browser script generation."""
        return cls.prepare_skills(working_dir, cls.BROWSER_SCRIPT_SKILLS, use_symlink)

    @classmethod
    def prepare_scraper_skills(cls, working_dir: Path) -> Path:
        """Prepare skills needed for scraper script generation."""
        return cls.prepare_skills(working_dir, cls.SCRAPER_SCRIPT_SKILLS)

    @classmethod
    def prepare_modification_skills(cls, working_dir: Path) -> Path:
        """Prepare skills for workflow modification session.

        Includes skills for both workflow YAML modification and script fixing.
        """
        return cls.prepare_skills(working_dir, cls.MODIFICATION_SKILLS)

    @classmethod
    def get_skill_path(cls, skill_name: str) -> Optional[Path]:
        """Get the path to a specific skill in the repository."""
        skill_path = SKILLS_REPOSITORY / skill_name
        if skill_path.exists():
            return skill_path
        return None

    @classmethod
    def list_available_skills(cls) -> List[str]:
        """List all available skills in the repository."""
        return [d.name for d in SKILLS_REPOSITORY.iterdir() if d.is_dir()]
