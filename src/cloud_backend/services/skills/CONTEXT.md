# Skills Service

Centralized management of Claude Code skills for workflow and script generation.

## Purpose

This service provides a single source of truth for all Claude Code skills used in the system. Skills are stored in `repository/` and copied to working directories at runtime by `SkillManager`.

## Structure

```
skills/
├── __init__.py          # Exports SkillManager
├── skill_manager.py     # Core skill management logic
├── CONTEXT.md           # This file
└── repository/          # All skills stored here
    ├── agent-specs/     # Agent I/O contracts
    ├── workflow-generation/   # Workflow YAML generation
    ├── workflow-optimizations/  # Optimization patterns
    ├── workflow-validation/     # Validation scripts
    ├── dom-extraction/   # DOM data extraction for script generation
    ├── element-finder/   # Browser element finding
    └── scraper-fix/      # Scraper extraction diagnostics and fixes
```

## Usage

```python
from src.cloud_backend.services.skills import SkillManager

# For workflow generation (agent-specs, workflow-*, etc.)
SkillManager.prepare_workflow_skills(working_dir)

# For browser script generation (element-finder)
SkillManager.prepare_browser_skills(working_dir, use_symlink=True)

# For scraper script generation (dom-extraction)
SkillManager.prepare_scraper_skills(working_dir)

# Get path to a specific skill
dom_tools_path = SkillManager.get_skill_path("dom-extraction") / "tools" / "dom_tools.py"
```

## Skill Groups

| Method | Skills Included | Used By |
|--------|----------------|---------|
| `prepare_workflow_skills()` | agent-specs, workflow-generation, workflow-optimizations, workflow-validation | WorkflowBuilder |
| `prepare_browser_skills()` | element-finder | BrowserAgent, BrowserScriptGenerator |
| `prepare_scraper_skills()` | dom-extraction | ScraperScriptGenerator |
| `prepare_modification_skills()` | All workflow skills + dom-extraction + scraper-fix | WorkflowModificationSession |

## When to Update Skills

- `agent-specs/`: When agent I/O contracts change
- `workflow-generation/`: When workflow YAML structure changes
- `dom-extraction/`: When extraction logic or dom_tools commands change
- `element-finder/`: When element finding logic changes
- `workflow-validation/`: When validation rules change
- `workflow-optimizations/`: When new optimization patterns discovered
- `scraper-fix/`: When diagnostic workflow or dom_tools commands change
