"""
DOM Tools for extraction script generation.

These tools help Claude analyze and navigate DOM structures to generate
robust extraction scripts.

Usage:
    python dom_tools.py <command> [args...]

Commands:
    find <xpath>              - Find element by exact xpath match
    container <xpath>         - Build virtual container from children's xpath prefix
    analyze <xpath>           - Analyze container structure (supports virtual containers)
    children <xpath> [tag]    - List children of container (supports virtual containers)
    print <xpath> [depth]     - Print element structure (default depth: 2)
    fields <xpath>            - List available fields (text, href, src) in container
    extract <xpath> <field>   - Extract all values of a field (text, href, src) from container
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


def parse_xpath_to_path(xpath: str) -> List[tuple]:
    """
    Parse xpath string to a list of (tag, index) tuples.

    Example:
        "//*[@id='app']/div[4]/div/a[1]" -> [('*', 'app'), ('div', 4), ('div', None), ('a', 1)]
    """
    # Handle //*[@id='xxx'] prefix
    id_match = re.match(r"^//\*\[@id=['\"]([^'\"]+)['\"]\](.*)$", xpath)
    if id_match:
        root_id = id_match.group(1)
        rest = id_match.group(2)
        path = [('*', root_id)]  # Special marker for id-based root
    else:
        # Handle simple //tag or /tag prefix
        rest = re.sub(r'^/+', '', xpath)
        path = []

    # Parse remaining path segments
    if rest:
        segments = rest.strip('/').split('/')
        for seg in segments:
            if not seg:
                continue
            # Parse tag[index] format
            match = re.match(r'^(\w+)(?:\[(\d+)\])?$', seg)
            if match:
                tag = match.group(1)
                index = int(match.group(2)) if match.group(2) else None
                path.append((tag, index))

    return path


def find_element_by_id(dom: Dict, element_id: str) -> Optional[Dict]:
    """Find element by id attribute (recursive)."""
    if dom.get('id') == element_id:
        return dom

    for child in dom.get('children', []):
        result = find_element_by_id(child, element_id)
        if result:
            return result

    return None


def normalize_xpath(xpath: str) -> str:
    """
    Normalize xpath for comparison (handle single vs double quotes).
    """
    # Normalize quotes: convert single quotes to double quotes
    return xpath.replace("'", '"')


def find_by_xpath_attr(dom: Dict, xpath: str) -> Optional[Dict]:
    """
    Find element by searching for matching xpath attribute (recursive).

    This handles DOM structures where xpath is stored as an attribute
    rather than being derived from the tree structure.
    """
    normalized_target = normalize_xpath(xpath)

    def search(node: Dict) -> Optional[Dict]:
        node_xpath = node.get('xpath', '')
        if normalize_xpath(node_xpath) == normalized_target:
            return node
        for child in node.get('children', []):
            result = search(child)
            if result:
                return result
        return None

    return search(dom)


def find_children_by_xpath_prefix(dom: Dict, xpath_prefix: str) -> List[Dict]:
    """
    Find all elements whose xpath starts with the given prefix and are
    direct children (one level deeper in xpath hierarchy).

    This is useful for containers that don't have their own xpath attribute
    but have children with xpath attributes.

    Args:
        dom: Root DOM dictionary
        xpath_prefix: The xpath prefix to match (e.g., "//*[@id='app']/div[4]/div")

    Returns:
        List of direct child elements (one xpath level deeper than prefix)
    """
    normalized_prefix = normalize_xpath(xpath_prefix)
    results = []
    seen_xpaths = set()

    def search(node: Dict):
        node_xpath = node.get('xpath', '')
        if node_xpath:
            normalized = normalize_xpath(node_xpath)
            # Check if this is a direct child of the prefix
            if normalized.startswith(normalized_prefix + '/'):
                rest = normalized[len(normalized_prefix) + 1:]
                # Direct child has no more slashes (e.g., "a[1]" not "a[1]/div")
                if '/' not in rest and normalized not in seen_xpaths:
                    seen_xpaths.add(normalized)
                    results.append(node)
        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def build_virtual_container(dom: Dict, xpath: str) -> Optional[Dict]:
    """
    Build a virtual container element for containers that don't have their
    own xpath attribute but have children with matching xpath prefixes.

    This allows analyzing container structure even when the container itself
    was filtered out during DOM serialization (only content elements keep xpath).

    Args:
        dom: Root DOM dictionary
        xpath: The xpath of the container to build

    Returns:
        Virtual container dict with children, or None if no children found
    """
    children = find_children_by_xpath_prefix(dom, xpath)
    if not children:
        return None

    # Infer tag from the container xpath
    parts = xpath.rstrip('/').split('/')
    last_part = parts[-1] if parts else 'div'
    # Remove index like div[4] -> div
    tag = re.sub(r'\[\d+\]$', '', last_part)

    return {
        'tag': tag,
        'class': '',
        'xpath': xpath,
        'children': children,
        '_virtual': True  # Mark as virtual container
    }


def find_by_xpath(dom: Dict, xpath: str) -> Optional[Dict]:
    """
    Find element by exact xpath match.

    Args:
        dom: Root DOM dictionary
        xpath: XPath string like "//*[@id='app']/div[4]/div/a[1]"

    Returns:
        Matching element dict or None

    Note: This only finds elements that have the exact xpath attribute.
    Container elements (without xpath) won't be found - use build_virtual_container() instead.
    """
    return find_by_xpath_attr(dom, xpath)


def find_or_build_container(dom: Dict, xpath: str) -> Optional[Dict]:
    """
    Find element by xpath, or build a virtual container if not found.

    This is useful for container elements that don't have their own xpath
    attribute but have children with xpath attributes.

    Args:
        dom: Root DOM dictionary
        xpath: XPath string

    Returns:
        Element dict (real or virtual) or None
    """
    # First try exact match
    result = find_by_xpath_attr(dom, xpath)
    if result:
        return result

    # Try building virtual container from children
    return build_virtual_container(dom, xpath)


def get_parent_xpath(xpath: str, levels: int = 1) -> str:
    """
    Get parent xpath by removing last N segments.

    Args:
        xpath: Original xpath
        levels: How many levels to go up

    Returns:
        Parent xpath string
    """
    # Split by / but preserve the //*[@id='xxx'] prefix
    id_match = re.match(r"^(//\*\[@id=['\"][^'\"]+['\"]\])(.*)$", xpath)
    if id_match:
        prefix = id_match.group(1)
        rest = id_match.group(2)
    else:
        prefix = ""
        rest = xpath

    segments = rest.strip('/').split('/')
    if len(segments) <= levels:
        return prefix or "/"

    parent_segments = segments[:-levels]
    return prefix + '/' + '/'.join(parent_segments)


def find_parent(dom: Dict, xpath: str, levels: int = 1) -> Optional[Dict]:
    """
    Find parent container of an element.

    Args:
        dom: Root DOM dictionary
        xpath: XPath of child element
        levels: How many levels up (default: 1)

    Returns:
        Parent element dict or None
    """
    parent_xpath = get_parent_xpath(xpath, levels)
    return find_by_xpath(dom, parent_xpath)


def analyze_container(container: Dict) -> Dict:
    """
    Analyze container structure.

    Args:
        container: Container element dict

    Returns:
        {
            "xpath": container's xpath,
            "tag": container's tag,
            "class": container's class,
            "total_children": count,
            "by_tag": {"a": 20, "div": 5},
            "by_class": {"product-item": 20},
            "sample_child": first child structure (truncated)
        }
    """
    children = container.get('children', [])

    by_tag = {}
    by_class = {}

    for child in children:
        # Count by tag
        tag = child.get('tag', 'unknown')
        by_tag[tag] = by_tag.get(tag, 0) + 1

        # Count by class
        class_str = child.get('class', '')
        if class_str:
            # Split multiple classes
            for cls in class_str.split():
                by_class[cls] = by_class.get(cls, 0) + 1

    # Get sample child (first one, truncated)
    sample_child = None
    if children:
        sample_child = truncate_element(children[0], max_depth=2)

    return {
        "xpath": container.get('xpath', ''),
        "tag": container.get('tag', ''),
        "class": container.get('class', ''),
        "total_children": len(children),
        "by_tag": by_tag,
        "by_class": by_class,
        "sample_child": sample_child
    }


def get_children(container: Dict, tag: str = None, class_contains: str = None) -> List[Dict]:
    """
    Get children of container, optionally filtered.

    Args:
        container: Container element dict
        tag: Filter by tag name (optional)
        class_contains: Filter by class substring (optional)

    Returns:
        List of matching child elements
    """
    children = container.get('children', [])

    if tag:
        children = [c for c in children if c.get('tag') == tag]

    if class_contains:
        children = [c for c in children if class_contains in c.get('class', '')]

    return children


def truncate_element(element: Dict, max_depth: int = 2, current_depth: int = 0) -> Dict:
    """
    Truncate element tree to max depth for readable output.
    """
    if current_depth >= max_depth:
        children = element.get('children', [])
        if children:
            return {**{k: v for k, v in element.items() if k != 'children'},
                    'children': f"[... {len(children)} children ...]"}
        return element

    result = {}
    for key, value in element.items():
        if key == 'children':
            result['children'] = [
                truncate_element(child, max_depth, current_depth + 1)
                for child in value
            ]
        else:
            result[key] = value

    return result


def print_element(element: Dict, max_depth: int = 2) -> str:
    """
    Format element for readable output.

    Args:
        element: Element dict
        max_depth: Max depth to display (default: 2)

    Returns:
        Formatted JSON string
    """
    truncated = truncate_element(element, max_depth)
    return json.dumps(truncated, indent=2, ensure_ascii=False)


def load_dom(file_path: str = "dom_data.json") -> Dict:
    """Load DOM from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def collect_fields_from_container(dom: Dict, xpath_prefix: str) -> Dict[str, List[Dict]]:
    """
    Collect all field values (text, href, src) from elements under the given xpath prefix.

    Args:
        dom: Root DOM dictionary
        xpath_prefix: Container xpath prefix

    Returns:
        Dict with field names as keys and lists of {value, xpath} as values
    """
    normalized_prefix = normalize_xpath(xpath_prefix)
    fields = {'text': [], 'href': [], 'src': []}

    def collect(node: Dict):
        node_xpath = node.get('xpath', '')
        if node_xpath:
            normalized = normalize_xpath(node_xpath)
            if normalized.startswith(normalized_prefix + '/'):
                # Collect fields
                if node.get('text'):
                    fields['text'].append({
                        'value': node['text'],
                        'xpath': node_xpath,
                        'tag': node.get('tag', '')
                    })
                if node.get('href'):
                    fields['href'].append({
                        'value': node['href'],
                        'xpath': node_xpath,
                        'tag': node.get('tag', '')
                    })
                if node.get('src'):
                    fields['src'].append({
                        'value': node['src'],
                        'xpath': node_xpath,
                        'tag': node.get('tag', '')
                    })
        for child in node.get('children', []):
            collect(child)

    collect(dom)
    return fields


# === CLI Interface ===

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    # Load DOM
    dom_file = "dom_data.json"
    if not Path(dom_file).exists():
        print(f"Error: {dom_file} not found in current directory")
        sys.exit(1)

    dom = load_dom(dom_file)

    if command == "find":
        if len(sys.argv) < 3:
            print("Usage: python dom_tools.py find <xpath>")
            sys.exit(1)
        xpath = sys.argv[2]
        element = find_by_xpath(dom, xpath)
        if element:
            print(f"✓ Found element at {xpath}")
            print(print_element(element, max_depth=2))
        else:
            print(f"✗ Element not found: {xpath}")
            print("  Hint: This xpath may be a container without its own xpath attribute.")
            print("  Try 'container' command to build a virtual container from children.")

    elif command == "container":
        if len(sys.argv) < 3:
            print("Usage: python dom_tools.py container <xpath>")
            sys.exit(1)
        xpath = sys.argv[2]
        container = find_or_build_container(dom, xpath)
        if container:
            is_virtual = container.get('_virtual', False)
            if is_virtual:
                print(f"✓ Built virtual container for: {xpath}")
                print(f"  (Container itself has no xpath, built from {len(container.get('children', []))} children)")
            else:
                print(f"✓ Found container at {xpath}")
            print(print_element(container, max_depth=1))
        else:
            print(f"✗ Cannot build container: {xpath}")
            print("  No elements found with this xpath prefix.")

    elif command == "analyze":
        if len(sys.argv) < 3:
            print("Usage: python dom_tools.py analyze <xpath>")
            sys.exit(1)
        xpath = sys.argv[2]
        # Use find_or_build_container to support virtual containers
        container = find_or_build_container(dom, xpath)
        if container:
            is_virtual = container.get('_virtual', False)
            stats = analyze_container(container)
            print(f"✓ Container Analysis: {xpath}")
            if is_virtual:
                print(f"  (Virtual container built from children)")
            print(f"  Tag: {stats['tag']}")
            print(f"  Class: {stats['class']}")
            print(f"  Total children: {stats['total_children']}")
            print(f"  By tag: {json.dumps(stats['by_tag'])}")
            print(f"  By class: {json.dumps(stats['by_class'])}")
            if stats['sample_child']:
                print(f"\n  Sample child:")
                print(json.dumps(stats['sample_child'], indent=4, ensure_ascii=False))
        else:
            print(f"✗ Container not found: {xpath}")

    elif command == "children":
        if len(sys.argv) < 3:
            print("Usage: python dom_tools.py children <xpath> [tag] [class_contains]")
            sys.exit(1)
        xpath = sys.argv[2]
        tag = sys.argv[3] if len(sys.argv) > 3 else None
        class_contains = sys.argv[4] if len(sys.argv) > 4 else None

        # Use find_or_build_container to support virtual containers
        container = find_or_build_container(dom, xpath)
        if container:
            is_virtual = container.get('_virtual', False)
            children = get_children(container, tag, class_contains)
            print(f"✓ Found {len(children)} children")
            if is_virtual:
                print(f"  (From virtual container)")
            for i, child in enumerate(children[:5]):  # Show first 5
                print(f"\n  [{i+1}] {child.get('tag')} class=\"{child.get('class', '')}\"")
                print(f"      xpath: {child.get('xpath', 'N/A')}")
                if child.get('text'):
                    text = child['text'][:50] + '...' if len(child.get('text', '')) > 50 else child.get('text', '')
                    print(f"      text: {text}")
            if len(children) > 5:
                print(f"\n  ... and {len(children) - 5} more")
        else:
            print(f"✗ Container not found: {xpath}")

    elif command == "print":
        if len(sys.argv) < 3:
            print("Usage: python dom_tools.py print <xpath> [depth]")
            sys.exit(1)
        xpath = sys.argv[2]
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
        element = find_by_xpath(dom, xpath)
        if element:
            print(print_element(element, max_depth=depth))
        else:
            print(f"✗ Element not found: {xpath}")

    elif command == "fields":
        if len(sys.argv) < 3:
            print("Usage: python dom_tools.py fields <xpath>")
            sys.exit(1)
        xpath = sys.argv[2]
        fields = collect_fields_from_container(dom, xpath)
        print(f"✓ Fields in container: {xpath}")
        print(f"  text: {len(fields['text'])} values")
        print(f"  href: {len(fields['href'])} values")
        print(f"  src:  {len(fields['src'])} values")

    elif command == "extract":
        if len(sys.argv) < 4:
            print("Usage: python dom_tools.py extract <xpath> <field>")
            print("  field: text, href, or src")
            sys.exit(1)
        xpath = sys.argv[2]
        field = sys.argv[3]
        if field not in ('text', 'href', 'src'):
            print(f"✗ Unknown field: {field}")
            print("  Valid fields: text, href, src")
            sys.exit(1)
        fields = collect_fields_from_container(dom, xpath)
        values = fields[field]
        print(f"✓ Found {len(values)} '{field}' values in container")
        for i, item in enumerate(values[:10]):  # Show first 10
            value = item['value'][:60] + '...' if len(item['value']) > 60 else item['value']
            print(f"  [{i+1}] {value}")
            print(f"      tag: {item['tag']}, xpath: ...{item['xpath'][-40:]}")
        if len(values) > 10:
            print(f"\n  ... and {len(values) - 10} more")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
