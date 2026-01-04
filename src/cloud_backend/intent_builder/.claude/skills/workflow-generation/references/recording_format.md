# Recording Format Reference

## Directory Structure

```
{recording_id}/
├── operations.json      # User actions with dom_id references
└── dom_snapshots/
    ├── url_index.json   # URL to file mapping (for debugging)
    └── {dom_id}.json    # DOM snapshot files
```

## Operation Schema

Each operation in `operations.json` has the following structure:

```json
{
  "type": "click|navigate|input|select|scroll|newtab|closetab",
  "timestamp": "ISO datetime string",
  "url": "Page URL when action occurred",
  "dom_id": "12-char hash ID linking to DOM file (null if no DOM captured)",
  "page_title": "Page title",
  "element": {
    "xpath": "XPath to the element",
    "tagName": "HTML tag name",
    "className": "CSS class names",
    "textContent": "Visible text content",
    "href": "Link URL (for anchor elements)",
    "id": "Element ID (if any)"
  },
  "data": {
    // Type-specific data
  }
}
```

### Operation Types

| Type | Description | Key Fields |
|------|-------------|------------|
| `click` | User clicked an element | `element.xpath`, `element.href` |
| `navigate` | Page navigation | `data.fromUrl`, `data.toUrl` |
| `input` | Text input | `element.xpath`, `data.value` |
| `select` | Text selection | `data.selectedText` |
| `scroll` | Page scroll | `data.scrollY` |
| `newtab` | New tab opened | `data.target_id` |
| `closetab` | Tab closed | `data.target_id` |

## DOM Snapshot Format

Each DOM file (`{dom_id}.json`) contains:

```json
{
  "url": "Full URL of the page",
  "dom": {
    // DOM tree structure with interactive_index
  },
  "captured_at": "ISO datetime when captured"
}
```

### DOM Tree Node Structure

```json
{
  "tag": "div",
  "xpath": "//*[@id='app']/main/div[1]",
  "interactive_index": 42,  // Only for interactive elements
  "attributes": {
    "class": "container",
    "id": "main-content"
  },
  "text": "Visible text",
  "children": [...]
}
```

## Using dom_id to Find DOM

To find the DOM for an operation:

1. Get `dom_id` from the operation
2. If `dom_id` is null, no DOM was captured for that URL
3. Read `dom_snapshots/{dom_id}.json`
4. Parse the `dom` field to find elements by xpath

### Example

```python
# Given operation:
operation = {
    "type": "click",
    "url": "https://example.com/page",
    "dom_id": "39a7f9d42289",
    "element": {"xpath": "//*[@id='btn']"}
}

# Find corresponding DOM:
dom_file = f"dom_snapshots/{operation['dom_id']}.json"
# Read dom_file, then search for element by xpath
```

## url_index.json

For debugging purposes, `url_index.json` lists all captured URLs:

```json
[
  {
    "url": "https://example.com/",
    "file": "39a7f9d42289.json",
    "captured_at": "2026-01-04T17:58:23"
  }
]
```

This file is **not needed** for workflow generation - use `dom_id` directly.
