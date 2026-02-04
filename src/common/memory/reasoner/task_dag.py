"""Task DAG - Directed Acyclic Graph for task decomposition."""

from typing import Any, Dict, List, Optional, Tuple


class TaskDAG:
    """Task DAG for decomposed tasks.

    Each task node in the DAG contains:
    - target: Target description
    - tool_type: Type of tool to use (e.g., "retrieval", "action", etc.)
    - tool_parameters: Parameters for the tool (optional)
    - dependencies: List of task IDs this task depends on
    """

    def __init__(
        self,
        dag_id: str,
        original_target: str,
        nodes: Dict[str, Dict[str, Any]],
        edges: List[Tuple[str, str]],
    ):
        """Initialize TaskDAG.

        Args:
            dag_id: Unique DAG identifier.
            original_target: Original target description.
            nodes: Dictionary of task nodes {task_id: task_data}.
                   Each node should have:
                   - target: str
                   - tool_type: str (default: "retrieval")
                   - tool_parameters: Dict[str, Any] (optional)
                   - dependencies: List[str] (optional)
            edges: List of dependency edges [(source_id, target_id)].
        """
        self.dag_id = dag_id
        self.original_target = original_target
        self.nodes = nodes
        self.edges = edges

        # Ensure each node has required fields
        self._normalize_nodes()

    def _normalize_nodes(self):
        """Ensure each node has required fields with defaults."""
        for node_data in self.nodes.values():
            # Set default tool_type if not specified
            if "tool_type" not in node_data:
                node_data["tool_type"] = "retrieval"

            # Set empty tool_parameters if not specified
            if "tool_parameters" not in node_data:
                node_data["tool_parameters"] = {}

            # Set empty dependencies if not specified
            if "dependencies" not in node_data:
                node_data["dependencies"] = []

    def topological_order(self) -> List[str]:
        """Get topological ordering of tasks.

        Returns:
            List of task IDs in topological order.
        """
        in_degree = {node_id: 0 for node_id in self.nodes}
        for source, target in self.edges:
            in_degree[target] += 1

        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node_id = queue.pop(0)
            result.append(node_id)

            for source, target in self.edges:
                if source == node_id:
                    in_degree[target] -= 1
                    if in_degree[target] == 0:
                        queue.append(target)

        return result if len(result) == len(self.nodes) else []

    def get_node(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task node by ID.

        Args:
            task_id: Task ID.

        Returns:
            Task node data or None if not found.
        """
        return self.nodes.get(task_id)

    def get_tool_type(self, task_id: str) -> str:
        """Get tool type for a task.

        Args:
            task_id: Task ID.

        Returns:
            Tool type (default: "retrieval").
        """
        node = self.get_node(task_id)
        return node.get("tool_type", "retrieval") if node else "retrieval"

    def get_tool_parameters(self, task_id: str) -> Dict[str, Any]:
        """Get tool parameters for a task.

        Args:
            task_id: Task ID.

        Returns:
            Tool parameters dictionary.
        """
        node = self.get_node(task_id)
        return node.get("tool_parameters", {}) if node else {}


__all__ = ["TaskDAG"]
