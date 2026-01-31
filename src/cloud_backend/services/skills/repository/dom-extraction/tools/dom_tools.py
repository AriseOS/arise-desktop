"""
DOM Tools for extraction script generation.

These tools help Claude analyze and navigate DOM structures to generate
robust extraction scripts.

Supports eigent_browser's YAML-like snapshot format with [ref=eN] element references.

Usage:
    python dom_tools.py <command> [args...]

Commands:
    find <ref>                            - Find element by ref, show details
    find <json_refs>                      - Find multiple elements by refs
    search --text "..." [--role ...]      - Search elements by content
    search --role "link" [--has-href]     - Search elements by role
    links [--region "..."]                - List all links with their hrefs
    list --role "..." [--limit N]         - List elements by role

DOM Format:
    The new DOM format from eigent_browser consists of:
    1. snapshotText: YAML-like text with element refs like [ref=e1]
    2. elements: Dict mapping ref -> element info (name, role, href, etc.)

Example DOM:
    {
        "url": "https://example.com",
        "dom": {
            "snapshot_text": "- link \\"Product\\" [ref=e1] [cursor=pointer]",
            "elements_count": 100,
            "elements": {
                "e1": {"role": "link", "name": "Product", "href": "https://..."}
            }
        }
    }
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union


# =============================================================================
# Core Functions (can be imported by extraction scripts)
# =============================================================================

def find_by_ref(elements: Dict[str, Dict], ref: str) -> Optional[Dict]:
    """
    Find element by ref (e.g., "e1", "e52").

    Args:
        elements: Elements map from DOM (ref -> element info)
        ref: Element reference like "e1" or "e52"

    Returns:
        Element dict or None
    """
    # Normalize ref (remove 'e' prefix if not present in key)
    if ref not in elements and ref.startswith('e'):
        ref = ref[1:]
    if ref not in elements and not ref.startswith('e'):
        ref = 'e' + ref
    return elements.get(ref)


def get_all_links(elements: Dict[str, Dict]) -> List[Dict]:
    """
    Get all links from elements map.

    Args:
        elements: Elements map from DOM

    Returns:
        List of link elements with ref, name, href, role
    """
    links = []
    for ref, elem in elements.items():
        href = elem.get('href')
        if href:
            links.append({
                'ref': ref,
                'name': elem.get('name', ''),
                'href': href,
                'role': elem.get('role', ''),
                'tagName': elem.get('tagName', ''),
            })
    return links


def get_elements_by_role(elements: Dict[str, Dict], role: str) -> List[Dict]:
    """
    Get all elements with a specific role.

    Args:
        elements: Elements map from DOM
        role: Role to filter by (e.g., "link", "button", "heading")

    Returns:
        List of matching elements with ref
    """
    results = []
    for ref, elem in elements.items():
        if elem.get('role') == role:
            results.append({
                'ref': ref,
                **elem
            })
    return results


def search_by_text(elements: Dict[str, Dict], text: str, role: str = None) -> List[Dict]:
    """
    Search elements containing text.

    Args:
        elements: Elements map from DOM
        text: Text to search for (case-insensitive)
        role: Optional role filter

    Returns:
        List of matching elements with ref
    """
    text_lower = text.lower()
    results = []

    for ref, elem in elements.items():
        name = (elem.get('name') or '').lower()
        if text_lower in name:
            if role and elem.get('role') != role:
                continue
            results.append({
                'ref': ref,
                **elem
            })

    return results


def extract_links_from_region(
    snapshot_text: str,
    elements: Dict[str, Dict],
    region_name: str
) -> List[Dict]:
    """
    Extract links from a specific region in the snapshot.

    Args:
        snapshot_text: YAML-like snapshot text
        elements: Elements map from DOM
        region_name: Name of the region to extract from

    Returns:
        List of links with name and href
    """
    # Find the region in snapshot_text
    region_pattern = rf'region "{re.escape(region_name)}"'
    region_match = re.search(region_pattern, snapshot_text, re.IGNORECASE)

    if not region_match:
        return []

    # Extract content from this region
    rest_of_text = snapshot_text[region_match.end():]

    # Find refs in this region (until next region or end)
    next_region = re.search(r'\n\s*- (?:region|contentinfo|banner) "', rest_of_text)
    if next_region:
        region_content = rest_of_text[:next_region.start()]
    else:
        region_content = rest_of_text

    # Extract all refs from this region
    ref_pattern = r'\[ref=(e\d+)\]'
    refs = re.findall(ref_pattern, region_content)

    # Get link info for each ref
    links = []
    for ref in refs:
        elem = elements.get(ref, {})
        href = elem.get('href')
        if href:
            links.append({
                'ref': ref,
                'name': elem.get('name', ''),
                'href': href,
            })

    return links


def extract_list(
    elements: Dict[str, Dict],
    role: str = 'link',
    field_mapping: Dict[str, str] = None
) -> List[Dict]:
    """
    Extract list data from elements by role.

    Args:
        elements: Elements map from DOM
        role: Role to filter by (default: 'link')
        field_mapping: Optional mapping of {output_name: element_field}
            Default: {"name": "name", "url": "href"}

    Returns:
        List of extracted data dicts
    """
    if field_mapping is None:
        field_mapping = {"name": "name", "url": "href"}

    results = []
    for ref, elem in elements.items():
        if elem.get('role') != role:
            continue

        item = {'ref': ref}
        for output_name, elem_field in field_mapping.items():
            item[output_name] = elem.get(elem_field, '')

        # Only add if at least one mapped field has value
        if any(item.get(k) for k in field_mapping.keys()):
            results.append(item)

    return results


def extract_single(elements: Dict[str, Dict], ref: str, field: str = 'name') -> Optional[str]:
    """Extract a single field from an element by ref."""
    elem = find_by_ref(elements, ref)
    if elem:
        return elem.get(field)
    return None


def extract_multi(
    elements: Dict[str, Dict],
    ref_mapping: Dict[str, str],
    field: str = 'name'
) -> Dict[str, Optional[str]]:
    """
    Extract multiple fields from different refs.

    Args:
        elements: Elements map from DOM
        ref_mapping: Dict of {output_name: ref}
        field: Field to extract from each element (default: name)

    Returns:
        Dict of {output_name: value}
    """
    result = {}
    for name, ref in ref_mapping.items():
        result[name] = extract_single(elements, ref, field)
    return result


# =============================================================================
# Snapshot Text Parsing
# =============================================================================

def parse_snapshot_line(line: str) -> Optional[Dict]:
    """
    Parse a single line from snapshot text.

    Args:
        line: Line like '- link "Product Name" [ref=e1] [cursor=pointer]'

    Returns:
        Dict with role, name, ref, and attributes
    """
    # Pattern: - role "name" [ref=eN] [attr1] [attr2]...
    pattern = r'^\s*-\s+(\w+)\s+"([^"]*)"\s*(?:\[level=(\d+)\])?\s*\[ref=(e\d+)\](.*)$'
    match = re.match(pattern, line)

    if not match:
        return None

    role = match.group(1)
    name = match.group(2)
    level = match.group(3)
    ref = match.group(4)
    attrs_str = match.group(5)

    # Parse additional attributes
    attrs = {}
    if level:
        attrs['level'] = int(level)

    attr_pattern = r'\[([^\]]+)\]'
    for attr_match in re.finditer(attr_pattern, attrs_str):
        attr = attr_match.group(1)
        if '=' in attr:
            key, value = attr.split('=', 1)
            attrs[key] = value
        else:
            attrs[attr] = True

    return {
        'role': role,
        'name': name,
        'ref': ref,
        'attrs': attrs,
    }


def parse_snapshot_text(snapshot_text: str) -> List[Dict]:
    """
    Parse entire snapshot text into list of elements.

    Args:
        snapshot_text: YAML-like snapshot text

    Returns:
        List of parsed elements
    """
    elements = []
    for line in snapshot_text.split('\n'):
        parsed = parse_snapshot_line(line)
        if parsed:
            elements.append(parsed)
    return elements


def get_elements_in_snapshot(snapshot_text: str, elements: Dict[str, Dict]) -> List[Dict]:
    """
    Get ordered list of elements as they appear in snapshot.

    Args:
        snapshot_text: YAML-like snapshot text
        elements: Elements map from DOM

    Returns:
        List of elements in snapshot order with full info
    """
    parsed = parse_snapshot_text(snapshot_text)
    result = []

    for p in parsed:
        ref = p['ref']
        elem_info = elements.get(ref, {})
        result.append({
            'ref': ref,
            'role': p['role'],
            'name': p['name'],
            'attrs': p['attrs'],
            **elem_info
        })

    return result


# =============================================================================
# Helper Functions
# =============================================================================

def load_dom(file_path: str = "dom_data.json") -> tuple:
    """Load DOM from JSON file.

    DOM files use wrapped format: {"url": "...", "dom": {...}}

    Returns:
        Tuple of (elements_dict, snapshot_text, page_url)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if "dom" not in data:
        raise ValueError(f"Invalid DOM format: missing 'dom' key.")

    dom = data["dom"]
    page_url = data.get("url", dom.get("url", ""))

    # Handle both old and new format
    # New format: elements is a dict in dom
    # Old format: might have snapshot_text as string
    elements = dom.get("elements", {})
    snapshot_text = dom.get("snapshot_text", "")

    return elements, snapshot_text, page_url


def truncate_text(text: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + '...'


# =============================================================================
# CLI Interface
# =============================================================================

def cmd_find(elements: Dict, snapshot_text: str, args: List[str]):
    """Handle find command."""
    if not args:
        print("Usage: python dom_tools.py find <ref>")
        print("       python dom_tools.py find '<json_refs>'")
        sys.exit(1)

    ref_arg = args[0]

    # Check if it's JSON (multiple refs)
    if ref_arg.startswith('{'):
        try:
            ref_mapping = json.loads(ref_arg)
        except json.JSONDecodeError:
            print(f"✗ Invalid JSON: {ref_arg}")
            sys.exit(1)

        for name, ref in ref_mapping.items():
            elem = find_by_ref(elements, ref)
            print(f"\n{'='*60}")
            print(f"Field: {name}")
            print(f"Ref: {ref}")

            if not elem:
                print(f"  ✗ Not found")
                continue

            print(f"  role: {elem.get('role', 'N/A')}")
            print(f"  name: \"{truncate_text(elem.get('name', ''), 80)}\"")
            if elem.get('href'):
                print(f"  href: {elem.get('href')}")
            if elem.get('tagName'):
                print(f"  tagName: {elem.get('tagName')}")
    else:
        # Single ref
        elem = find_by_ref(elements, ref_arg)
        if not elem:
            print(f"✗ Element not found: {ref_arg}")
            return

        print(f"✓ Found: {ref_arg}")
        print(f"  role: {elem.get('role', 'N/A')}")
        print(f"  name: \"{elem.get('name', '')}\"")
        print(f"  tagName: {elem.get('tagName', 'N/A')}")
        if elem.get('href'):
            print(f"  href: {elem.get('href')}")
        if elem.get('value'):
            print(f"  value: {elem.get('value')}")

        # Show code snippet
        print("\n# Code snippet:")
        print(f"from dom_tools import extract_single")
        print(f"result = extract_single(elements, \"{ref_arg}\", 'name')")


def cmd_search(elements: Dict, snapshot_text: str, args: List[str]):
    """Handle search command."""
    if not args:
        print("Usage: python dom_tools.py search --text \"...\" [--role ...]")
        print("       python dom_tools.py search --role \"link\" [--has-href]")
        sys.exit(1)

    text = None
    role = None
    has_href = False

    # Parse arguments
    i = 0
    while i < len(args):
        if args[i] == '--text' and i + 1 < len(args):
            text = args[i + 1]
            i += 2
        elif args[i] == '--role' and i + 1 < len(args):
            role = args[i + 1]
            i += 2
        elif args[i] == '--has-href':
            has_href = True
            i += 1
        else:
            i += 1

    results = []

    if text:
        results = search_by_text(elements, text, role)
        print(f"✓ Found {len(results)} elements containing \"{text}\":")
    elif role:
        results = get_elements_by_role(elements, role)
        if has_href:
            results = [r for r in results if r.get('href')]
        print(f"✓ Found {len(results)} elements with role=\"{role}\"" +
              (" (with href)" if has_href else "") + ":")
    else:
        print("✗ Please specify --text or --role")
        return

    for i, elem in enumerate(results[:10]):
        ref = elem.get('ref', 'N/A')
        name = truncate_text(elem.get('name', ''), 50)
        print(f"\n  [{i+1}] ref={ref}")
        print(f"      role: {elem.get('role', 'N/A')}, name: \"{name}\"")
        if elem.get('href'):
            print(f"      href: {elem.get('href')}")

    if len(results) > 10:
        print(f"\n  ... and {len(results) - 10} more")


def cmd_links(elements: Dict, snapshot_text: str, args: List[str]):
    """Handle links command - list all links with hrefs."""
    region = None

    # Parse arguments
    i = 0
    while i < len(args):
        if args[i] == '--region' and i + 1 < len(args):
            region = args[i + 1]
            i += 2
        else:
            i += 1

    if region:
        links = extract_links_from_region(snapshot_text, elements, region)
        print(f"✓ Found {len(links)} links in region \"{region}\":")
    else:
        links = get_all_links(elements)
        print(f"✓ Found {len(links)} links on page:")

    for i, link in enumerate(links[:20]):
        name = truncate_text(link.get('name', ''), 40)
        href = link.get('href', '')
        print(f"  [{link['ref']}] \"{name}\" -> {href}")

    if len(links) > 20:
        print(f"\n  ... and {len(links) - 20} more")

    # Code snippet
    print("\n# Code snippet:")
    if region:
        print(f"from dom_tools import extract_links_from_region")
        print(f"links = extract_links_from_region(snapshot_text, elements, \"{region}\")")
    else:
        print(f"from dom_tools import get_all_links")
        print(f"links = get_all_links(elements)")


def cmd_list(elements: Dict, snapshot_text: str, args: List[str]):
    """Handle list command - list elements by role."""
    role = None
    limit = 10

    # Parse arguments
    i = 0
    while i < len(args):
        if args[i] == '--role' and i + 1 < len(args):
            role = args[i + 1]
            i += 2
        elif args[i] == '--limit' and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        else:
            i += 1

    if not role:
        print("Usage: python dom_tools.py list --role \"link\" [--limit N]")
        return

    results = extract_list(elements, role)
    print(f"✓ Found {len(results)} elements with role=\"{role}\":")

    for i, item in enumerate(results[:limit]):
        print(f"  [{i+1}] {json.dumps(item, ensure_ascii=False)}")

    if len(results) > limit:
        print(f"\n  ... and {len(results) - limit} more")

    # Code snippet
    print("\n# Code snippet:")
    print(f"from dom_tools import extract_list")
    print(f"results = extract_list(elements, '{role}')")


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

    elements, snapshot_text, page_url = load_dom(dom_file)

    if command == "find":
        cmd_find(elements, snapshot_text, args)
    elif command == "search":
        cmd_search(elements, snapshot_text, args)
    elif command == "links":
        cmd_links(elements, snapshot_text, args)
    elif command == "list":
        cmd_list(elements, snapshot_text, args)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
