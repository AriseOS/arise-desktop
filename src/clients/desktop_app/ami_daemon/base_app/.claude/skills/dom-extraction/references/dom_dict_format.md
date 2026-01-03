# DOM Dictionary Format

## Structure

The DOM is represented as a nested Python dictionary, NOT HTML.

```json
{
  "tag": "a",
  "class": "product-list-item group",
  "href": "/products/example",
  "xpath": "//*[@id='app']/main/div[2]/div/a[1]",
  "text": "Product Name",
  "children": [
    {
      "tag": "div",
      "class": "product-info",
      "children": [
        {
          "tag": "h4",
          "text": "Product Title",
          "class": "product-name"
        }
      ]
    }
  ]
}
```

## Fields

| Field | Description |
|-------|-------------|
| `tag` | HTML tag name (e.g., "div", "a", "span") |
| `class` | CSS class attribute (may contain multiple classes) |
| `href` | Link URL (for `<a>` tags) |
| `src` | Image source (for `<img>` tags) |
| `text` | Text content of the element |
| `xpath` | XPath location in the original page |
| `children` | List of child elements |

## Important Notes

1. **Text content**: In the `"text"` field, not as a separate text node
2. **Attributes**: Direct keys in the dict (class, href, id, etc.)
3. **Children**: Always a list, even if empty
4. **XPath**: Matches the original page structure, use for grep/search

## Traversal Example

```python
def find_by_tag(node: Dict, tag: str) -> List[Dict]:
    """Find all elements with given tag."""
    results = []

    if node.get('tag') == tag:
        results.append(node)

    for child in node.get('children', []):
        results.extend(find_by_tag(child, tag))

    return results
```

## Class Matching

Classes may have additional modifiers. Use partial matching:

```python
# Bad - exact match fails
if node.get('class') == 'product-item':

# Good - partial match
if 'product-item' in node.get('class', ''):
```
