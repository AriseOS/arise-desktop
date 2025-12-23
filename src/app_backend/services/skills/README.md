# Claude Conversation Skills

This directory contains the conversation skill system for automated workflow debugging and fixing.

## Architecture

```
User Feedback
  ↓
ConversationSkillHandler
  - Loads skill metadata from YAML frontmatter
  - Creates temp workspace with workflow context
  - Copies skill directories for Claude to access
  ↓
Claude Agent SDK (streaming)
  - Claude reads user feedback
  - Claude autonomously decides which skill to use
  - Claude reads SKILL.md and follows instructions
  - Claude uses Read/Edit/Bash tools directly
  ↓
Returns response with detailed report
```

## Skills

Skills are **instruction-based** - each skill is a directory containing a `SKILL.md` file with YAML frontmatter.

### Available Skills

- **scraper-optimization** - Fixes scraper extraction issues when fields are missing or data is not extracted correctly
- **storage-debugging** - Fixes storage schema issues by checking database structure and updating workflow.yaml

### Skill Structure

```
skills/
├── scraper-optimization/
│   └── SKILL.md              # Instructions with YAML frontmatter
└── storage-debugging/
    └── SKILL.md              # Instructions with YAML frontmatter
```

### SKILL.md Format

```markdown
---
name: skill-name
description: Brief description for Claude to decide when to use this skill
---

# Skill Title

## When to use
- Trigger condition 1
- Trigger condition 2

## How to fix (Follow ALL steps in order)

### Step 1: ...
Instructions...

### Step 2: ...
Instructions...
```

## Key Principles

1. **Instruction-Based**: Skills are markdown instructions, not Python scripts
2. **Autonomous Decision**: Claude decides which skill to use based on description
3. **Direct Tool Usage**: Claude uses Read, Edit, Bash tools directly
4. **Automatic Fixing**: Skills fix problems, not just diagnose them
5. **Data Preservation**: Always preserve user data (use ALTER TABLE, not DROP TABLE)

## Adding New Skills

1. Create a new directory in `skills/`
2. Add `SKILL.md` with YAML frontmatter:
   ```yaml
   ---
   name: my-skill
   description: What this skill does and when to use it
   ---
   ```
3. Write step-by-step instructions for Claude
4. Skills are automatically loaded by ConversationSkillHandler

## Usage

The skill system is automatically invoked when users provide feedback on workflow execution. No manual configuration needed.

```python
from src.app_backend.services.conversation_skill_handler import ConversationSkillHandler

handler = ConversationSkillHandler(config_service=config_service)

async for event in handler.handle_feedback(
    user_message="Data not being saved",
    workflow_context=workflow_context,
    api_key=api_key
):
    # Stream events to frontend
    print(event)
```

## Benefits

- ✅ Zero data loss (ALTER TABLE instead of DROP TABLE)
- ✅ Automatic problem fixing
- ✅ Clear final reports to users
- ✅ Database-aware storage fixing
- ✅ Pure instruction-based (no Python scripts to maintain)
