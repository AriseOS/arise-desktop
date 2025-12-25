# intent_builder/extractors/

Intent extraction from user operations.

## Files

| File | Purpose |
|------|---------|
| `intent_extractor.py` | Extracts Intent objects from user operation sequences |

## IntentExtractor

Converts raw user operations (from browser recording) into semantic Intent objects.

```python
extractor = IntentExtractor(llm_provider)
intents = await extractor.extract_intents(
    operations=operations_json,
    task_description="Collect coffee prices"
)
```

## Extraction Strategy

**Hybrid approach: Rules + LLM**

### Step 1: URL-based Segmentation (Rules)
Split operation sequence at URL changes:
- `navigate` action with new URL → new segment
- Each segment contains related operations

### Step 2: LLM Extraction (per segment)
For each segment, LLM generates:
- Intent description (semantic, human-readable)
- Operation indices (which operations belong to this intent)
- May generate 1-N intents per segment

## Input Format

```json
{
  "taskDescription": "Collect coffee product prices from Allegro",
  "operations": [
    {"type": "navigate", "url": "https://allegro.pl/"},
    {"type": "click", "element": {"textContent": "Menu"}},
    ...
  ]
}
```

## Output

List of Intent objects with:
- Semantic descriptions
- Associated operations
- Generated IDs (hash of description)
