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


# Update forward references
LoopNode.model_rebuild()
MetaFlow.model_rebuild()
