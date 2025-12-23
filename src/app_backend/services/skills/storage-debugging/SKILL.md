---
name: storage-debugging
description: Fixes storage schema issues when data is not being saved to the database. Automatically adds missing fields to storage schema by comparing database structure with extracted fields. Use when user mentions data not saved, storage failed, schema errors, or database issues.
---

# Storage Debugging and Fix

Fix storage schema issues by comparing the current database table structure with extracted fields, then automatically updating workflow.yaml to include missing fields.

## When to use

Use this skill when the user reports:
- Data not saved to database (e.g., "data was not saved", "extracted data not in database")
- Storage failed or schema errors
- Fields extracted but not appearing in database
- Database-related issues

## How to fix (Follow ALL steps in order)

### Step 1: Read workflow configuration and identify components

```bash
cat workflow.yaml
```

Find:
1. **Storage step**: Look for `agent_type: storage_agent`
   - Note the `collection` name
   - Check if `schema` exists in `inputs`
2. **Scraper step**: Look for `agent_type: scraper_agent`
   - Note the step `id` for later use

Example workflow.yaml structure:
```yaml
steps:
  - id: extract-content
    agent_type: scraper_agent
    inputs:
      requirement:
        fields:
          - name: title
          - name: price
          - name: stock
    outputs:
      - items

  - id: save-to-storage
    agent_type: storage_agent
    inputs:
      operation: store
      collection: products           # Collection name
      data: "{{items}}"
      schema:                        # May be missing or incomplete!
        title:
          type: string
```

### Step 2: Check database current table structure

Get user_id and collection name from context:

```bash
# Get user_id
cat workflow_context.json

# Query database table structure
sqlite3 ~/.ami/databases/storage.db "PRAGMA table_info({collection_name}_{user_id})"
```

Example output:
```
0|id|INTEGER|0||1
1|title|TEXT|1||0
2|created_at|TEXT|1||0
```

This shows the table currently has columns: `id`, `title`, `created_at`

**Parse the output**:
- Column 1 (index): Column position
- Column 2 (name): **Field name** (ignore system fields: `id`, `created_at`, `updated_at`)
- Column 3 (type): SQLite type (TEXT, INTEGER, REAL, BLOB)
- Column 4 (notnull): NOT NULL constraint

**If table doesn't exist**: You'll get "Error: no such table". This means it's the first run - proceed to Step 3 to identify what fields should be in schema.

### Step 3: Identify fields being extracted

**Option A**: From workflow.yaml scraper requirement

Look at the scraper step's `inputs.requirement.fields`:
```yaml
- id: extract-content
  agent_type: scraper_agent
  inputs:
    requirement:
      fields:
        - name: title
        - name: price
        - name: stock
```

Extracted fields: `title`, `price`, `stock`

**Option B**: From scraper workspace (if workflow has been executed)

```bash
# Get user_id, workflow_id from workflow_context.json
cat workflow_context.json

# List fields from requirement.json
cat ~/.ami/users/{user_id}/workflows/{workflow_id}/{scraper_step_id}/scraper_script_*/requirement.json
```

### Step 4: Compare and identify missing fields

Compare:
1. **Current database fields** (from Step 2) - e.g., `title`
2. **Extracted fields** (from Step 3) - e.g., `title`, `price`, `stock`

**Missing fields**: Fields in extracted but NOT in database
- Example: `price`, `stock` are missing

**Field type mapping**:
- If field name contains "count", "quantity", "stock", "year" → `integer`
- If field name contains "price", "rating", "score", "weight" → `float` or `integer`
- If field name contains "url", "link", "title", "name", "description", "content" → `string`
- If field name contains "is_", "has_", "enabled", "active" → `boolean`
- Default: `string`

### Step 5: Fix the workflow.yaml schema (REQUIRED)

**CRITICAL**: You MUST use the Edit tool to modify workflow.yaml and add missing fields to the storage schema.

#### Case A: Schema field is completely missing

If storage step has NO `schema` field, add entire schema block:

```
Edit(
  file_path="workflow.yaml",
  old_string="    data: \"{{items}}\"",
  new_string="    data: \"{{items}}\"\n    schema:\n      title:\n        type: string\n        description: \"Product title\"\n      price:\n        type: float\n        description: \"Product price\"\n      stock:\n        type: integer\n        description: \"Stock quantity\""
)
```

#### Case B: Schema exists but missing fields

If schema exists but is incomplete, add only missing fields:

```
Edit(
  file_path="workflow.yaml",
  old_string="    schema:\n      title:\n        type: string\n        description: \"Product title\"",
  new_string="    schema:\n      title:\n        type: string\n        description: \"Product title\"\n      price:\n        type: float\n        description: \"Product price\"\n      stock:\n        type: integer\n        description: \"Stock quantity\""
)
```

**Important**:
- Match exact indentation (6 spaces for field names, 8 spaces for type/description)
- Preserve existing fields exactly
- Add new fields at the end
- Use correct YAML data types:
  - `string` → SQLite TEXT
  - `integer` → SQLite INTEGER
  - `float` → SQLite REAL
  - `boolean` → SQLite INTEGER (0/1)
  - `array`, `object` → SQLite TEXT (JSON-encoded)

### Step 6: Verify the fix

Read the file to confirm changes:

```bash
cat workflow.yaml
```

Verify:
- ✅ Schema includes all extracted fields
- ✅ Field types are appropriate
- ✅ YAML syntax is valid (proper indentation)

### Step 7: Update existing database table structure (REQUIRED)

**CRITICAL**: NEVER drop the database table! This will lose user data. Instead, use ALTER TABLE to add missing columns.

#### If table exists and missing fields were identified:

Add each missing field to the database table using ALTER TABLE:

```bash
# Add missing columns to existing table (one at a time)
sqlite3 ~/.ami/databases/storage.db "ALTER TABLE {collection_name}_{user_id} ADD COLUMN {field_name} {sqlite_type}"
```

**Type mapping** (workflow.yaml → SQLite):
- `string` → `TEXT`
- `integer` → `INTEGER`
- `float` → `REAL`
- `boolean` → `INTEGER`
- `array` → `TEXT`
- `object` → `TEXT`

**Example**: If missing field is `answer_count` (type: integer):
```bash
sqlite3 ~/.ami/databases/storage.db "ALTER TABLE zhihu_hot_topics_liuyihua ADD COLUMN answer_count INTEGER"
```

**Example**: If missing multiple fields (price: float, stock: integer):
```bash
sqlite3 ~/.ami/databases/storage.db "ALTER TABLE products_alice ADD COLUMN price REAL"
sqlite3 ~/.ami/databases/storage.db "ALTER TABLE products_alice ADD COLUMN stock INTEGER"
```

#### Clear schema cache after table modification:

```bash
# Clear cached schema so StorageAgent regenerates it
sqlite3 ~/.ami/databases/kv.db "DELETE FROM kv_storage WHERE key LIKE 'storage_schema_{collection_name}_{user_id}%'"
```

**Important notes**:
- ALTER TABLE ADD COLUMN preserves all existing data
- New columns will be NULL for existing rows (which is fine)
- SQLite does not support DROP COLUMN or MODIFY COLUMN directly
- If you need to change an existing column's type, report to user that manual migration is needed
- NEVER use DROP TABLE - this loses all user data!

### Step 8: Report results to user (REQUIRED)

**CRITICAL**: After completing all technical work, you MUST generate a comprehensive summary report for the user. Do NOT just complete the todos and end - the user needs to see what you fixed!

First, mark the todo as in_progress, then provide a detailed text report.

**Report template** (customize with actual details):

```
## ✅ Storage Issue Fixed!

### Problem Identified
The storage schema was missing the `answer_count` field.

**Database had**: title, content
**Scraper extracts**: title, content, answer_count
**Missing**: answer_count ❌

### Changes Made

1. **Updated workflow.yaml schema**
   - Added `answer_count` field (type: integer)
   - Description: "Number of answers for this question"

2. **Updated database table structure**
   - Added column `answer_count INTEGER` to table `zhihu_hot_topics_liuyihua`
   - Existing data preserved ✓
   - All previous records remain intact

3. **Cleared schema cache**
   - Removed cached schema from kv.db
   - StorageAgent will use updated structure

### Next Steps

✅ **You can now re-run the workflow**
   - All extracted fields will be saved correctly
   - The `answer_count` field will be stored in the database
   - Your existing data is preserved

**Verification**: After re-running, check the database:
```bash
sqlite3 ~/.ami/databases/storage.db "SELECT * FROM zhihu_hot_topics_liuyihua LIMIT 5"
```

You should now see the `answer_count` column with values!
```

**Important**:
- Use clear formatting with headers (##, ###)
- Use checkmarks (✅, ❌) for visual clarity
- Be specific about field names and types
- Reassure user that data is preserved
- Provide clear next steps

## Important notes

- **Always check database first** - This tells you what's currently stored
- **Use Edit tool** - Don't just suggest changes, actually modify workflow.yaml
- **Match types carefully** - Ensure YAML types match data types
- **Preserve existing schema** - Only add what's missing
- **YAML indentation** - Must be exact (use spaces, not tabs)
- **System fields** - Ignore `id`, `created_at`, `updated_at` when comparing

## Common scenarios

### Scenario 1: First workflow run (no database table yet)

```
User: "Data not being saved"

Steps:
1. cat workflow.yaml → storage schema is empty
2. sqlite3 query → "Error: no such table" (expected)
3. Check scraper requirement → extracts: title, price, stock
4. Edit workflow.yaml → add complete schema
5. Report: "Added schema with 3 fields. Run workflow to create table."
```

### Scenario 2: Schema missing new fields (table exists)

```
User: "New fields not appearing in database"

Steps:
1. cat workflow.yaml → schema has: title, price
2. sqlite3 query → table has: id, title, price, created_at
3. Check scraper → extracts: title, price, stock (stock is new!)
4. Edit workflow.yaml → add stock to schema
5. ALTER TABLE → sqlite3 ... "ALTER TABLE products_alice ADD COLUMN stock INTEGER"
6. Clear cache → sqlite3 kv.db "DELETE FROM kv_storage WHERE key LIKE 'storage_schema_%'"
7. Report: "Added 'stock' field to schema and database. Existing data preserved. Re-run workflow."
```

### Scenario 3: Schema completely missing

```
User: "Nothing is saved to database"

Steps:
1. cat workflow.yaml → no schema field at all
2. sqlite3 query → table exists but only has: id, created_at (no data fields!)
3. Check scraper → extracts: title, price, stock
4. Edit workflow.yaml → add entire schema block
5. ALTER TABLE → add all missing columns:
   - sqlite3 ... "ALTER TABLE products_alice ADD COLUMN title TEXT"
   - sqlite3 ... "ALTER TABLE products_alice ADD COLUMN price REAL"
   - sqlite3 ... "ALTER TABLE products_alice ADD COLUMN stock INTEGER"
6. Clear cache → sqlite3 kv.db "DELETE FROM kv_storage WHERE key LIKE 'storage_schema_%'"
7. Report: "Added complete schema. Added 3 columns to database. Re-run workflow."
```

## Database type reference

**YAML workflow.yaml types** → **SQLite types**:
- `string` → `TEXT`
- `integer` → `INTEGER`
- `float` → `REAL`
- `boolean` → `INTEGER` (0 or 1)
- `array` → `TEXT` (JSON-encoded)
- `object` → `TEXT` (JSON-encoded)

## Example complete execution

```
User: "Extracted data not saved to products collection"

Process:
1. cat workflow.yaml
   → storage step: collection="products", schema has only "title"
2. cat workflow_context.json
   → user_id="alice"
3. sqlite3 ~/.ami/databases/storage.db "PRAGMA table_info(products_alice)"
   → columns: id, title, created_at (missing: price, stock)
4. Check scraper in workflow.yaml
   → extracts: title, price, stock
5. Edit workflow.yaml to add price and stock:
   Edit(
     file_path="workflow.yaml",
     old_string="    schema:\n      title:\n        type: string\n        description: \"Product title\"",
     new_string="    schema:\n      title:\n        type: string\n        description: \"Product title\"\n      price:\n        type: float\n        description: \"Product price\"\n      stock:\n        type: integer\n        description: \"Stock quantity\""
   )
6. cat workflow.yaml
   → verify schema now has all 3 fields
7. Add missing columns to database:
   sqlite3 ~/.ami/databases/storage.db "ALTER TABLE products_alice ADD COLUMN price REAL"
   sqlite3 ~/.ami/databases/storage.db "ALTER TABLE products_alice ADD COLUMN stock INTEGER"
8. Clear schema cache:
   sqlite3 ~/.ami/databases/kv.db "DELETE FROM kv_storage WHERE key LIKE 'storage_schema_products_alice%'"
9. Report: "Fixed! Added 'price' and 'stock' to schema and database. Existing data preserved. Re-run workflow and all fields will be saved."
```

You MUST complete ALL steps using Read, Edit, and Bash tools. You MUST actually modify workflow.yaml - do not just provide suggestions!
