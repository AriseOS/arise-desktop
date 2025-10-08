"""DOM Data Extractor for Scraping Purposes

This module provides enhanced DOM data extraction functionality specifically
designed for web scraping scenarios. It extracts more detailed information
than the standard llm_representation() method, including href links and 
other attributes useful for generating scraping scripts.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

# Import browser-use data structures
from browser_use.dom.views import (
    NodeType, 
    SimplifiedNode, 
    SerializedDOMState,
    DOMSelectorMap,
    EnhancedDOMTreeNode
)
from browser_use.dom.serializer.clickable_elements import ClickableElementDetector

logger = logging.getLogger(__name__)

# Replicate constants from browser-use
DISABLED_ELEMENTS = {'style', 'script', 'head', 'meta', 'link', 'title'}


class DOMExtractor:
    """Enhanced DOM data extractor for scraping purposes"""
    
    def __init__(self):
        pass
    
    
    


    def serialize_accessible_elements_custom(self, enhanced_dom: EnhancedDOMTreeNode, include_non_visible: bool = False) -> Tuple[SerializedDOMState, Dict[str, float]]:
        """Custom implementation of serialize_accessible_elements logic
        
        Args:
            enhanced_dom: The enhanced DOM tree node from browser-use
            include_non_visible: If True, includes non-visible elements by treating all elements as visible
            
        Returns:
            Tuple of (SerializedDOMState, timing_info)
        """
        import time
        
        start_total = time.time()
        
        # Reset state
        self._interactive_counter = 1
        self._selector_map: DOMSelectorMap = {}
        self._clickable_cache = {}
        self._include_non_visible = include_non_visible  # Store the parameter for use in helper methods
        timing_info = {}
        
        # Step 1: Create simplified tree
        start_step1 = time.time()
        simplified_tree = self._create_simplified_tree(enhanced_dom)
        end_step1 = time.time()
        timing_info['create_simplified_tree'] = end_step1 - start_step1
        
        # Step 2: Optimize tree
        start_step2 = time.time()
        optimized_tree = self._optimize_tree(simplified_tree)
        end_step2 = time.time()
        timing_info['optimize_tree'] = end_step2 - start_step2
        
        # Step 3: Assign interactive indices
        start_step3 = time.time()
        self._assign_interactive_indices_and_mark_new_nodes(optimized_tree)
        end_step3 = time.time()
        timing_info['assign_interactive_indices'] = end_step3 - start_step3
        
        end_total = time.time()
        timing_info['serialize_accessible_elements_total'] = end_total - start_total
        
        return SerializedDOMState(_root=optimized_tree, selector_map=self._selector_map), timing_info
    
    def _create_simplified_tree(self, node: EnhancedDOMTreeNode) -> SimplifiedNode | None:
        """Create simplified tree - Step 1 of serialization"""
        try:
            if node.node_type == NodeType.DOCUMENT_NODE:
                for child in getattr(node, 'children_and_shadow_roots', []):
                    simplified_child = self._create_simplified_tree(child)
                    if simplified_child:
                        return simplified_child
                return None
                
            if node.node_type == NodeType.DOCUMENT_FRAGMENT_NODE:
                simplified = SimplifiedNode(original_node=node, children=[])
                for child in getattr(node, 'children_and_shadow_roots', []):
                    simplified_child = self._create_simplified_tree(child)
                    if simplified_child:
                        simplified.children.append(simplified_child)
                return simplified
                
            elif node.node_type == NodeType.ELEMENT_NODE:
                if node.node_name.lower() in DISABLED_ELEMENTS:
                    return None
                    
                if node.node_name == 'IFRAME':
                    if getattr(node, 'content_document', None):
                        simplified = SimplifiedNode(original_node=node, children=[])
                        for child in node.content_document.children:
                            simplified_child = self._create_simplified_tree(child)
                            if simplified_child:
                                simplified.children.append(simplified_child)
                        return simplified
                
                
                # Get visibility (follow browser-use official logic)
                original_is_visible = getattr(node, 'is_visible', False)
                # Override visibility if include_non_visible is True
                is_visible = True if getattr(self, '_include_non_visible', False) else original_is_visible
                is_scrollable = getattr(node, 'is_actually_scrollable', False)
                has_shadow_content = bool(getattr(node, 'children_and_shadow_roots', []))

                # Enhanced shadow DOM detection (follow browser-use official logic)
                is_shadow_host = any(
                    child.node_type == NodeType.DOCUMENT_FRAGMENT_NODE
                    for child in getattr(node, 'children_and_shadow_roots', [])
                )

                # Override visibility for elements with validation attributes (follow browser-use)
                if not is_visible and node.attributes:
                    has_validation_attrs = any(
                        attr.startswith(('aria-', 'pseudo'))
                        for attr in node.attributes.keys()
                    )
                    if has_validation_attrs:
                        is_visible = True

                # Include if visible, scrollable, has children, or is shadow host (follow browser-use)
                # Note: Don't check is_interactive here - that's done in _assign_interactive_indices
                should_include = is_visible or is_scrollable or has_shadow_content or is_shadow_host

                if should_include:
                    simplified = SimplifiedNode(original_node=node, children=[])

                    for child in getattr(node, 'children_and_shadow_roots', []):
                        simplified_child = self._create_simplified_tree(child)
                        if simplified_child:
                            simplified.children.append(simplified_child)

                    # Return if meaningful or has meaningful children (follow browser-use)
                    if is_visible or is_scrollable or simplified.children:
                        return simplified
                        
            elif node.node_type == NodeType.TEXT_NODE:
                # Get visibility (follow browser-use official logic)
                original_is_visible = node.snapshot_node and node.is_visible
                # Override visibility if include_non_visible is True
                is_visible = True if getattr(self, '_include_non_visible', False) else original_is_visible
                if (is_visible and getattr(node, 'node_value', None) and
                    node.node_value.strip() and len(node.node_value.strip()) > 1):
                    return SimplifiedNode(original_node=node, children=[])
            
            return None
            
        except Exception as e:
            logger.error(f"Error in _create_simplified_tree: {e}")
            return None
    
    def _optimize_tree(self, node: SimplifiedNode | None) -> SimplifiedNode | None:
        """Optimize tree structure - Step 2 of serialization"""
        try:
            if not node:
                return None
            
            optimized_children = []
            for child in node.children:
                optimized_child = self._optimize_tree(child)
                if optimized_child:
                    optimized_children.append(optimized_child)
            node.children = optimized_children
            
            # Get visibility (follow browser-use official logic)
            original_is_visible = node.original_node.snapshot_node and node.original_node.is_visible
            # Override visibility if include_non_visible is True
            is_visible = True if getattr(self, '_include_non_visible', False) else original_is_visible

            # Keep meaningful nodes (follow browser-use official logic)
            # Note: Don't check is_interactive here - that's done in _assign_interactive_indices
            if (is_visible or
                node.original_node.is_actually_scrollable or
                node.original_node.node_type == NodeType.TEXT_NODE or
                node.children):
                return node
            
            return None
            
        except Exception as e:
            logger.error(f"Error in _optimize_tree: {e}")
            return node
    
    def _assign_interactive_indices_and_mark_new_nodes(self, node: SimplifiedNode | None) -> None:
        """Assign interactive indices - Step 3 of serialization"""
        try:
            if not node:
                return
            
            if not (hasattr(node, 'excluded_by_parent') and node.excluded_by_parent):
                is_interactive_assign = self._is_interactive_cached(node.original_node)
                # Override visibility if include_non_visible is True
                original_is_visible = (getattr(node.original_node, 'snapshot_node', None) and 
                                     getattr(node.original_node, 'is_visible', False))
                is_visible = True if getattr(self, '_include_non_visible', False) else original_is_visible
                
                if is_interactive_assign and is_visible:
                    node.interactive_index = self._interactive_counter
                    node.original_node.element_index = self._interactive_counter
                    self._selector_map[self._interactive_counter] = node.original_node
                    self._interactive_counter += 1
            
            for child in node.children:
                self._assign_interactive_indices_and_mark_new_nodes(child)
                
        except Exception as e:
            logger.error(f"Error in _assign_interactive_indices_and_mark_new_nodes: {e}")
    
    def _is_interactive_cached(self, node: EnhancedDOMTreeNode) -> bool:
        """Cached interactive element detection"""
        try:
            if not hasattr(node, 'node_id'):
                return False
                
            if node.node_id not in self._clickable_cache:
                self._clickable_cache[node.node_id] = ClickableElementDetector.is_interactive(node)
            
            return self._clickable_cache[node.node_id]
            
        except Exception as e:
            logger.error(f"Error in _is_interactive_cached: {e}")
            return False

    def extract_dom_dict(self, serialized_dom) -> Dict:
        """Extract DOM structure as simplified Python dictionary
        
        Uses layered filtering strategy:
        - Content elements: Keep full information for precise targeting  
        - Container elements: Only keep tag + children to reduce noise
        
        Args:
            serialized_dom: SerializedDOM object (from any source)
            
        Returns:
            Dict: Simplified nested dictionary structure optimized for both human and LLM consumption
        """
        try:
            # Check if DOM is valid
            if not hasattr(serialized_dom, '_root') or not serialized_dom._root:
                return {
                    "tag": "empty", 
                    "text": "Empty DOM tree (you might have to wait for the page to load)"
                }
            
            # No need for xpath precomputation - we'll calculate on demand
            
            # First generate complete DOM dictionary
            full_dict = self._serialize_tree_to_dict(serialized_dom._root, depth=0, parent_structural_path="", parent_xpath="")
            
            # Then apply layered filtering for consistency between human and LLM views
            simplified_dict = self._apply_layered_filtering(full_dict)
            
            return simplified_dict
            
        except Exception as e:
            logger.error(f"Error extracting DOM dict: {e}")
            return {
                "tag": "error",
                "text": f"Error extracting DOM dict: {str(e)}"
            }
    
    def _serialize_tree_to_dict(self, node, depth: int = 0, parent_structural_path: str = "", parent_xpath: str = "") -> Dict:
        """Serialize tree to simplified dict format (matching llm_representation style)"""
        if not node:
            return None
        
        # Skip rendering excluded nodes, but process their children
        if hasattr(node, 'excluded_by_parent') and node.excluded_by_parent:
            children_dicts = []
            for child in node.children:
                child_dict = self._serialize_tree_to_dict(child, depth, parent_structural_path, parent_xpath)
                if child_dict:
                    children_dicts.append(child_dict)
            # Return children as flat list or first child
            return {"children": children_dicts} if len(children_dicts) > 1 else (children_dicts[0] if children_dicts else None)
        
        # Initialize empty node structure - will only add keys with actual content
        node_dict = {}
        
        if node.original_node.node_type == NodeType.ELEMENT_NODE:
            # Skip displaying nodes marked as should_display=False
            if hasattr(node, 'should_display') and not node.should_display:
                children_dicts = []
                for child in node.children:
                    child_dict = self._serialize_tree_to_dict(child, depth, parent_structural_path, parent_xpath)
                    if child_dict:
                        children_dicts.append(child_dict)
                # Return children as flat list or first child
                return {"children": children_dicts} if len(children_dicts) > 1 else (children_dicts[0] if children_dicts else None)
            
            # Only set tag if it exists and is not empty
            tag_name = node.original_node.tag_name.lower() if node.original_node.tag_name else ""
            if tag_name:
                node_dict["tag"] = tag_name
            
            # Calculate xpath in top-down manner (much more efficient)
            current_xpath = self._build_xpath_top_down(node.original_node, parent_xpath, tag_name)
            if current_xpath:
                node_dict["xpath"] = current_xpath
            
            # Generate structural path (similar to xpath format but simplified)
            current_structural_path = self._build_structural_path(node, parent_structural_path, tag_name)
            if current_structural_path:
                node_dict["structural_path"] = current_structural_path
            
            # Add node identification information (no expensive calculations)
            node_dict["node_id"] = node.original_node.node_id
            if hasattr(node.original_node, 'backend_node_id'):
                node_dict["backend_node_id"] = node.original_node.backend_node_id
            
            # Extract useful attributes from the element
            if (hasattr(node.original_node, 'attributes') and 
                node.original_node.attributes):
                
                # Common useful attributes for data extraction
                useful_attributes = {
                    'id': 'id',
                    'class': 'class',
                    'href': 'href', 
                    'src': 'src',
                    'alt': 'alt',
                    'title': 'title',
                    'name': 'name',
                    'value': 'value',
                    'type': 'type',
                    'role': 'role',
                    'aria-label': 'aria_label',
                    'aria-labelledby': 'aria_labelledby',
                    'aria-describedby': 'aria_describedby',
                    'data-testid': 'data_testid',
                    'data-id': 'data_id',
                    'data-value': 'data_value',
                    'data-action': 'data_action',
                    'placeholder': 'placeholder',
                    'rel': 'rel',
                    'target': 'target'
                }
                
                for attr_name, dict_key in useful_attributes.items():
                    if (attr_name in node.original_node.attributes and 
                        node.original_node.attributes[attr_name]):
                        node_dict[dict_key] = node.original_node.attributes[attr_name]
            
            # Add element state information (现成可用，无需计算)
            if hasattr(node.original_node, 'is_visible') and node.original_node.is_visible is not None:
                node_dict["is_visible"] = node.original_node.is_visible
            
            if hasattr(node.original_node, 'is_scrollable') and node.original_node.is_scrollable is not None:
                node_dict["is_scrollable"] = node.original_node.is_scrollable
            
            # Add position information if available (现成可用)
            if (hasattr(node.original_node, 'absolute_position') and 
                node.original_node.absolute_position is not None):
                pos = node.original_node.absolute_position
                node_dict["position"] = {
                    "x": pos.x,
                    "y": pos.y, 
                    "width": pos.width,
                    "height": pos.height
                }
            
            # Only add interactive index if present
            if hasattr(node, 'interactive_index') and node.interactive_index is not None:
                node_dict["interactive_index"] = node.interactive_index
            
            # Collect text content from direct TEXT_NODE children and merge into this element
            direct_text_parts = []
            element_children = []
            
            for child in node.children:
                if child.original_node.node_type == NodeType.TEXT_NODE:
                    # Check if text content is meaningful (not just whitespace)
                    is_visible = (getattr(child.original_node, 'snapshot_node', None) and 
                                 getattr(child.original_node, 'is_visible', False))
                    if (is_visible and 
                        getattr(child.original_node, 'node_value', None) and
                        child.original_node.node_value.strip()):
                        text_content = child.original_node.node_value.strip()
                        # Only add non-empty text that's not just whitespace/newlines
                        if text_content and len(text_content) > 1:
                            direct_text_parts.append(text_content)
                else:
                    # This is an element child, process it recursively
                    element_children.append(child)
            
            # Add text content to element if any meaningful text found
            if direct_text_parts:
                node_dict["text"] = " ".join(direct_text_parts)
            
            # Process element children (skip TEXT_NODE children as they're already processed above)
            children_dicts = []
            for child in element_children:
                child_dict = self._serialize_tree_to_dict(child, depth + 1, current_structural_path, current_xpath)
                if child_dict:
                    children_dicts.append(child_dict)
            
            if children_dicts:
                node_dict["children"] = children_dicts
        
        elif node.original_node.node_type == NodeType.TEXT_NODE:
            # TEXT_NODE is now processed by parent ELEMENT_NODE, so we skip individual text nodes
            return None
        
        # Only return node if it has any content
        return node_dict if node_dict else None
    
    

    def _build_xpath_top_down(self, node: EnhancedDOMTreeNode, parent_xpath: str, tag_name: str) -> str:
        """Build relative xpath in top-down manner (one-pass, very efficient)"""
        if not tag_name:
            return parent_xpath
        
        # Check if this element has an ID - use ID-based relative xpath
        if hasattr(node, 'attributes') and node.attributes:
            element_id = node.attributes.get('id')
            if element_id and element_id.strip():
                return f'//*[@id="{element_id}"]'
        
        # Calculate position among siblings with same tag name (browser-use style)
        position = self._get_element_position_in_original_dom(node, tag_name)
        
        # Build current xpath segment
        xpath_segment = tag_name
        if position > 0:  # Only add index if needed (multiple siblings)
            xpath_segment += f"[{position}]"
        
        # Generate relative xpath format
        if not parent_xpath:
            return f"//{xpath_segment}"  # Root element with // prefix
        elif parent_xpath.startswith("//"):
            return f"{parent_xpath}/{xpath_segment}"  # Continue relative path
        else:
            return f"//{xpath_segment}"  # Ensure relative format
    
    def _get_element_position_in_original_dom(self, element: EnhancedDOMTreeNode, tag_name: str) -> int:
        """Get position using browser-use logic - returns 0 if only element, otherwise 1-based index"""
        if not hasattr(element, 'parent_node') or not element.parent_node:
            return 0
        
        parent = element.parent_node
        if not hasattr(parent, 'children_nodes') or not parent.children_nodes:
            return 0

        # Find all siblings with same tag name (based on original DOM structure)
        same_tag_siblings = [
            child
            for child in parent.children_nodes
            if (child.node_type == NodeType.ELEMENT_NODE and 
                hasattr(child, 'node_name') and
                child.node_name and
                child.node_name.lower() == tag_name)
        ]

        if len(same_tag_siblings) <= 1:
            return 0  # No index needed if it's the only one

        try:
            # XPath is 1-indexed
            position = same_tag_siblings.index(element) + 1
            return position
        except ValueError:
            return 0


    
    def _build_structural_path(self, node, parent_path: str, tag_name: str) -> str:
        """Build structural path with semantic information (different from xpath)"""
        if not tag_name:
            return parent_path
            
        # Build current element selector with semantic meaning
        element_selector = tag_name
        
        # Add meaningful identifiers that provide semantic context
        if (hasattr(node.original_node, 'attributes') and 
            node.original_node.attributes):
            
            attrs = node.original_node.attributes
            
            # Priority 1: ID (most stable and meaningful)
            if 'id' in attrs and attrs['id']:
                element_selector += f"#{attrs['id']}"
            
            # Priority 2: CSS classes (keep all classes for precision)
            elif 'class' in attrs and attrs['class']:
                # Use the first class as primary identifier, but keep all for context
                classes = attrs['class'].split()
                if classes:
                    # Add first class as main selector
                    element_selector += f".{classes[0]}"
                    # If there are multiple significant classes, add them too
                    if len(classes) > 1:
                        # Add up to 2 more classes for better precision
                        additional_classes = classes[1:3]
                        for cls in additional_classes:
                            if len(cls) > 2:  # Skip very short classes
                                element_selector += f".{cls}"
            
            # Priority 3: Data attributes for identification
            elif any(key.startswith('data-testid') for key in attrs):
                for key, value in attrs.items():
                    if key.startswith('data-testid') and value:
                        element_selector += f"[data-testid='{value}']"
                        break
            
            # Priority 4: Role or type attributes (semantic meaning)
            elif attrs.get('role') or attrs.get('type'):
                role_or_type = attrs.get('role') or attrs.get('type')
                element_selector += f"[{attrs.get('role') and 'role' or 'type'}='{role_or_type}']"
        
        # Combine with parent path
        if parent_path:
            return f"{parent_path}>{element_selector}"
        else:
            return element_selector
    
    def _extract_stable_classes(self, class_string: str) -> list:
        """Extract stable CSS classes (avoid auto-generated ones)"""
        classes = class_string.split()
        stable_classes = []
        
        for cls in classes:
            # Skip classes that look auto-generated
            if (not self._is_generated_class(cls) and 
                len(cls) > 2 and  # Skip very short classes
                not cls.isdigit()):  # Skip pure numeric classes
                stable_classes.append(cls)
        
        return stable_classes
    
    def _is_generated_class(self, class_name: str) -> bool:
        """Check if class name appears to be auto-generated"""
        # Common patterns for auto-generated classes
        generated_patterns = [
            # Random strings like: m389_6m, mwdn_1_m
            lambda x: len([c for c in x if c.isdigit()]) > len(x) / 3,
            # Very short random strings
            lambda x: len(x) <= 3 and any(c.isdigit() for c in x),
            # Hash-like patterns
            lambda x: len(x) > 8 and all(c in '0123456789abcdef' for c in x.lower()),
            # CSS-in-JS patterns like: _77895_3emTY
            lambda x: x.count('_') >= 2 and any(c.isdigit() for c in x)
        ]
        
        return any(pattern(class_name) for pattern in generated_patterns)

    def format_dict_as_text(self, dom_dict: Dict, depth: int = 0) -> str:
        """Format simplified dictionary structure as text (matching llm_representation output)"""
        if not dom_dict:
            return ""
        
        formatted_lines = []
        depth_str = depth * '\t'
        
        # Extract all relevant attributes
        tag = dom_dict.get("tag", "")
        text = dom_dict.get("text", "").strip()
        interactive_index = dom_dict.get("interactive_index")
        children = dom_dict.get("children", [])
        
        # Collect attributes to display
        attrs_to_show = []
        attr_keys = ["id", "class", "href", "src", "alt", "title", "name", "value", "type", "role", 
                    "data_testid", "data_id", "placeholder"]
        for attr_key in attr_keys:
            if attr_key in dom_dict and dom_dict[attr_key]:
                attrs_to_show.append(f'{attr_key}={dom_dict[attr_key]}')
        
        # Add position info if available
        if "position" in dom_dict and dom_dict["position"]:
            pos = dom_dict["position"]
            attrs_to_show.append(f'pos=({pos["x"]:.0f},{pos["y"]:.0f},{pos["width"]:.0f}x{pos["height"]:.0f})')
        
        # Add visibility info
        if "is_visible" in dom_dict:
            attrs_to_show.append(f'visible={dom_dict["is_visible"]}')
        
        if tag == "empty":
            return text
        elif tag == "error":
            return text
        elif tag == "text":
            # Text node - just output the text
            if text:
                formatted_lines.append(f'{depth_str}{text}')
        else:
            # Element node
            if interactive_index is not None or tag == 'iframe':
                # Build the line like: [160]<hr />, [161]<a name=summaryonecolumn-container />
                line = depth_str
                
                if interactive_index is not None:
                    line += f'[{interactive_index}]<{tag.upper()}'
                elif tag == 'iframe':
                    line += f'|IFRAME|<{tag.upper()}'
                else:
                    line += f'<{tag.upper()}'
                
                # Add all collected attributes
                if attrs_to_show:
                    line += ' ' + ' '.join(attrs_to_show)
                
                line += ' />'
                formatted_lines.append(line)
                
                # Process children with increased depth
                for child in children:
                    child_text = self.format_dict_as_text(child, depth + 1)
                    if child_text:
                        formatted_lines.append(child_text)
            else:
                # Non-interactive elements, just process children
                for child in children:
                    child_text = self.format_dict_as_text(child, depth)
                    if child_text:
                        formatted_lines.append(child_text)
        
        return '\n'.join(formatted_lines)

    def extract_llm_view(self, dom_dict: Dict, include_xpath: bool = True) -> str:
        """Extract LLM view from already simplified DOM dictionary

        Since extract_dom_dict() now applies layered filtering, this method
        just converts the simplified dict to compact JSON format.

        Args:
            dom_dict: Simplified DOM dictionary from extract_dom_dict()
            include_xpath: If False, remove xpath fields to save tokens (default: True)

        Returns:
            str: Compact JSON string for LLM consumption
        """
        try:
            # Remove xpath if not needed
            if not include_xpath:
                dom_dict = self._remove_xpath_recursive(dom_dict)

            # DOM dict is already simplified by extract_dom_dict, just convert to JSON
            import json
            return json.dumps(dom_dict, separators=(',', ':'), ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error extracting LLM view: {e}")
            return "{}"

    def _remove_xpath_recursive(self, node: Dict) -> Dict:
        """Recursively remove xpath fields from DOM dict to save tokens

        Args:
            node: DOM node dictionary

        Returns:
            Dict: DOM dict without xpath fields
        """
        if not isinstance(node, dict):
            return node

        # Create a copy to avoid modifying original
        node = node.copy()

        # Remove xpath if present
        if 'xpath' in node:
            del node['xpath']

        # Recursively process children
        if 'children' in node and isinstance(node['children'], list):
            node['children'] = [self._remove_xpath_recursive(child) for child in node['children']]

        return node
    
    def _apply_layered_filtering(self, node):
        """Apply layered filtering: full info for content elements, minimal for containers
        
        Args:
            node: DOM node dictionary
            
        Returns:
            Dict: Filtered node dictionary
        """
        if not isinstance(node, dict):
            return node
            
        # Check if this element contains meaningful content
        is_content = self._is_content_element(node)
        
        if is_content:
            # Content element: keep all important fields for precise targeting
            result = self._extract_content_fields(node)
        else:
            # Container element: only keep basic structure
            result = {"tag": node["tag"]} if "tag" in node else {}
        
        # Process children recursively
        if "children" in node and node["children"]:
            result["children"] = [self._apply_layered_filtering(child) for child in node["children"]]
            
        return result
    
    def _is_content_element(self, node: Dict) -> bool:
        """Check if element has meaningful content that needs full representation
        
        Content elements include:
        - Elements with text content
        - Interactive elements
        - Elements with important attributes (href, src, etc.)
        - Important semantic tags
        
        Args:
            node: DOM node dictionary
            
        Returns:
            bool: True if element should keep full information
        """
        # Has text content
        if node.get("text") and node["text"].strip():
            return True
            
        # Has interactive index (clickable/operable)
        if "interactive_index" in node:
            return True
            
        # Has important attributes
        important_attrs = ["href", "src", "alt", "value", "placeholder"]
        if any(node.get(attr) for attr in important_attrs):
            return True
            
        # Important semantic tags (always content even if empty)
        content_tags = {"img", "input", "button", "a", "select", "textarea", "h1", "h2", "h3", "h4", "h5", "h6", "p", "label"}
        if node.get("tag") in content_tags:
            return True
            
        return False
    
    def _extract_content_fields(self, node: Dict) -> Dict:
        """Extract all important fields for content elements (no modification of values)
        
        Keep original values for precise targeting - do not simplify paths or classes.
        
        Args:
            node: DOM node dictionary
            
        Returns:
            Dict: Node with all important fields preserved
        """
        # Fields that are important for content elements
        content_fields = [
            # Basic identification
            "tag",
            # Content data
            "text", "href", "src", "alt", "title", "value", "placeholder",
            # Targeting information (keep original for precision)
            # "xpath", "structural_path", "id", "class",
            "id", "class",
            "xpath",
            # "structural_path",
            # Interactive information
            "interactive_index",
            # Other useful attributes
            # "type", "role", "name", "data_testid", "data_id", "data_action"
        ]
        
        result = {}
        for field in content_fields:
            if field in node and node[field] is not None:
                # Keep original values - no simplification
                result[field] = node[field]
                
        return result
    


# New simplified convenience functions
def extract_dom_dict(serialized_dom) -> Dict:
    """Extract DOM as nested dictionary with href support
    
    Args:
        serialized_dom: SerializedDOM object (from any source)
        
    Returns:
        Dict: Nested dictionary structure
    """
    extractor = DOMExtractor()
    return extractor.extract_dom_dict(serialized_dom)


def extract_llm_view(dom_dict: Dict, include_xpath: bool = True) -> str:
    """Extract simplified view for LLM from DOM dictionary

    Args:
        dom_dict: DOM dictionary from extract_dom_dict()
        include_xpath: If False, remove xpath fields to save tokens (default: True)

    Returns:
        str: Compact JSON string for LLM
    """
    extractor = DOMExtractor()
    return extractor.extract_llm_view(dom_dict, include_xpath=include_xpath)


def format_dict_as_text(dom_dict: Dict) -> str:
    """Format DOM dictionary as text (for debugging/validation)
    
    Args:
        dom_dict: DOM dictionary from extract_dom_dict()
        
    Returns:
        str: Human-readable text format
    """
    extractor = DOMExtractor()
    return extractor.format_dict_as_text(dom_dict)


