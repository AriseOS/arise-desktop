"""
Element Finder Tools for browser interaction script generation.

These tools help Claude find interactive elements in DOM to generate
robust find_element.py scripts.

Usage:
    python element_tools.py <command> [args...]

Commands:
    find <xpath>              - Find element by xpath, return interactive_index
    search <keyword>          - Search elements by text/aria-label/placeholder
    list <xpath>              - List interactive elements in container
    attr <attr> <value>       - Search by attribute (class, aria-label, placeholder, id)
    hint <xpath>              - Analyze xpath hint, find matching interactive element
    print <xpath> [depth]     - Print element structure (default depth: 2)

Note: Only elements with 'interactive_index' can be clicked or filled.
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


def normalize_xpath(xpath: str) -> str:
    """Normalize xpath for comparison (handle single vs double quotes)."""
    return xpath.replace("'", '"')


def find_by_xpath_attr(dom: Dict, xpath: str) -> Optional[Dict]:
    """
    Find element by searching for matching xpath attribute (recursive).
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


def find_interactive_elements(dom: Dict) -> List[Dict]:
    """
    Find all elements with interactive_index (clickable/fillable elements).

    Returns:
        List of elements with interactive_index
    """
    results = []

    def search(node: Dict):
        if node.get('interactive_index') is not None:
            results.append(node)
        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def search_by_text(dom: Dict, keywords: List[str], require_interactive: bool = True) -> List[Dict]:
    """
    Search elements containing any of the keywords in text.

    Args:
        dom: DOM dictionary
        keywords: List of keywords to search (case insensitive)
        require_interactive: Only return elements with interactive_index

    Returns:
        List of matching elements
    """
    results = []
    keywords_lower = [k.lower() for k in keywords]

    def search(node: Dict):
        text = (node.get('text', '') or '').lower()
        has_index = node.get('interactive_index') is not None

        for kw in keywords_lower:
            if kw in text:
                if not require_interactive or has_index:
                    results.append(node)
                    break

        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def search_by_attribute(dom: Dict, attr: str, value: str, require_interactive: bool = True) -> List[Dict]:
    """
    Search elements by attribute value.

    Args:
        dom: DOM dictionary
        attr: Attribute name (class, aria-label, placeholder, id, etc.)
        value: Value to search for (case insensitive, partial match)
        require_interactive: Only return elements with interactive_index

    Returns:
        List of matching elements
    """
    results = []
    value_lower = value.lower()

    def search(node: Dict):
        attr_value = (node.get(attr, '') or '').lower()
        has_index = node.get('interactive_index') is not None

        if value_lower in attr_value:
            if not require_interactive or has_index:
                results.append(node)

        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def find_children_by_xpath_prefix(dom: Dict, xpath_prefix: str) -> List[Dict]:
    """
    Find all elements whose xpath starts with the given prefix.
    """
    normalized_prefix = normalize_xpath(xpath_prefix)
    results = []

    def search(node: Dict):
        node_xpath = node.get('xpath', '')
        if node_xpath:
            normalized = normalize_xpath(node_xpath)
            if normalized.startswith(normalized_prefix + '/') or normalized == normalized_prefix:
                results.append(node)
        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def list_interactive_in_container(dom: Dict, xpath_prefix: str) -> List[Dict]:
    """
    List all interactive elements under a container xpath.

    Args:
        dom: DOM dictionary
        xpath_prefix: Container xpath

    Returns:
        List of interactive elements in container
    """
    normalized_prefix = normalize_xpath(xpath_prefix)
    results = []

    def search(node: Dict):
        node_xpath = node.get('xpath', '')
        if node_xpath:
            normalized = normalize_xpath(node_xpath)
            if normalized.startswith(normalized_prefix):
                if node.get('interactive_index') is not None:
                    results.append(node)
        for child in node.get('children', []):
            search(child)

    search(dom)
    return results


def get_parent_xpath(xpath: str, levels: int = 1) -> str:
    """Get parent xpath by removing last N segments."""
    import re
    # Handle ID-based xpath like //*[@id="app"]/div/span
    id_match = re.match(r"^(//\*\[@id=['\"][^'\"]+['\"]\])(.*)$", xpath)
    if id_match:
        id_part = id_match.group(1)
        rest = id_match.group(2)
        parts = [p for p in rest.split('/') if p]
        if len(parts) <= levels:
            return id_part
        remaining = '/'.join(parts[:-levels])
        return f"{id_part}/{remaining}" if remaining else id_part
    else:
        parts = xpath.split('/')
        if len(parts) <= levels:
            return ''
        return '/'.join(parts[:-levels])


def analyze_xpath_hint(dom: Dict, xpath_hint: str, max_levels: int = 5) -> Dict:
    """
    Analyze xpath hint from recording and find the best matching interactive element.

    The xpath hint from recording may not exactly match the current DOM,
    so we try multiple strategies:
    1. Exact xpath match
    2. Auto-search up parent levels to find interactive elements

    Args:
        dom: DOM dictionary
        xpath_hint: XPath from user's recording
        max_levels: Maximum levels to search up

    Returns:
        Analysis result with best match and alternatives
    """
    result = {
        'xpath_hint': xpath_hint,
        'exact_match': None,
        'interactive_match': None,
        'alternatives': [],
        'levels_up': 0
    }

    # Strategy 1: Exact match
    exact = find_by_xpath_attr(dom, xpath_hint)
    if exact:
        result['exact_match'] = {
            'interactive_index': exact.get('interactive_index'),
            'tag': exact.get('tag'),
            'text': (exact.get('text', '') or '')[:50],
            'class': exact.get('class', ''),
            'xpath': exact.get('xpath', '')
        }
        if exact.get('interactive_index') is not None:
            result['interactive_match'] = result['exact_match']
            return result

    # Strategy 2: Auto-search up parent levels
    current_xpath = xpath_hint
    for level in range(1, max_levels + 1):
        parent_xpath = get_parent_xpath(current_xpath, 1)
        if not parent_xpath or parent_xpath == current_xpath:
            break
        current_xpath = parent_xpath

        siblings = list_interactive_in_container(dom, parent_xpath)
        if siblings:
            result['levels_up'] = level
            for elem in siblings[:5]:  # Top 5 alternatives
                result['alternatives'].append({
                    'interactive_index': elem.get('interactive_index'),
                    'tag': elem.get('tag'),
                    'text': (elem.get('text', '') or '')[:50],
                    'xpath': elem.get('xpath', ''),
                    'class': elem.get('class', '')
                })

            if result['interactive_match'] is None:
                result['interactive_match'] = result['alternatives'][0]
            break

    return result


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


def format_element_summary(elem: Dict) -> str:
    """Format element as a one-line summary."""
    idx = elem.get('interactive_index', 'N/A')
    tag = elem.get('tag', '?')
    text = (elem.get('text', '') or '')[:30]
    if len(elem.get('text', '') or '') > 30:
        text += '...'
    cls = elem.get('class', '')[:30]
    return f"[{idx}] <{tag}> text=\"{text}\" class=\"{cls}\""


def load_dom(file_path: str = "dom_data.json") -> Dict:
    """Load DOM from JSON file.

    DOM files use wrapped format: {"url": "...", "dom": {...}}
    Returns the DOM dictionary (unwrapped) ready for traversal.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # All DOM files use wrapped format: {"url": ..., "dom": {...}}
    if "dom" not in data:
        raise ValueError(f"Invalid DOM format: missing 'dom' key. Expected wrapped format.")

    return data["dom"]


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
            print("Usage: python element_tools.py find <xpath>")
            sys.exit(1)
        xpath = sys.argv[2]
        element = find_by_xpath_attr(dom, xpath)
        if element:
            idx = element.get('interactive_index')
            if idx is not None:
                print(f"FOUND: interactive_index = {idx}")
                print(f"  tag: {element.get('tag')}")
                print(f"  text: {(element.get('text', '') or '')[:50]}")
                print(f"  class: {element.get('class', '')}")
            else:
                print(f"FOUND but NOT interactive (no interactive_index)")
                print(f"  tag: {element.get('tag')}")
                print(f"  text: {(element.get('text', '') or '')[:50]}")
                print("  Hint: This element cannot be clicked. Look for a parent or sibling with interactive_index.")
        else:
            print(f"NOT FOUND: {xpath}")
            print("  Hint: Try 'search' or 'attr' command to find similar elements.")

    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python element_tools.py search <keyword>")
            print("  Searches text, aria-label, and placeholder for keyword")
            sys.exit(1)
        keyword = sys.argv[2]

        # Search in multiple attributes
        results = []
        results.extend(search_by_text(dom, [keyword]))
        results.extend(search_by_attribute(dom, 'aria-label', keyword))
        results.extend(search_by_attribute(dom, 'placeholder', keyword))

        # Dedupe by interactive_index
        seen = set()
        unique = []
        for r in results:
            idx = r.get('interactive_index')
            if idx is not None and idx not in seen:
                seen.add(idx)
                unique.append(r)

        print(f"FOUND {len(unique)} interactive elements matching '{keyword}':")
        for elem in unique[:10]:
            print(f"\n  {format_element_summary(elem)}")
            print(f"      xpath: {elem.get('xpath', 'N/A')}")
        if len(unique) > 10:
            print(f"\n  ... and {len(unique) - 10} more")
        if not unique:
            print("  No interactive elements found. Try a different keyword.")

    elif command == "list":
        if len(sys.argv) < 3:
            print("Usage: python element_tools.py list <xpath>")
            print("  Lists all interactive elements in container")
            sys.exit(1)
        xpath = sys.argv[2]
        elements = list_interactive_in_container(dom, xpath)
        print(f"FOUND {len(elements)} interactive elements in '{xpath}':")
        for elem in elements[:15]:
            print(f"\n  {format_element_summary(elem)}")
            print(f"      xpath: {elem.get('xpath', 'N/A')}")
        if len(elements) > 15:
            print(f"\n  ... and {len(elements) - 15} more")

    elif command == "attr":
        if len(sys.argv) < 4:
            print("Usage: python element_tools.py attr <attribute> <value>")
            print("  attribute: class, aria-label, placeholder, id, role, etc.")
            sys.exit(1)
        attr = sys.argv[2]
        value = sys.argv[3]
        elements = search_by_attribute(dom, attr, value)
        print(f"FOUND {len(elements)} interactive elements with {attr} containing '{value}':")
        for elem in elements[:10]:
            print(f"\n  {format_element_summary(elem)}")
            print(f"      {attr}: {elem.get(attr, '')}")
            print(f"      xpath: {elem.get('xpath', 'N/A')}")
        if len(elements) > 10:
            print(f"\n  ... and {len(elements) - 10} more")

    elif command == "hint":
        if len(sys.argv) < 3:
            print("Usage: python element_tools.py hint <xpath>")
            print("  Analyzes xpath hint from recording, finds best interactive match")
            sys.exit(1)
        xpath = sys.argv[2]
        analysis = analyze_xpath_hint(dom, xpath)

        print(f"ANALYZING xpath hint: {xpath}")

        if analysis['exact_match']:
            em = analysis['exact_match']
            print(f"\n  Exact match found:")
            print(f"    interactive_index: {em['interactive_index']}")
            print(f"    tag: {em['tag']}")
            print(f"    text: {em['text']}")
            if em['interactive_index'] is not None:
                print(f"\n  ✓ Element is interactive, use index {em['interactive_index']}")
        else:
            print(f"\n  No exact match found")

        if analysis['levels_up'] > 0:
            print(f"\n  (Auto-searched {analysis['levels_up']} level(s) up)")

        if analysis['interactive_match'] and (not analysis['exact_match'] or analysis['exact_match'].get('interactive_index') is None):
            im = analysis['interactive_match']
            print(f"\n  BEST INTERACTIVE MATCH:")
            print(f"    interactive_index: {im['interactive_index']}")
            print(f"    tag: {im['tag']}")
            print(f"    text: {im['text']}")
            if im.get('xpath'):
                print(f"    xpath: {im['xpath']}")

        if analysis['alternatives'] and len(analysis['alternatives']) > 1:
            print(f"\n  Other alternatives ({len(analysis['alternatives']) - 1}):")
            for i, alt in enumerate(analysis['alternatives'][1:5]):
                print(f"    [{i+1}] index={alt['interactive_index']} <{alt['tag']}> \"{alt['text']}\"")

    elif command == "print":
        if len(sys.argv) < 3:
            print("Usage: python element_tools.py print <xpath> [depth]")
            sys.exit(1)
        xpath = sys.argv[2]
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
        element = find_by_xpath_attr(dom, xpath)
        if element:
            print(print_element(element, max_depth=depth))
        else:
            print(f"Element not found: {xpath}")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
