"""
DOM Tools for extraction script generation.

These tools help Claude analyze and navigate DOM structures to generate
robust extraction scripts.

Usage:
    python dom_tools.py <command> [args...]

Commands:
    find <xpath>                          - Find element, show value + children + siblings
    find <json_xpaths>                    - Find multiple elements, show structure for each
    container <xpath> [--fields ...]      - Extract list data from container
    search --text "..." [--tag ...]       - Search elements by content
    children <xpath> [tag]                - List children of container

The 'find' command is intelligent:
- If xpath points to a leaf element: returns the value directly
- If xpath points to a container: shows all children with data (xpath + text/href)
- Always shows sibling elements to help decide if content needs merging
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union


# =============================================================================
# Core Functions (can be imported by extraction scripts)
# =============================================================================

def normalize_xpath(xpath: str) -> str:
    """Normalize xpath for comparison (handle single vs double quotes)."""
    return xpath.replace("'", '"')


def find_by_xpath(dom: Dict, xpath: str) -> Optional[Dict]:
    """
    Find element by exact xpath match.

    Args:
        dom: Root DOM dictionary
        xpath: XPath string like "//*[@id='app']/div[4]/div/a[1]"

    Returns:
        Matching element dict or None
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
    """
    normalized_prefix = normalize_xpath(xpath_prefix)
    results = []
    seen_xpaths = set()

    def search(node: Dict):
        node_xpath = node.get('xpath', '')
        if node_xpath:
            normalized = normalize_xpath(node_xpath)
            if normalized.startswith(normalized_prefix + '/'):
                rest = normalized[len(normalized_prefix) + 1:]
                if '/' not in rest and normalized not in seen_xpaths:
                    seen_xpaths.add(normalized)
                    results.append(node)
        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def get_parent_xpath(xpath: str, levels: int = 1) -> str:
    """Get parent xpath by removing last N segments."""
    # Remove trailing index like [1] first
    xpath = re.sub(r'\[\d+\]$', '', xpath)

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


def build_virtual_container(dom: Dict, xpath: str) -> Optional[Dict]:
    """
    Build a virtual container element for containers that don't have their
    own xpath attribute but have children with matching xpath prefixes.
    """
    children = find_children_by_xpath_prefix(dom, xpath)
    if not children:
        return None

    parts = xpath.rstrip('/').split('/')
    last_part = parts[-1] if parts else 'div'
    tag = re.sub(r'\[\d+\]$', '', last_part)

    return {
        'tag': tag,
        'class': '',
        'xpath': xpath,
        'children': children,
        '_virtual': True
    }


def find_or_build_container(dom: Dict, xpath: str) -> Optional[Dict]:
    """Find element by xpath, or build a virtual container if not found."""
    result = find_by_xpath(dom, xpath)
    if result:
        return result
    return build_virtual_container(dom, xpath)


def extract_field(element: Dict, field: str) -> Optional[str]:
    """Extract a single field value from element."""
    if field == 'text':
        return element.get('text', '')
    elif field == 'href':
        return element.get('href', '')
    elif field == 'src':
        return element.get('src', '')
    elif field == 'class':
        return element.get('class', '')
    elif field == 'tag':
        return element.get('tag', '')
    else:
        return element.get(field, '')


def extract_from_element(element: Dict, fields: List[str]) -> Dict[str, str]:
    """Extract multiple fields from a single element."""
    result = {}
    for field in fields:
        result[field] = extract_field(element, field) or ''
    return result


def find_field_in_children(children: List[Dict], field: str, selector: str = None) -> Optional[str]:
    """
    Find a field value in children tree (DFS), optionally filtered by selector.

    Args:
        children: List of child elements
        field: Field to extract (text, href, src)
        selector: Optional CSS-like selector (tag or .class)
    """
    for child in children:
        # Check if current node matches selector
        matches = False
        if selector:
            if selector.startswith('.'):
                class_name = selector[1:]
                matches = class_name in (child.get('class') or '')
            else:
                matches = child.get('tag') == selector
        else:
            matches = True

        # If matches, try to extract field
        if matches:
            value = extract_field(child, field)
            if value:
                return value

        # Always recurse into children (DFS)
        if child.get('children'):
            value = find_field_in_children(child['children'], field, selector)
            if value:
                return value

    return None


def extract_list_item(item: Dict, field_mapping: Dict[str, str]) -> Dict[str, str]:
    """
    Extract fields from a list item based on field mapping.

    Args:
        item: List item element
        field_mapping: Dict of {output_name: "field:selector"} or {output_name: "field"}
            Examples:
            - {"name": "text"}  - get text from item
            - {"url": "href"}   - get href from item
            - {"name": "text:h4"} - get text from h4 child
            - {"name": "text:.title"} - get text from child with .title class
    """
    result = {}
    children = item.get('children', [])

    for output_name, spec in field_mapping.items():
        if ':' in spec:
            field, selector = spec.split(':', 1)
        else:
            field = spec
            selector = None

        # No selector: extract from item itself, then search children
        if not selector:
            value = extract_field(item, field)
            if not value:
                # If item has no value, search in children
                value = find_field_in_children(children, field, None)
            result[output_name] = value or ''
            continue

        # With selector: first check if item itself matches the selector
        item_tag = item.get('tag', '')
        if selector.startswith('.'):
            # Class selector - check if item has this class
            class_name = selector[1:]
            if class_name in (item.get('class') or ''):
                value = extract_field(item, field)
                if value:
                    result[output_name] = value
                    continue
        else:
            # Tag selector - check if item is this tag
            if item_tag == selector:
                value = extract_field(item, field)
                if value:
                    result[output_name] = value
                    continue

        # Search in children (recursive)
        value = find_field_in_children(children, field, selector)
        result[output_name] = value or ''

    return result


def extract_list(dom: Dict, container_xpath: str, field_mapping: Dict[str, str]) -> List[Dict]:
    """
    Extract list data from a container.

    Args:
        dom: Root DOM dictionary
        container_xpath: XPath of the container
        field_mapping: Dict of {output_name: "field:selector"}

    Returns:
        List of extracted data dicts
    """
    container = find_or_build_container(dom, container_xpath)
    if not container:
        return []

    results = []
    for child in container.get('children', []):
        item_data = extract_list_item(child, field_mapping)
        if any(item_data.values()):  # Only add if at least one field has value
            results.append(item_data)

    return results


def extract_single(dom: Dict, xpath: str, field: str = 'text') -> Optional[str]:
    """Extract a single field from an element by xpath."""
    element = find_by_xpath(dom, xpath)
    if element:
        return extract_field(element, field)
    return None


def extract_multi(dom: Dict, xpath_mapping: Dict[str, str], field: str = 'text') -> Dict[str, Optional[str]]:
    """
    Extract multiple fields from different xpaths.

    Args:
        dom: Root DOM dictionary
        xpath_mapping: Dict of {output_name: xpath}
        field: Field to extract from each element (default: text)

    Returns:
        Dict of {output_name: value}
    """
    result = {}
    for name, xpath in xpath_mapping.items():
        result[name] = extract_single(dom, xpath, field)
    return result


def search_by_text(dom: Dict, text: str, tag: str = None, class_contains: str = None) -> List[Dict]:
    """
    Search elements containing text.

    Args:
        dom: Root DOM dictionary
        text: Text to search for (case-insensitive)
        tag: Optional tag filter
        class_contains: Optional class substring filter

    Returns:
        List of matching elements with xpath
    """
    text_lower = text.lower()
    results = []

    def search(node: Dict):
        # Check if node matches
        node_text = (node.get('text') or '').lower()
        if text_lower in node_text:
            # Apply filters
            if tag and node.get('tag') != tag:
                pass
            elif class_contains and class_contains not in (node.get('class') or ''):
                pass
            elif node.get('xpath'):  # Only return elements with xpath
                results.append(node)

        # Recurse
        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def search_by_class(dom: Dict, class_contains: str, tag: str = None) -> List[Dict]:
    """Search elements by class substring."""
    results = []

    def search(node: Dict):
        node_class = node.get('class') or ''
        if class_contains in node_class:
            if tag and node.get('tag') != tag:
                pass
            elif node.get('xpath'):
                results.append(node)

        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def search_by_tag(dom: Dict, tag: str) -> List[Dict]:
    """Search elements by tag name."""
    results = []

    def search(node: Dict):
        if node.get('tag') == tag and node.get('xpath'):
            results.append(node)
        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


# =============================================================================
# Helper Functions
# =============================================================================

def truncate_element(element: Dict, max_depth: int = 2, current_depth: int = 0) -> Dict:
    """Truncate element tree to max depth for readable output."""
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
    """Format element for readable output."""
    truncated = truncate_element(element, max_depth)
    return json.dumps(truncated, indent=2, ensure_ascii=False)


def load_dom(file_path: str = "dom_data.json") -> Dict:
    """Load DOM from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_container(container: Dict) -> Dict:
    """Analyze container structure."""
    children = container.get('children', [])

    by_tag = {}
    by_class = {}

    for child in children:
        tag = child.get('tag', 'unknown')
        by_tag[tag] = by_tag.get(tag, 0) + 1

        class_str = child.get('class', '')
        if class_str:
            for cls in class_str.split():
                by_class[cls] = by_class.get(cls, 0) + 1

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


def parse_fields_arg(fields_str: str) -> Dict[str, str]:
    """
    Parse --fields argument like "name:text,url:href,title:text:h4"

    Returns:
        Dict of {output_name: "field:selector" or "field"}
    """
    result = {}
    for item in fields_str.split(','):
        item = item.strip()
        if not item:
            continue
        parts = item.split(':', 2)
        if len(parts) == 1:
            # Just field name, use as both output name and field
            result[parts[0]] = parts[0]
        elif len(parts) == 2:
            # name:field
            result[parts[0]] = parts[1]
        else:
            # name:field:selector
            result[parts[0]] = f"{parts[1]}:{parts[2]}"
    return result


# =============================================================================
# CLI Interface
# =============================================================================

def collect_children_with_data(element: Dict, max_depth: int = 5) -> List[Dict]:
    """
    Collect all descendant elements that have meaningful data (text or href).

    Args:
        element: Root element to search from
        max_depth: Maximum depth to search

    Returns:
        List of elements with xpath, text, href
    """
    results = []

    def collect(node: Dict, depth: int):
        if depth > max_depth:
            return

        # Check if this node has meaningful data
        text = node.get('text', '')
        href = node.get('href', '')
        xpath = node.get('xpath', '')

        # Only include if it has data and xpath
        if xpath and (text or href):
            # Skip if text is too long (likely aggregated container text)
            if len(text) <= 100:
                results.append({
                    'xpath': xpath,
                    'tag': node.get('tag', ''),
                    'text': text,
                    'href': href
                })

        # Recurse into children
        for child in node.get('children', []):
            collect(child, depth + 1)

    # Start from children, not the element itself
    for child in element.get('children', []):
        collect(child, 1)

    return results


def find_siblings(dom: Dict, xpath: str) -> List[Dict]:
    """
    Find sibling elements of the given xpath.

    Args:
        dom: Root DOM dictionary
        xpath: XPath of the element

    Returns:
        List of sibling elements with data
    """
    # Get parent xpath
    parent_xpath = get_parent_xpath(xpath, 1)
    if not parent_xpath:
        return []

    # Find parent container
    parent = find_or_build_container(dom, parent_xpath)
    if not parent:
        return []

    # Get siblings (children of parent, excluding the element itself)
    normalized_xpath = normalize_xpath(xpath)
    siblings = []

    for child in parent.get('children', []):
        child_xpath = normalize_xpath(child.get('xpath', ''))
        if child_xpath and child_xpath != normalized_xpath:
            text = child.get('text', '')
            href = child.get('href', '')
            if text or href:
                siblings.append({
                    'xpath': child.get('xpath', ''),
                    'tag': child.get('tag', ''),
                    'text': text[:100] if text else '',
                    'href': href
                })

    return siblings


def is_container(element: Dict) -> bool:
    """Check if element is a container (has children with data)."""
    children = element.get('children', [])
    if not children:
        return False

    # Check if any child has text or href
    for child in children:
        if child.get('text') or child.get('href'):
            return True
        # Check grandchildren too
        for grandchild in child.get('children', []):
            if grandchild.get('text') or grandchild.get('href'):
                return True

    return False


def cmd_find(dom: Dict, args: List[str]):
    """Handle find command - returns value + children + siblings for each xpath."""
    if not args:
        print("Usage: python dom_tools.py find <xpath>")
        print("       python dom_tools.py find '<json_xpaths>'")
        sys.exit(1)

    xpath_arg = args[0]

    # Check if it's JSON (multiple xpaths)
    if xpath_arg.startswith('{'):
        try:
            xpath_mapping = json.loads(xpath_arg)
        except json.JSONDecodeError:
            print(f"✗ Invalid JSON: {xpath_arg}")
            sys.exit(1)

        # Process each xpath
        all_results = {}
        code_xpaths = {}

        for name, xpath in xpath_mapping.items():
            element = find_by_xpath(dom, xpath)

            print(f"\n{'='*60}")
            print(f"Field: {name}")
            print(f"XPath: {xpath}")

            if not element:
                print(f"  ✗ Not found")
                all_results[name] = None
                continue

            text = element.get('text', '')
            href = element.get('href', '')
            tag = element.get('tag', '')

            print(f"  tag: {tag}")
            if text:
                text_preview = text[:80] + '...' if len(text) > 80 else text
                print(f"  text: \"{text_preview}\"")
            if href:
                print(f"  href: {href}")

            all_results[name] = text or href or ''
            code_xpaths[name] = xpath

            # Check if it's a container
            if is_container(element):
                print(f"\n  ⚠ Container detected - showing children with data:")
                children_data = collect_children_with_data(element)
                for i, child in enumerate(children_data[:10]):
                    child_text = child.get('text', '')
                    child_href = child.get('href', '')
                    # Show relative xpath (remove common prefix)
                    rel_xpath = child['xpath']
                    if rel_xpath.startswith(xpath):
                        rel_xpath = "..." + rel_xpath[len(xpath):]
                    print(f"    [{i+1}] {rel_xpath}")
                    print(f"        tag: {child['tag']}, text: \"{child_text[:50]}\"" + (f", href: {child_href}" if child_href else ""))
                if len(children_data) > 10:
                    print(f"    ... and {len(children_data) - 10} more")

                # Suggest using child xpath
                if children_data:
                    print(f"\n  → To extract specific value, use child xpath like:")
                    print(f"     {children_data[0]['xpath']}")

            # Show siblings
            siblings = find_siblings(dom, xpath)
            if siblings:
                print(f"\n  Siblings ({len(siblings)}):")
                for i, sib in enumerate(siblings[:5]):
                    sib_text = sib.get('text', '')[:50]
                    # Show relative xpath
                    rel_xpath = sib['xpath'].split('/')[-1] if '/' in sib['xpath'] else sib['xpath']
                    print(f"    [{i+1}] .../{rel_xpath}")
                    print(f"        tag: {sib['tag']}, text: \"{sib_text}\"")
                if len(siblings) > 5:
                    print(f"    ... and {len(siblings) - 5} more")

        # Summary
        found_count = sum(1 for v in all_results.values() if v is not None)
        print(f"\n{'='*60}")
        if found_count == len(all_results):
            print(f"✓ Found all {len(all_results)} elements")
        else:
            print(f"⚠ Found {found_count}/{len(all_results)} elements")

        # Output code snippet
        if code_xpaths:
            print("\n# Code snippet (update xpaths if needed based on children above):")
            print(f"from dom_tools import extract_multi")
            print(f"result = extract_multi(dom_dict, {json.dumps(code_xpaths, ensure_ascii=False)}, 'text')")

    else:
        # Single xpath
        element = find_by_xpath(dom, xpath_arg)
        if not element:
            print(f"✗ Element not found: {xpath_arg}")
            print("  Hint: Use 'search --text \"...\"' to find elements by content")
            return

        text = element.get('text', '')
        href = element.get('href', '')
        tag = element.get('tag', '')

        print(f"✓ Found: {xpath_arg}")
        print(f"  tag: {tag}")
        if element.get('class'):
            print(f"  class: {element.get('class')}")
        if text:
            text_preview = text[:80] + '...' if len(text) > 80 else text
            print(f"  text: \"{text_preview}\"")
        if href:
            print(f"  href: {href}")

        # Check if it's a container
        if is_container(element):
            print(f"\n⚠ Container detected - showing children with data:")
            children_data = collect_children_with_data(element)
            for i, child in enumerate(children_data[:10]):
                child_text = child.get('text', '')
                child_href = child.get('href', '')
                # Show relative xpath
                rel_xpath = child['xpath']
                if rel_xpath.startswith(xpath_arg):
                    rel_xpath = "..." + rel_xpath[len(xpath_arg):]
                print(f"  [{i+1}] {rel_xpath}")
                print(f"      tag: {child['tag']}, text: \"{child_text[:50]}\"" + (f", href: {child_href}" if child_href else ""))
            if len(children_data) > 10:
                print(f"  ... and {len(children_data) - 10} more")

            # Suggest using child xpath
            if children_data:
                print(f"\n→ To extract specific value, use child xpath like:")
                print(f"   {children_data[0]['xpath']}")

        # Show siblings
        siblings = find_siblings(dom, xpath_arg)
        if siblings:
            print(f"\nSiblings ({len(siblings)}):")
            for i, sib in enumerate(siblings[:5]):
                sib_text = sib.get('text', '')[:50]
                rel_xpath = sib['xpath'].split('/')[-1] if '/' in sib['xpath'] else sib['xpath']
                print(f"  [{i+1}] .../{rel_xpath}")
                print(f"      tag: {sib['tag']}, text: \"{sib_text}\"")
            if len(siblings) > 5:
                print(f"  ... and {len(siblings) - 5} more")

        # Output code snippet
        print("\n# Code snippet:")
        print(f"from dom_tools import extract_single")
        print(f"result = extract_single(dom_dict, \"{xpath_arg}\", 'text')")


def find_container_with_siblings(dom: Dict, xpath: str, min_siblings: int = 2, max_levels: int = 5) -> tuple:
    """
    Find a container by starting from xpath and going up until we find one with multiple children.

    Args:
        dom: Root DOM dictionary
        xpath: Starting xpath (typically a list item)
        min_siblings: Minimum number of siblings to consider it a valid container
        max_levels: Maximum levels to go up

    Returns:
        (container, container_xpath, levels_up) or (None, None, 0) if not found
    """
    current_xpath = xpath

    for level in range(max_levels + 1):
        if level > 0:
            current_xpath = get_parent_xpath(current_xpath, 1)
            if not current_xpath or current_xpath == xpath:
                break

        container = find_or_build_container(dom, current_xpath)
        if container:
            children_count = len(container.get('children', []))
            if children_count >= min_siblings:
                return container, current_xpath, level

    return None, None, 0


def cmd_container(dom: Dict, args: List[str]):
    """Handle container command."""
    if not args:
        print("Usage: python dom_tools.py container <xpath> [--fields name:text,url:href] [--parent N]")
        sys.exit(1)

    xpath = args[0]
    fields_str = None
    parent_levels = 0

    # Parse arguments
    i = 1
    while i < len(args):
        if args[i] == '--fields' and i + 1 < len(args):
            fields_str = args[i + 1]
            i += 2
        elif args[i] == '--parent' and i + 1 < len(args):
            parent_levels = int(args[i + 1])
            i += 2
        else:
            i += 1

    # Adjust xpath for explicit parent levels
    if parent_levels > 0:
        xpath = get_parent_xpath(xpath, parent_levels)
        print(f"  (Adjusted to parent: {xpath})")

    # Auto-find container by going up until we find one with multiple children
    container, container_xpath, levels_up = find_container_with_siblings(dom, xpath)

    if not container:
        print(f"✗ Container not found starting from: {xpath}")
        print("  Hint: Use 'search --text \"...\"' to find elements by content")
        return

    if levels_up > 0:
        print(f"  (Auto-adjusted {levels_up} level(s) up: {xpath} → {container_xpath})")
        xpath = container_xpath

    is_virtual = container.get('_virtual', False)
    children_count = len(container.get('children', []))

    if is_virtual:
        print(f"✓ Built virtual container: {xpath}")
        print(f"  (Found {children_count} child elements)")
    else:
        print(f"✓ Found container: {xpath}")
        print(f"  ({children_count} children)")

    if fields_str:
        # Extract data
        field_mapping = parse_fields_arg(fields_str)
        results = extract_list(dom, xpath, field_mapping)

        print(f"\nExtracted {len(results)} items:")
        for i, item in enumerate(results[:5]):
            print(f"  [{i+1}] {json.dumps(item, ensure_ascii=False)}")
        if len(results) > 5:
            print(f"  ... and {len(results) - 5} more")

        # Output code snippet
        print("\n# Code snippet:")
        print(f"from dom_tools import extract_list")
        print(f"results = extract_list(dom_dict, \"{xpath}\", {json.dumps(field_mapping, ensure_ascii=False)})")
    else:
        # Just show container info
        stats = analyze_container(container)
        print(f"  Tag: {stats['tag']}")
        print(f"  By tag: {json.dumps(stats['by_tag'])}")
        if stats['by_class']:
            top_classes = dict(sorted(stats['by_class'].items(), key=lambda x: -x[1])[:5])
            print(f"  Top classes: {json.dumps(top_classes)}")

        if stats['sample_child']:
            print(f"\n  Sample child:")
            print(json.dumps(stats['sample_child'], indent=4, ensure_ascii=False))


def cmd_search(dom: Dict, args: List[str]):
    """Handle search command."""
    if not args:
        print("Usage: python dom_tools.py search --text \"...\" [--tag ...] [--class ...]")
        sys.exit(1)

    text = None
    tag = None
    class_contains = None

    # Parse arguments
    i = 0
    while i < len(args):
        if args[i] == '--text' and i + 1 < len(args):
            text = args[i + 1]
            i += 2
        elif args[i] == '--tag' and i + 1 < len(args):
            tag = args[i + 1]
            i += 2
        elif args[i] == '--class' and i + 1 < len(args):
            class_contains = args[i + 1]
            i += 2
        else:
            i += 1

    results = []

    if text:
        results = search_by_text(dom, text, tag, class_contains)
        print(f"✓ Found {len(results)} elements containing \"{text}\":")
    elif class_contains:
        results = search_by_class(dom, class_contains, tag)
        print(f"✓ Found {len(results)} elements with class containing \"{class_contains}\":")
    elif tag:
        results = search_by_tag(dom, tag)
        print(f"✓ Found {len(results)} <{tag}> elements:")
    else:
        print("✗ Please specify --text, --class, or --tag")
        return

    for i, elem in enumerate(results[:10]):
        print(f"\n  [{i+1}] {elem.get('xpath')}")
        print(f"      tag: {elem.get('tag')}, class: \"{elem.get('class', '')}\"")
        if elem.get('text'):
            text_preview = elem['text'][:60] + '...' if len(elem['text']) > 60 else elem['text']
            print(f"      text: \"{text_preview}\"")
        if elem.get('href'):
            print(f"      href: {elem.get('href')}")

    if len(results) > 10:
        print(f"\n  ... and {len(results) - 10} more")




def cmd_children(dom: Dict, args: List[str]):
    """Handle children command."""
    if not args:
        print("Usage: python dom_tools.py children <xpath> [tag]")
        sys.exit(1)

    xpath = args[0]
    tag = args[1] if len(args) > 1 else None

    container = find_or_build_container(dom, xpath)
    if not container:
        print(f"✗ Container not found: {xpath}")
        return

    is_virtual = container.get('_virtual', False)
    children = container.get('children', [])

    if tag:
        children = [c for c in children if c.get('tag') == tag]

    print(f"✓ Found {len(children)} children" + (f" (tag={tag})" if tag else ""))
    if is_virtual:
        print(f"  (From virtual container)")

    for i, child in enumerate(children[:5]):
        print(f"\n  [{i+1}] {child.get('tag')} class=\"{child.get('class', '')}\"")
        print(f"      xpath: {child.get('xpath', 'N/A')}")
        if child.get('text'):
            text = child['text'][:50] + '...' if len(child['text']) > 50 else child['text']
            print(f"      text: {text}")

    if len(children) > 5:
        print(f"\n  ... and {len(children) - 5} more")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    # Load DOM
    dom_file = "dom_data.json"
    if not Path(dom_file).exists():
        print(f"Error: {dom_file} not found in current directory")
        sys.exit(1)

    dom = load_dom(dom_file)

    if command == "find":
        cmd_find(dom, args)
    elif command == "container":
        cmd_container(dom, args)
    elif command == "search":
        cmd_search(dom, args)
    elif command == "children":
        cmd_children(dom, args)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
