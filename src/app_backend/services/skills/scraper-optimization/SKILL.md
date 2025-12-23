---
name: scraper-optimization
description: Fixes scraper extraction issues when fields are missing or data is not extracted correctly. Use when user mentions missing fields, extraction errors, data not being extracted, or field-related problems in Chinese or English.
---

# Scraper Optimization

Fix scraper extraction scripts when fields are missing or data is not extracted correctly.

## When to use

Use this skill when the user reports:
- Fields missing from extracted data (e.g., "回答数量字段没有被提取出来", "answer_count field not extracted")
- Data not extracted correctly
- Extraction errors or wrong data
- Field-related issues in workflow results

## How to fix (Follow ALL steps in order)

**🎯 EXECUTION FLOW**: Gather info → Locate workspace → Analyze → Find selector → Fix script → **GENERATE SUMMARY**

**CRITICAL**: Once you complete Step 5 (Edit the script), you MUST immediately jump to Step 6 and generate the final summary. DO NOT continue investigating or checking more files.

### Step 1: Gather required information

Read the context files to get necessary information:

```bash
cat workflow_context.json
cat workflow.yaml
```

From these files, identify:
- **user_id**: From `workflow_context.json` → `user_id` field
- **workflow_id**: From `workflow_context.json` → `workflow_id` field
- **step_id**: From `workflow.yaml` → Find the step with `agent_type: scraper_agent`, use its `id` field

Example from workflow.yaml:
```yaml
- id: extract-topic-content    # <-- This is the step_id
  agent_type: scraper_agent
  name: Extract Topic Content
  inputs:
    requirement: {...}
```

### Step 2: Locate the scraper workspace

The scraper workspace is located at:
```
~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*/
```

Find the exact workspace directory:

```bash
ls -d ~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*
```

Example:
```bash
ls -d ~/.ami/users/liuyihua/workflows/workflow_8958553f9570/extract-topic-content/scraper_script_*
```

This will show the full workspace path.

### Step 3: Analyze current state

Read these files from the workspace to understand the current situation:

```bash
# Read the extraction script
cat ~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*/extraction_script.py

# Read what should be extracted
cat ~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*/requirement.json

# List available DOM snapshots
ls ~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*/dom_snapshots/
```

Compare:
1. **What fields should be extracted** (from requirement.json)
2. **What fields are currently being extracted** (from extraction_script.py - look for the data dictionary)
3. **What data is available in DOM** (from dom_snapshots)

### Step 4: Examine DOM structure

Pick one DOM snapshot and analyze it to find where the missing field data exists:

```bash
# List snapshot directories
ls ~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*/dom_snapshots/

# Read a snapshot (replace {hash} with actual directory name)
cat ~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*/dom_snapshots/{hash}/dom_data.json
```

The DOM snapshot is JSON format with this structure:
```json
{
  "tag": "div",
  "attributes": {"class": "item-title"},
  "text": "Example text",
  "xpath": "/html/body/div[1]",
  "css_selector": "div.item-title",
  "children": [...]
}
```

**Search for the missing field in DOM**:
- Examine the JSON structure to find where the field data is located
- Note the CSS selector or xpath that can access this data
- Verify the selector is correct

### Step 5: Fix the extraction script (REQUIRED)

**CRITICAL**: You MUST use the Edit tool to modify the extraction_script.py file.

Find the exact location in the script where data fields are defined (usually in a `data = {...}` dictionary), then use the Edit tool:

**Important guidelines**:
- Keep the overall structure intact
- Don't modify function signatures or imports
- Only add/fix the specific fields mentioned by the user
- Use correct CSS selectors based on DOM analysis from Step 4
- Follow the existing code style and indentation
- Preserve exact whitespace and formatting

**Example Edit tool usage**:

If the current script has:
```python
        data = {
            'title': extract_text(element, '.title'),
            'url': extract_attr(element, 'a', 'href')
        }
```

And you need to add `answer_count` field, use Edit tool:
```
Edit(
  file_path="/Users/liuyihua/.ami/users/liuyihua/workflows/workflow_xxx/extract-topic-content/scraper_script_abc/extraction_script.py",
  old_string="        data = {\n            'title': extract_text(element, '.title'),\n            'url': extract_attr(element, 'a', 'href')\n        }",
  new_string="        data = {\n            'title': extract_text(element, '.title'),\n            'url': extract_attr(element, 'a', 'href'),\n            'answer_count': extract_text(element, '.answer-metrics span')  # FIXED: Added answer count extraction\n        }"
)
```

**CRITICAL**: You MUST actually use the Edit tool - do not just describe what should be done!

**⚠️ STOP AFTER EDITING ⚠️**: Once you have successfully used the Edit tool to fix the extraction script, DO NOT:
- ❌ Continue analyzing or checking DOM snapshots
- ❌ Run tests to verify the fix
- ❌ Check storage schemas
- ❌ Look for other potential issues
- ❌ Do any additional investigation

**IMMEDIATELY proceed to Step 6** to generate the final summary. Trust that your fix is correct based on your DOM analysis. The user will test it themselves. Any additional analysis after the edit is unnecessary and will result in an incomplete execution due to iteration limits.

**SPECIAL CASE - If extraction script is already correct**: If you find that the extraction script already includes the field correctly (Step 4 analysis shows it should work), DO NOT continue investigating storage or other components. Instead:
1. IMMEDIATELY go to Step 6
2. In your summary, report: "The extraction script already includes the `{field_name}` field correctly. The issue might be in storage (missing schema field) or elsewhere. The user should check the storage schema or contact support for further assistance."
3. DO NOT attempt to fix storage issues - that's a different skill (storage-debugging)

### Step 6: Generate comprehensive completion summary (MANDATORY - FINAL STEP)

**🚨 CRITICAL REQUIREMENT 🚨**: This is the LAST step. After completing all modifications, you MUST generate a comprehensive summary report. This is NOT optional.

**⏱️ ITERATION LIMIT WARNING**: You have a maximum of 30 iterations. If you've completed the Edit in Step 5, you MUST use your remaining iterations to generate a complete summary. Do NOT waste iterations on additional verification - the summary is more important than extra validation.

**DO NOT end with intermediate messages like:**
- ❌ "Let me check the DOM snapshot..."
- ❌ "Let me examine a recent DOM snapshot to see what the actual structure looks like"
- ❌ "I'll analyze the data structure..."
- ❌ "However, let me check if there might be an issue..."
- ❌ "部分回答个数字段没有提取出来"
- ❌ "Perfect! Now I can see the structure... let me check..."
- ❌ Any statement that suggests continued investigation (e.g., "Let me...", "I'll check...", "However...")
- ❌ Any incomplete analysis or investigation statement

**If you have completed the Edit tool to fix the script, you are DONE with the investigation phase. Go directly to the summary.**

**YOU MUST end with a complete summary that includes:**

1. **Clear Problem Statement** - What was wrong
2. **Specific Changes Made** - What you fixed with actual code
3. **Technical Details** - CSS selectors used and why they work
4. **Verification Steps** - How user can test the fix

**Report template** (customize with actual details):

```
## ✅ Scraper Extraction Issue - RESOLVED

### 📋 Problem Summary
[Clearly state what field(s) were missing and why]

Example:
The `answer_count` field was not being extracted from the zhihu topics.

**Analysis**:
- Required fields (from requirement.json): title, content, answer_count
- Script was extracting: title, content
- Missing: answer_count ❌

### 🔧 Solution Implemented

**Modified file**: `~/.ami/users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_*/extraction_script.py`

**Change made**:
```python
# Added this line to the data dictionary:
'answer_count': extract_text(element, '.answer-metrics span')
```

**Technical details**:
- CSS selector: `.answer-metrics span`
- Located by analyzing DOM snapshot: `dom_snapshots/{hash}/dom_data.json`
- This selector targets the answer count element in the zhihu topic card structure

### ✅ Completion Status

**All tasks completed**:
- ✅ Identified missing field in extraction script
- ✅ Analyzed DOM structure to find correct selector
- ✅ Modified extraction_script.py with correct field extraction
- ✅ Verified the edit was applied successfully

### 🎯 Next Steps for User

**To verify the fix**:
1. Re-run the workflow from the UI
2. Check the extracted results for the `answer_count` field
3. Verify all items now include the answer count data

**Expected result**: The workflow will now extract all required fields including `answer_count`.
```

**MANDATORY CHECKLIST - Your final message MUST include ALL of these**:
- ✅ Clear problem description
- ✅ Exact code changes made (show the actual code)
- ✅ CSS selector or xpath used
- ✅ File path that was modified
- ✅ Verification steps for the user
- ✅ Confirmation that ALL work is complete

**FORMATTING RULES**:
- Use clear section headers (##, ###)
- Use emojis for visual clarity (✅, ❌, 🔧, 📋, 🎯)
- Include code blocks with syntax highlighting
- Make it easy to scan and understand at a glance
- End with a definitive completion statement

**Remember**: This summary is the LAST thing you output. It represents the completion of the entire skill execution. Make it comprehensive, clear, and conclusive.

## Common issues and solutions

### Issue: Field in requirements but not in extraction script
**Solution**: Add the field to the data dictionary in extraction_script.py

### Issue: Wrong CSS selector
**Solution**: Analyze DOM snapshot to find correct selector, update in extraction_script.py

### Issue: Field name mismatch
**Solution**: Ensure field name in script matches requirement.json exactly

### Issue: Data exists in DOM but wrong location
**Solution**: Find correct element in DOM, update selector

## Important notes

- **Always read files first** before making changes
- **Preserve function structure** - don't rewrite the entire script
- **Test your understanding** by examining DOM before modifying code
- **Be minimal** - only fix what's broken, don't refactor
- **The workflow must have run at least once** to have DOM snapshots available
- **Use absolute paths** when reading/editing files in ~/.ami/users/...
- **Verify the edit succeeded** by reading the file again after editing

## Example complete execution

```
User feedback: "回答数量字段没有被提取出来"

Your process:
1. cat workflow_context.json → user_id="liuyihua", workflow_id="workflow_xxx"
2. cat workflow.yaml → find scraper step with id="extract-topic-content"
3. ls -d ~/.ami/users/liuyihua/workflows/workflow_xxx/extract-topic-content/scraper_script_*
   → workspace is scraper_script_abc123
4. cat ~/.ami/users/.../extraction_script.py → see current extraction logic
5. cat ~/.ami/users/.../requirement.json → confirm "answer_count" should be extracted
6. cat ~/.ami/users/.../dom_snapshots/abc123/dom_data.json → find answer count at ".answer-metrics span"
7. Use Edit tool to modify extraction_script.py:
   - Add 'answer_count': extract_text(element, '.answer-metrics span')
8. Report: "Fixed! Added answer_count extraction using selector '.answer-metrics span'. Please re-run workflow."
```

You complete ALL steps using Read, Edit, and Bash tools. No external scripts needed.
