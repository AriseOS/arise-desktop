"""
MetaFlow data structures

Based on: docs/intent_builder/metaflow_specification.md
"""
import yaml
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from .operation import Operation, ElementInfo

# Operation and ElementInfo are now imported from operation.py - unified definitions


class MetaFlowNode(BaseModel):
    """Regular node in MetaFlow

    Represents a single intent with its operations and I/O.
    """
    id: str
    intent_id: str
    intent_name: str
    intent_description: str

    # Operations list
    operations: List[Operation]

    # Optional I/O
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, str]] = None

    class Config:
        populate_by_name = True


class LoopNode(BaseModel):
    """Loop node in MetaFlow

    Represents a foreach loop over a list of items.
    """
    id: str
    type: str = "loop"
    description: str

    # Loop configuration
    source: str  # Variable reference like "{{product_urls}}"
    item_var: str

    # Loop body
    children: List['MetaFlowNode']

    class Config:
        populate_by_name = True


class MetaFlow(BaseModel):
    """MetaFlow - Intent composition and orchestration

    Represents the execution logic to complete a task,
    including intent sequence, control flow, and data flow.
    """
    version: str = "1.0"
    task_description: str

    # Node list (can be regular nodes or loop nodes)
    nodes: List[Union[MetaFlowNode, LoopNode]]

    class Config:
        populate_by_name = True

    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'MetaFlow':
        """Load MetaFlow from YAML string"""
        data = yaml.safe_load(yaml_str)

        # Parse nodes (handle both MetaFlowNode and LoopNode)
        parsed_nodes = []
        for node_data in data.get('nodes', []):
            if node_data.get('type') == 'loop':
                # Parse loop node
                loop_node = LoopNode(**node_data)
                parsed_nodes.append(loop_node)
            else:
                # Parse regular node
                regular_node = MetaFlowNode(**node_data)
                parsed_nodes.append(regular_node)

        data['nodes'] = parsed_nodes
        return cls(**data)

    @classmethod
    def from_yaml_file(cls, file_path: str) -> 'MetaFlow':
        """Load MetaFlow from YAML file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_str = f.read()
        return cls.from_yaml(yaml_str)

    def to_yaml(self) -> str:
        """Convert MetaFlow to YAML string"""
        data = self.model_dump(by_alias=True, exclude_none=True)
        return yaml.dump(data, allow_unicode=True, sort_keys=False)

    def to_yaml_file(self, file_path: str):
        """Save MetaFlow to YAML file"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.to_yaml())

    def _infer_node_type(self, node: Union[MetaFlowNode, LoopNode]) -> str:
        """Infer visualization node type from operations"""
        if isinstance(node, LoopNode):
            return 'loop'

        operations = node.operations
        if not operations:
            return 'process'

        # Check operation types
        has_navigate = any(op.type == 'navigate' for op in operations)
        has_click = any(op.type == 'click' for op in operations)
        has_extract = any(op.type in ['extract', 'extract_data'] for op in operations)
        has_input = any(op.type in ['input', 'type'] for op in operations)
        has_select = any(op.type in ['select', 'copy_action'] for op in operations)

        # Infer type based on operations
        if has_extract or has_select:
            return 'extract'
        if has_navigate:
            return 'navigate'
        if has_click or has_input:
            return 'interact'

        return 'process'

    def to_visualization_json(self) -> Dict[str, Any]:
        """Convert MetaFlow to frontend visualization format

        Returns a JSON structure optimized for frontend rendering:
        - nodes: List of nodes with type, name, description
        - edges: List of connections between nodes
        - metadata: Additional information for rendering
        """
        viz_nodes = []
        viz_edges = []

        # Add start node
        viz_nodes.append({
            'id': 'start',
            'type': 'start',
            'name': 'Start',
            'description': self.task_description
        })

        # Process each node
        prev_node_id = 'start'
        for i, node in enumerate(self.nodes):
            if isinstance(node, LoopNode):
                # Loop node
                loop_node_data = {
                    'id': node.id,
                    'type': 'loop',
                    'name': f'Loop: {node.item_var}',
                    'description': node.description,
                    'properties': {
                        'source': node.source,
                        'item_var': node.item_var,
                        'children_count': len(node.children)
                    }
                }
                viz_nodes.append(loop_node_data)

                # Connect previous node to loop
                viz_edges.append({
                    'source': prev_node_id,
                    'target': node.id
                })

                # Process loop children
                prev_child_id = node.id
                for child in node.children:
                    child_node_data = {
                        'id': child.id,
                        'type': self._infer_node_type(child),
                        'name': child.intent_name,
                        'description': child.intent_description,
                        'properties': {
                            'intent_id': child.intent_id,
                            'operations_count': len(child.operations),
                            'parent_loop': node.id
                        }
                    }
                    viz_nodes.append(child_node_data)

                    # Connect within loop
                    viz_edges.append({
                        'source': prev_child_id,
                        'target': child.id
                    })
                    prev_child_id = child.id

                prev_node_id = prev_child_id

            else:
                # Regular node
                node_type = self._infer_node_type(node)
                node_data = {
                    'id': node.id,
                    'type': node_type,
                    'name': node.intent_name,
                    'description': node.intent_description,
                    'properties': {
                        'intent_id': node.intent_id,
                        'operations_count': len(node.operations)
                    }
                }

                # Add input/output info if exists
                if node.inputs:
                    node_data['properties']['inputs'] = node.inputs
                if node.outputs:
                    node_data['properties']['outputs'] = node.outputs

                viz_nodes.append(node_data)

                # Connect to previous node
                viz_edges.append({
                    'source': prev_node_id,
                    'target': node.id
                })

                prev_node_id = node.id

        # Add end node
        viz_nodes.append({
            'id': 'end',
            'type': 'end',
            'name': 'End',
            'description': 'Workflow completed successfully'
        })

        # Connect last node to end
        viz_edges.append({
            'source': prev_node_id,
            'target': 'end'
        })

        return {
            'task_description': self.task_description,
            'nodes': viz_nodes,
            'edges': viz_edges,
            'metadata': {
                'version': self.version,
                'total_nodes': len(self.nodes),
                'has_loops': any(isinstance(n, LoopNode) for n in self.nodes)
            }
        }


# Update forward references
LoopNode.model_rebuild()
MetaFlow.model_rebuild()
