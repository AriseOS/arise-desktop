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
                
                is_interactive = self._is_interactive_cached(node)
                # Override visibility if include_non_visible is True
                original_is_visible = getattr(node, 'snapshot_node', None) and getattr(node, 'is_visible', False)
                is_visible = True if getattr(self, '_include_non_visible', False) else original_is_visible
                is_scrollable = getattr(node, 'is_actually_scrollable', False)
                
                should_include = (is_interactive and is_visible) or is_scrollable or getattr(node, 'children_and_shadow_roots', [])
                
                if should_include:
                    simplified = SimplifiedNode(original_node=node, children=[])
                    
                    for child in getattr(node, 'children_and_shadow_roots', []):
                        simplified_child = self._create_simplified_tree(child)
                        if simplified_child:
                            simplified.children.append(simplified_child)
                    
                    if (is_interactive and is_visible) or is_scrollable or simplified.children:
                        return simplified
                        
            elif node.node_type == NodeType.TEXT_NODE:
                # Override visibility if include_non_visible is True
                original_is_visible = getattr(node, 'snapshot_node', None) and getattr(node, 'is_visible', False)
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
            
            is_interactive_opt = self._is_interactive_cached(node.original_node)
            # Override visibility if include_non_visible is True
            original_is_visible = (getattr(node.original_node, 'snapshot_node', None) and 
                                 getattr(node.original_node, 'is_visible', False))
            is_visible = True if getattr(self, '_include_non_visible', False) else original_is_visible
            
            if ((is_interactive_opt and is_visible) or
                getattr(node.original_node, 'is_actually_scrollable', False) or
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
        """Extract DOM structure as Python dictionary with href support
        
        Args:
            serialized_dom: SerializedDOM object (from any source)
            
        Returns:
            Dict: Nested dictionary structure with tag, text, href, interactive_index, children
        """
        try:
            # Check if DOM is valid
            if not hasattr(serialized_dom, '_root') or not serialized_dom._root:
                return {
                    "tag": "empty", 
                    "text": "Empty DOM tree (you might have to wait for the page to load)"
                }
            
            return self._serialize_tree_to_dict(serialized_dom._root, depth=0)
            
        except Exception as e:
            logger.error(f"Error extracting DOM dict: {e}")
            return {
                "tag": "error",
                "text": f"Error extracting DOM dict: {str(e)}"
            }
    
    def _serialize_tree_to_dict(self, node, depth: int = 0) -> Dict:
        """Serialize tree to simplified dict format (matching llm_representation style)"""
        if not node:
            return None
        
        # Skip rendering excluded nodes, but process their children
        if hasattr(node, 'excluded_by_parent') and node.excluded_by_parent:
            children_dicts = []
            for child in node.children:
                child_dict = self._serialize_tree_to_dict(child, depth)
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
                    child_dict = self._serialize_tree_to_dict(child, depth)
                    if child_dict:
                        children_dicts.append(child_dict)
                # Return children as flat list or first child
                return {"children": children_dicts} if len(children_dicts) > 1 else (children_dicts[0] if children_dicts else None)
            
            # Only set tag if it exists and is not empty
            tag_name = node.original_node.tag_name.lower() if node.original_node.tag_name else ""
            if tag_name:
                node_dict["tag"] = tag_name
            
            # Only extract href attribute if it exists and is not empty
            if (hasattr(node.original_node, 'attributes') and 
                node.original_node.attributes and 
                'href' in node.original_node.attributes and
                node.original_node.attributes['href']):
                node_dict["href"] = node.original_node.attributes['href']
            
            # Only add interactive index if present
            if hasattr(node, 'interactive_index') and node.interactive_index is not None:
                node_dict["interactive_index"] = node.interactive_index
        
        elif node.original_node.node_type == NodeType.TEXT_NODE:
            # Include visible text (like "Warunki oferty", "-6%")
            is_visible = (getattr(node.original_node, 'snapshot_node', None) and 
                         getattr(node.original_node, 'is_visible', False))
            if (is_visible and 
                getattr(node.original_node, 'node_value', None) and
                node.original_node.node_value.strip() and 
                len(node.original_node.node_value.strip()) > 1):
                
                node_dict["tag"] = "text"
                node_dict["text"] = node.original_node.node_value.strip()
        
        # Process children and only add children key if there are actual children
        children_dicts = []
        for child in node.children:
            child_dict = self._serialize_tree_to_dict(child, depth + 1)
            if child_dict:
                children_dicts.append(child_dict)
        
        if children_dicts:
            node_dict["children"] = children_dicts
        
        # Only return node if it has any content
        return node_dict if node_dict else None

    def format_dict_as_text(self, dom_dict: Dict, depth: int = 0) -> str:
        """Format simplified dictionary structure as text (matching llm_representation output)"""
        if not dom_dict:
            return ""
        
        formatted_lines = []
        depth_str = depth * '\t'
        
        # Use get() with empty string defaults, but keys might not exist
        tag = dom_dict.get("tag", "")
        text = dom_dict.get("text", "").strip()
        href = dom_dict.get("href", "")
        interactive_index = dom_dict.get("interactive_index")
        children = dom_dict.get("children", [])
        
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
                
                # Add href attribute if present (like: href=/oferta/...)
                if href:
                    line += f' href={href}'
                
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

    def extract_llm_view(self, dom_dict: Dict) -> str:
        """Extract simplified view for LLM (flattened meaningful nodes only)
        
        Args:
            dom_dict: Nested DOM dictionary from extract_dom_dict()
            
        Returns:
            str: Compact JSON string of meaningful nodes for LLM
        """
        try:
            meaningful_nodes = self._extract_meaningful_nodes(dom_dict)
            # Return compact JSON string
            import json
            return json.dumps(meaningful_nodes, separators=(',', ':'), ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Error extracting LLM view: {e}")
            return "[]"
    
    def _extract_meaningful_nodes(self, node) -> List[Dict]:
        """Extract meaningful nodes from nested DOM dict (interactive elements + text nodes)"""
        results = []
        
        def traverse(current_node):
            if not isinstance(current_node, dict):
                return
                
            # Collect interactive elements
            if "interactive_index" in current_node:
                node_info = {"interactive_index": current_node["interactive_index"]}
                if "tag" in current_node:
                    node_info["tag"] = current_node["tag"]
                if "href" in current_node:
                    node_info["href"] = current_node["href"]
                results.append(node_info)
            
            # Collect text nodes
            elif current_node.get("tag") == "text" and "text" in current_node:
                results.append({
                    "tag": "text", 
                    "text": current_node["text"]
                })
            
            # Recursively process children
            for child in current_node.get("children", []):
                traverse(child)
        
        traverse(node)
        return results


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


def extract_llm_view(dom_dict: Dict) -> str:
    """Extract simplified view for LLM from DOM dictionary
    
    Args:
        dom_dict: DOM dictionary from extract_dom_dict()
        
    Returns:
        str: Compact JSON string for LLM
    """
    extractor = DOMExtractor()
    return extractor.extract_llm_view(dom_dict)


def format_dict_as_text(dom_dict: Dict) -> str:
    """Format DOM dictionary as text (for debugging/validation)
    
    Args:
        dom_dict: DOM dictionary from extract_dom_dict()
        
    Returns:
        str: Human-readable text format
    """
    extractor = DOMExtractor()
    return extractor.format_dict_as_text(dom_dict)


