"""
AMI Task Planner - Memory-First task decomposition.

Memory-First flow:
1. Query Memory for the whole task (single query, not per-subtask)
2. Inject Memory context into LLM decomposition prompt
3. Decompose into atomic, self-contained subtasks
4. Assign Memory result as workflow_guide to browser-type subtasks (whole injection)

Decomposition principles (from CAMEL's TASK_DECOMPOSE_PROMPT):
- Self-contained subtasks with clear deliverables
- Each subtask needs only 1-2 tool calls (single astep())
- Strategic grouping of sequential actions by same worker
- Aggressive parallelization across different workers
- Explicit dependencies between subtasks

No CAMEL Workforce dependencies - just uses ChatAgent for LLM calls.
"""

import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from camel.agents import ChatAgent
    from ..tools.toolkits import MemoryToolkit, QueryResult

from src.common.llm import parse_json_with_repair
from .ami_task_executor import AMISubtask, SubtaskState
from ..events import (
    DecomposeProgressData,
    MemoryLevelData,
    NoticeData,
)

logger = logging.getLogger(__name__)

_MAX_GUIDE_SEQUENCES = 3
_MAX_GUIDE_INTENTS = 20


# =============================================================================
# Prompts for Task Decomposition
# =============================================================================

# Fine-grained decomposition prompt - based on CAMEL's TASK_DECOMPOSE_PROMPT
# Key principles:
# 1. Self-Contained Subtasks - each subtask must be independently understandable
# 2. Clear Deliverables - specify exact output format for each subtask
# 3. Strategic Grouping - group sequential actions by same worker type
# 4. Aggressive Parallelization - parallelize across different workers
# 5. Explicit Dependencies - LLM specifies which tasks depend on which
FINE_GRAINED_DECOMPOSE_PROMPT = r"""You need to decompose a task into atomic, executable subtasks.

**CRITICAL PRINCIPLES:**

1. **Self-Contained Subtasks**: Each subtask must be FULLY self-sufficient and independently understandable.
   - DO NOT use relative references like "the previous result" or "the data above"
   - DO write explicit instructions with all necessary context
   - Example: Instead of "Analyze the document", write "Analyze the document titled 'Q2 Report' and extract key metrics"

2. **Clear Deliverables**: Each subtask must specify a concrete output.
   - DO NOT use vague verbs like "research" or "look into" without defining output
   - DO specify the format: "Return a JSON list of...", "Write to file products.md..."
   - Example: "Extract all product names and prices, return as JSON list with 'name' and 'price' keys"

3. **Atomic Actions**: Each subtask should require only 1-2 tool calls.
   - Browser subtasks: one navigation or one data extraction
   - Document subtasks: one file read or one file write
   - Code subtasks: one command execution

4. **Strategic Grouping**: Group ONLY sequential actions that:
   - Must be done by the SAME worker type
   - Are tightly coupled (e.g., navigate to page + extract data from same page)

5. **Aggressive Parallelization**: Create separate subtasks for:
   - Different worker types (browser vs document)
   - Independent operations (processing multiple items in parallel)

6. **Explicit Dependencies**: You MUST specify dependencies for each task.
   - If a task needs data from another task, add depends_on attribute
   - If tasks are independent, do NOT add depends_on (they can run in parallel)
   - Example: Task 3 needs results from Task 1 and 2 → depends_on="1,2"

**LANGUAGE POLICY**: Write subtask content in the SAME language as the user's task.

**AVAILABLE WORKERS:**
{workers_info}

**OUTPUT FORMAT (XML):**
<tasks>
<task id="1" type="browser">Visit producthunt.com and navigate to the weekly leaderboard page</task>
<task id="2" type="browser" depends_on="1">Extract the top 10 products with names, descriptions, and URLs. Return as JSON list.</task>
<task id="3" type="browser" depends_on="2">Save the extracted products to a note file named 'products.md'</task>
<task id="4" type="document" depends_on="3">Read products.md and generate an HTML report with product cards</task>
</tasks>

Each <task> element:
- Has "id" attribute: Sequential number (1, 2, 3...)
- Has "type" attribute: browser, document, code, or multi_modal
- Has optional "depends_on" attribute: Comma-separated list of task IDs that must complete first
  - ONLY add depends_on if the task NEEDS data from previous tasks
  - Independent tasks should NOT have depends_on (allows parallel execution)
- Contains a self-contained, actionable description with clear deliverable

**IMPORTANT**: Do NOT assume sequential dependencies. Only add depends_on when there is actual data dependency.

Example of INDEPENDENT tasks (can run in parallel):
<tasks>
<task id="1" type="browser">Search Amazon for AI glasses and extract top 3 products</task>
<task id="2" type="browser">Search ProductHunt for AI wearables and extract top products</task>
<task id="3" type="document" depends_on="1,2">Combine results from Amazon and ProductHunt searches into a comparison report</task>
</tasks>

**TASK TO DECOMPOSE:**
{task}
{memory_context}
Now decompose this task into atomic subtasks:"""


# Legacy coarse-grained prompt (kept for backward compatibility)
COARSE_DECOMPOSE_PROMPT = """Split the task by work type. Keep related operations of the same type together.

Types:
- browser: Web browsing, research, online operations
- document: Writing reports, creating files
- code: Programming, terminal commands

**CRITICAL Language Policy**:
- The subtask "content" field MUST be in the SAME language as the user's task.
- If the task is in Chinese, write subtask content in Chinese.
- If the task is in English, write subtask content in English.

Output JSON:
{{
    "subtasks": [
        {{"id": "1", "type": "browser", "content": "...", "depends_on": []}},
        {{"id": "2", "type": "document", "content": "...", "depends_on": ["1"]}}
    ]
}}

Task: {task}"""


# Default worker descriptions (used if not provided)
DEFAULT_WORKER_DESCRIPTIONS = {
    "browser": (
        "Browser Agent: Can search the web, visit URLs, click elements, "
        "type text, extract page content, and take notes. Use for web research "
        "and online operations."
    ),
    "document": (
        "Document Agent: Can read and write files (Markdown, HTML, JSON, YAML, "
        "Word, PDF, PowerPoint, Excel, CSV). Use for creating reports, documents, "
        "and data files."
    ),
    "code": (
        "Developer Agent: Can execute terminal commands, write and run code, "
        "manage files. Use for programming tasks and system operations."
    ),
    "multi_modal": (
        "Multi-Modal Agent: Can process images, audio, and video. "
        "Use for media analysis and generation tasks."
    ),
}


class AMITaskPlanner:
    """
    Task planner with fine-grained decomposition following Eigent/CAMEL pattern.

    Key features:
    - Fine-grained decomposition into atomic subtasks (1-2 tool calls each)
    - Self-contained subtask descriptions with clear deliverables
    - Memory query for workflow guidance
    - SSE events for real-time UI updates

    Design principles (from CAMEL's TASK_DECOMPOSE_PROMPT):
    - Self-Contained Subtasks: Each subtask independently understandable
    - Clear Deliverables: Specific output format for each subtask
    - Strategic Grouping: Group sequential actions by same worker
    - Aggressive Parallelization: Parallelize across different workers
    """

    def __init__(
        self,
        task_id: str,
        task_state: Any,  # TaskState for SSE events
        task_agent: "ChatAgent",  # LLM agent for decomposition
        memory_toolkit: Optional["MemoryToolkit"] = None,
        worker_descriptions: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the task planner.

        Args:
            task_id: Unique task identifier for events.
            task_state: TaskState instance for SSE event emission.
            task_agent: ChatAgent instance for LLM calls.
            memory_toolkit: Optional MemoryToolkit for workflow guidance.
            worker_descriptions: Optional dict of worker type -> description.
                                 Used to tell LLM what workers are available.
        """
        self.task_id = task_id
        self._task_state = task_state
        self._task_agent = task_agent
        self._memory_toolkit = memory_toolkit
        self._worker_descriptions = worker_descriptions or DEFAULT_WORKER_DESCRIPTIONS

        logger.info(
            f"[AMITaskPlanner] Initialized for task {task_id}, "
            f"memory_toolkit={'available' if memory_toolkit else 'not available'}"
        )

    async def _emit_event(self, event: Any) -> None:
        """Emit an event to the task's event queue."""
        if self._task_state and hasattr(self._task_state, 'put_event'):
            await self._task_state.put_event(event)

    async def decompose_and_query_memory(self, task: str) -> List[AMISubtask]:
        """
        Memory-First decomposition: query Memory first, then decompose with context.

        Flow:
        1. Query Memory for the whole task (single query)
        2. Format Memory result as context for LLM decomposition
        3. Decompose with Memory context (LLM sees known workflow)
        4. Assign Memory result to browser-type subtasks (whole injection)

        Args:
            task: The original task description from user.

        Returns:
            List of AMISubtask objects ready for execution.
        """
        logger.info(f"[AMITaskPlanner] Memory-First decomposing task: {task[:100]}...")

        # Step 1: Query Memory for the whole task
        task_memory = await self._query_task_memory(task)

        # Step 2: Format Memory result as decompose prompt context
        memory_context = self._format_memory_for_decompose(task_memory)

        # Step 3: Decompose with Memory context
        subtasks = await self._fine_grained_decompose(task, memory_context=memory_context)

        # Step 4: Assign Memory result to browser-type subtasks (Plan B: whole injection)
        self._assign_memory_to_subtasks(subtasks, task_memory)

        # Emit final decomposition event
        subtasks_data = [
            {
                "id": st.id,
                "content": st.content,
                "state": st.state.value,
                "agent_type": st.agent_type,
                "memory_level": st.memory_level,
            }
            for st in subtasks
        ]

        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=1.0,
            message="Decomposition complete",
            sub_tasks=subtasks_data,
            is_final=True,
        ))

        return subtasks

    def _build_workers_info(self) -> str:
        """Build worker descriptions string for the decomposition prompt."""
        lines = []
        for worker_type, description in self._worker_descriptions.items():
            lines.append(f"- **{worker_type}**: {description}")
        return "\n".join(lines)

    async def _query_task_memory(self, task: str) -> Optional["QueryResult"]:
        """
        Query Memory for the whole task (single query).

        Returns QueryResult or None if Memory is not available.
        Emits MemoryLevelData event with the result level.
        """
        if not self._memory_toolkit:
            logger.info("[AMITaskPlanner] Memory toolkit not configured, skipping")
            return None

        if not self._memory_toolkit.is_available():
            logger.info("[AMITaskPlanner] Memory service not available, skipping")
            return None

        logger.info(f"[AMITaskPlanner] Querying Memory for whole task: {task[:80]}...")

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.1,
            message="Querying Memory for task workflow...",
            is_final=False,
        ))

        try:
            result = await self._memory_toolkit.query_task(task)

            # Determine level for logging and event
            if result.cognitive_phrase:
                level = "L1"
                states_count = len(result.cognitive_phrase.states) if hasattr(result.cognitive_phrase, 'states') else 0
                logger.info(
                    f"[AMITaskPlanner] Memory L1 match: CognitivePhrase with "
                    f"{states_count} states"
                )
            elif result.states:
                level = "L2"
                logger.info(
                    f"[AMITaskPlanner] Memory L2 match: {len(result.states)} states, "
                    f"{len(result.actions)} actions"
                )
            else:
                level = "L3"
                logger.info("[AMITaskPlanner] Memory L3: no match")

            # Emit memory level event
            await self._emit_event(MemoryLevelData(
                task_id=self.task_id,
                level=level,
                reason=f"Task-level Memory query",
                states_count=len(result.states) if result.states else 0,
                method="ami_task_planner",
            ))

            return result

        except Exception as e:
            logger.warning(f"[AMITaskPlanner] Memory query failed: {e}")
            return None

    def _format_memory_for_decompose(self, task_memory: Optional["QueryResult"]) -> str:
        """
        Format Memory result as context for the decomposition prompt.

        L1/L2: Returns a description of the known workflow steps
        L3/None: Returns empty string (no context)
        """
        if not task_memory:
            logger.info("[AMITaskPlanner] No memory result, skipping context")
            return ""
        if not task_memory.success:
            logger.info(
                f"[AMITaskPlanner] Memory result not successful "
                f"(success={task_memory.success}), skipping context"
            )
            return ""

        from ..tools.toolkits import MemoryToolkit

        context_text = MemoryToolkit.format_task_result(task_memory)
        if not context_text:
            logger.warning(
                f"[AMITaskPlanner] format_task_result returned empty "
                f"(has_phrase={bool(task_memory.cognitive_phrase)}, "
                f"states={len(task_memory.states) if task_memory.states else 0})"
            )
            return ""

        logger.info(
            f"[AMITaskPlanner] Memory context for decompose "
            f"({len(context_text)} chars): {context_text[:300]}..."
        )

        return (
            "\n\n**MEMORY CONTEXT (known workflow from past executions):**\n"
            f"{context_text}"
        )

    def _assign_memory_to_subtasks(
        self, subtasks: List[AMISubtask], task_memory: Optional["QueryResult"]
    ) -> None:
        """
        Assign the whole Memory result as workflow_guide to browser-type subtasks.

        Plan B (whole injection): The entire Memory path is injected into every
        browser subtask as workflow_guide. Non-browser subtasks stay L3.
        The dynamic page operations layer will provide fine-grained per-page
        guidance during execution.
        """
        if not task_memory or not task_memory.success:
            return

        from ..tools.toolkits import MemoryToolkit

        if task_memory.cognitive_phrase:
            level = "L1"
            guide = MemoryToolkit.format_cognitive_phrase(task_memory.cognitive_phrase)
        elif task_memory.states:
            level = "L2"
            guide = MemoryToolkit.format_navigation_path(
                task_memory.states, task_memory.actions or []
            )
        else:
            return

        assigned_count = 0
        for subtask in subtasks:
            if subtask.agent_type == "browser":
                subtask.memory_level = level
                subtask.workflow_guide = guide
                assigned_count += 1

        logger.info(
            f"[AMITaskPlanner] Assigned {level} workflow_guide "
            f"({len(guide)} chars) to {assigned_count}/{len(subtasks)} "
            f"browser subtasks: {guide[:200]}..."
        )

    async def _fine_grained_decompose(
        self, task: str, memory_context: str = ""
    ) -> List[AMISubtask]:
        """
        Fine-grained task decomposition into atomic subtasks.

        Each subtask should:
        - Be self-contained and independently understandable
        - Have a clear deliverable
        - Require only 1-2 tool calls (single astep() execution)

        Args:
            task: The original task description.
            memory_context: Optional Memory context string to inject into prompt.

        Returns:
            List of AMISubtask objects (without workflow_guide yet).

        Raises:
            ValueError: If LLM response cannot be parsed.
        """
        logger.info(f"[AMITaskPlanner] Fine-grained decomposing task...")

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.3,
            message="Analyzing task and creating atomic subtasks...",
            is_final=False,
        ))

        # Build the prompt with worker descriptions and memory context
        workers_info = self._build_workers_info()
        prompt = FINE_GRAINED_DECOMPOSE_PROMPT.format(
            task=task,
            workers_info=workers_info,
            memory_context=memory_context,
        )

        # Call LLM for fine-grained decomposition
        self._task_agent.reset()
        response = self._task_agent.step(prompt)

        if not response or not response.msg:
            raise ValueError("Fine-grained decomposition returned empty response")

        response_text = response.msg.content
        logger.debug(f"[AMITaskPlanner] Fine-grained decompose raw response: {response_text[:500]}...")

        # Parse the XML response (CAMEL format)
        subtasks = self._parse_xml_subtasks(response_text)

        # Log each subtask for traceability
        type_counts: Dict[str, int] = {}
        for st in subtasks:
            type_counts[st.agent_type] = type_counts.get(st.agent_type, 0) + 1
            deps = f" depends_on={st.depends_on}" if st.depends_on else ""
            logger.info(
                f"[AMITaskPlanner] Subtask {st.id} ({st.agent_type}): "
                f"{st.content[:120]}{deps}"
            )
        logger.info(
            f"[AMITaskPlanner] Fine-grained decomposition complete: {len(subtasks)} subtasks "
            f"(types: {type_counts})"
        )

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.8,
            message=f"Created {len(subtasks)} atomic subtasks",
            is_final=False,
        ))

        return subtasks

    def _parse_xml_subtasks(self, response_text: str) -> List[AMISubtask]:
        """
        Parse LLM XML response into AMISubtask objects.

        Expected format:
        <tasks>
        <task id="1" type="browser">Visit producthunt.com</task>
        <task id="2" type="browser" depends_on="1">Extract products</task>
        <task id="3" type="document" depends_on="2">Create report</task>
        </tasks>

        Dependencies are now EXPLICIT via depends_on attribute, not inferred from order.
        This allows independent tasks to run in parallel.

        Args:
            response_text: Raw LLM response text.

        Returns:
            List of parsed AMISubtask objects.

        Raises:
            ValueError: If response cannot be parsed.
        """
        subtasks = []

        # Extract <tasks>...</tasks> block
        tasks_match = re.search(r'<tasks>(.*?)</tasks>', response_text, re.DOTALL | re.IGNORECASE)
        if not tasks_match:
            # Fallback: try to parse as JSON (backward compatibility)
            logger.warning("[AMITaskPlanner] No <tasks> block found, trying JSON fallback")
            return self._parse_coarse_subtasks(response_text)

        tasks_content = tasks_match.group(1)

        # Extract individual <task> elements with all attributes
        # Pattern to match <task ...attributes...>content</task>
        task_pattern = r'<task\s+([^>]*)>(.*?)</task>'
        matches = re.findall(task_pattern, tasks_content, re.DOTALL | re.IGNORECASE)

        if not matches:
            # Fallback: try simpler pattern without attributes
            task_pattern_simple = r'<task>(.*?)</task>'
            simple_matches = re.findall(task_pattern_simple, tasks_content, re.DOTALL | re.IGNORECASE)
            if simple_matches:
                for i, content in enumerate(simple_matches, 1):
                    # Infer type from content, no dependencies (independent tasks)
                    agent_type = self._infer_agent_type(content.strip())
                    subtask = AMISubtask(
                        id=str(i),
                        content=content.strip(),
                        agent_type=agent_type,
                        depends_on=[],  # No dependencies inferred
                    )
                    subtasks.append(subtask)
            else:
                logger.warning("[AMITaskPlanner] No <task> elements found, trying JSON fallback")
                return self._parse_coarse_subtasks(response_text)
        else:
            for i, (attrs_str, content) in enumerate(matches, 1):
                # Parse attributes from the attribute string
                # Use LLM-provided ID if available, otherwise use enumeration
                task_id = str(i)
                agent_type = "browser"  # Default type
                depends_on = []

                # Extract id attribute (LLM-provided ID takes precedence)
                id_match = re.search(r'id=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
                if id_match:
                    task_id = id_match.group(1).strip()

                # Extract type attribute
                type_match = re.search(r'type=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
                if type_match:
                    agent_type = type_match.group(1).lower().strip()
                    if agent_type not in ("browser", "document", "code", "multi_modal"):
                        logger.warning(
                            f"[AMITaskPlanner] Unknown agent type '{agent_type}', inferring from content"
                        )
                        agent_type = self._infer_agent_type(content.strip())
                else:
                    # Infer type from content if not specified
                    agent_type = self._infer_agent_type(content.strip())

                # Extract depends_on attribute (comma-separated list of task IDs)
                depends_match = re.search(r'depends_on=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
                if depends_match:
                    deps_str = depends_match.group(1).strip()
                    # Parse comma-separated list
                    depends_on = [d.strip() for d in deps_str.split(',') if d.strip()]

                logger.debug(
                    f"[AMITaskPlanner] Parsed task: id={task_id}, type={agent_type}, "
                    f"depends_on={depends_on}, content={content.strip()[:50]}..."
                )

                subtask = AMISubtask(
                    id=task_id,
                    content=content.strip(),
                    agent_type=agent_type,
                    depends_on=depends_on,
                )
                subtasks.append(subtask)

        if not subtasks:
            raise ValueError("Fine-grained decomposition produced no valid subtasks")

        return subtasks

    def _infer_agent_type(self, content: str) -> str:
        """
        Infer agent type from subtask content.

        Args:
            content: Subtask content/description.

        Returns:
            Inferred agent type (browser, document, code, or multi_modal).
        """
        content_lower = content.lower()

        # Browser indicators
        browser_keywords = [
            "visit", "navigate", "browse", "search", "click", "type",
            "extract", "scrape", "webpage", "website", "url", "http",
            "producthunt", "google", "amazon", "网页", "访问", "搜索",
            "点击", "浏览", "提取",
        ]
        if any(kw in content_lower for kw in browser_keywords):
            return "browser"

        # Document indicators
        document_keywords = [
            "write", "create", "generate", "report", "document", "file",
            "markdown", "html", "pdf", "word", "excel", "powerpoint",
            "read file", "save", "export", "写", "生成", "报告", "文档",
            "创建", "保存",
        ]
        if any(kw in content_lower for kw in document_keywords):
            return "document"

        # Code indicators
        code_keywords = [
            "run", "execute", "command", "terminal", "shell", "script",
            "python", "npm", "pip", "git", "compile", "build", "install",
            "运行", "执行", "命令", "脚本", "编译",
        ]
        if any(kw in content_lower for kw in code_keywords):
            return "code"

        # Multi-modal indicators
        mm_keywords = [
            "image", "video", "audio", "photo", "picture", "transcribe",
            "analyze image", "generate image", "图片", "视频", "音频",
        ]
        if any(kw in content_lower for kw in mm_keywords):
            return "multi_modal"

        # Default to browser (most common)
        return "browser"

    def _parse_coarse_subtasks(self, response_text: str) -> List[AMISubtask]:
        """
        Parse LLM response into AMISubtask objects.

        Args:
            response_text: Raw LLM response text.

        Returns:
            List of parsed AMISubtask objects.

        Raises:
            ValueError: If response cannot be parsed or is missing required fields.
        """
        # Use common JSON parsing with repair
        data = parse_json_with_repair(response_text)

        # Check for fallback (parsing failed completely)
        if "answer" in data and "subtasks" not in data:
            logger.error(f"[AMITaskPlanner] JSON parsing failed, got fallback: {response_text[:500]}")
            raise ValueError("Invalid JSON in coarse decomposition response")

        # Validate structure
        if "subtasks" not in data:
            raise ValueError("Coarse decomposition response missing 'subtasks' field")

        subtasks = []
        for item in data["subtasks"]:
            # Validate required fields
            if "id" not in item or "type" not in item or "content" not in item:
                logger.warning(f"[AMITaskPlanner] Skipping invalid subtask: {item}")
                continue

            # Validate agent type
            agent_type = item["type"].lower()
            if agent_type not in ("browser", "document", "code", "multi_modal"):
                logger.warning(
                    f"[AMITaskPlanner] Unknown agent type '{agent_type}', defaulting to 'browser'"
                )
                agent_type = "browser"

            subtask = AMISubtask(
                id=str(item["id"]),
                content=item["content"],
                agent_type=agent_type,
                depends_on=item.get("depends_on", []),
            )
            subtasks.append(subtask)

        if not subtasks:
            raise ValueError("Coarse decomposition produced no valid subtasks")

        return subtasks

    @staticmethod
    def _format_intent_for_guide(intent: Any) -> str:
        intent_type = str(getattr(intent, "type", "") or "").lower()
        element_role = getattr(intent, "element_role", None) or getattr(intent, "role", None)
        element_ref = getattr(intent, "element_ref", None) or getattr(intent, "ref", None)
        text = getattr(intent, "text", None)
        value = getattr(intent, "value", None)
        attributes = getattr(intent, "attributes", None)
        attrs = attributes if isinstance(attributes, dict) else {}

        if intent_type in ("click", "clickelement"):
            if text:
                return f"click \"{text}\""
            if element_role:
                return f"click {element_role}"
            if element_ref:
                return f"click element {element_ref}"
        elif intent_type in ("type", "input", "typetext"):
            target = text or element_role or "field"
            if value:
                return f"type \"{value}\" in {target}"
            return f"type in {target}"
        elif intent_type in ("scroll", "scrolldown", "scrollup"):
            direction = attrs.get("scroll_direction") or (
                "down" if "down" in intent_type else "up" if "up" in intent_type else ""
            )
            distance = attrs.get("scroll_distance")
            if distance is not None and str(distance) != "":
                distance_str = str(distance)
                if distance_str.isdigit():
                    distance_str = f"{distance_str}px"
                return f"scroll {direction} {distance_str}".strip()
            return f"scroll {direction}".strip()
        elif intent_type in ("navigate", "goto"):
            if value or text:
                return f"navigate to {value or text}"

        if text or value:
            return f"{intent_type or 'intent'}: {text or value}"
        return intent_type or ""

    @staticmethod
    def _append_intent_sequences(
        lines: List[str],
        intent_sequences: List[Any],
        indent: str = "    ",
    ) -> None:
        if not intent_sequences:
            return

        lines.append(f"{indent}Intent sequences (from memory):")
        for idx, seq in enumerate(intent_sequences[:_MAX_GUIDE_SEQUENCES], 1):
            desc = getattr(seq, "description", None) or "Operation"
            seq_id = getattr(seq, "id", "") or ""
            label = f"{idx}. {desc}"
            if seq_id:
                label += f" (id: {seq_id})"
            lines.append(f"{indent}  {label}")

            causes_nav = getattr(seq, "causes_navigation", False)
            nav_target = getattr(seq, "navigation_target_state_id", None)
            if causes_nav and nav_target:
                lines.append(f"{indent}     navigates_to: {nav_target}")

            intents = getattr(seq, "intents", None)
            if intents:
                lines.append(f"{indent}     intents:")
                for intent in intents[:_MAX_GUIDE_INTENTS]:
                    intent_line = AMITaskPlanner._format_intent_for_guide(intent)
                    if intent_line:
                        lines.append(f"{indent}       - {intent_line}")
            else:
                lines.append(f"{indent}     intents: (none)")

        remaining = len(intent_sequences) - _MAX_GUIDE_SEQUENCES
        if remaining > 0:
            lines.append(f"{indent}  ... ({remaining} more sequences)")

    @staticmethod
    def _format_action_trigger(action: Any) -> Optional[str]:
        trigger = getattr(action, "trigger", None)
        if not isinstance(trigger, dict):
            return None

        parts = []
        text = trigger.get("text")
        role = trigger.get("role") or trigger.get("element_role")
        ref = trigger.get("ref") or trigger.get("element_ref")
        if text:
            parts.append(f"text=\"{text}\"")
        if role:
            parts.append(f"role={role}")
        if ref:
            parts.append(f"ref={ref}")
        if not parts:
            return None
        return ", ".join(parts)

    @staticmethod
    def _format_cognitive_phrase(cognitive_phrase: Any) -> str:
        """
        Format a cognitive phrase into a workflow guide.

        This method converts Memory's cognitive_phrase object into a
        human-readable workflow guide that can be injected into prompts.

        Args:
            cognitive_phrase: CognitivePhrase object from Memory.

        Returns:
            Formatted workflow guide string.
        """
        if not cognitive_phrase:
            return ""

        lines = []
        lines.append("## Historical Workflow Guide")
        lines.append("")

        # Add task description if available
        if hasattr(cognitive_phrase, 'task') and cognitive_phrase.task:
            lines.append(f"**Original Task**: {cognitive_phrase.task}")
            lines.append("")

        # Add states as steps
        if hasattr(cognitive_phrase, 'states') and cognitive_phrase.states:
            lines.append("**Steps to follow**:")
            for i, state in enumerate(cognitive_phrase.states, 1):
                # Extract state description
                # State object has: page_url (required), page_title (optional), description (optional)
                desc = None

                # Try description first
                if hasattr(state, 'description') and state.description:
                    desc = state.description
                # Try page_title
                elif hasattr(state, 'page_title') and state.page_title:
                    desc = state.page_title
                # Generate semantic description from URL
                elif hasattr(state, 'page_url'):
                    desc = self._generate_url_description(state.page_url)
                # Fallback to string representation
                elif hasattr(state, '__str__'):
                    str_repr = str(state)[:200]
                    if str_repr and str_repr != "None":
                        desc = str_repr

                if desc:
                    lines.append(f"  Step {i}: {desc}")

                # Add action if available
                if hasattr(cognitive_phrase, 'actions') and i <= len(cognitive_phrase.actions):
                    action = cognitive_phrase.actions[i - 1]

                    # Action object has: type (default "user_action"), description (optional)
                    # The description is generated by workflow_processor
                    action_desc = None
                    if hasattr(action, 'description') and action.description:
                        action_desc = action.description
                    elif hasattr(action, 'type') and action.type:
                        action_desc = action.type

                    if action_desc:
                        lines.append(f"    Action: {action_desc}")

                    trigger_line = AMITaskPlanner._format_action_trigger(action)
                    if trigger_line:
                        lines.append(f"      Trigger: {trigger_line}")
                    trigger_sequence_id = getattr(action, "trigger_sequence_id", None)
                    if trigger_sequence_id:
                        lines.append(f"      Trigger sequence: {trigger_sequence_id}")

        return "\n".join(lines)

    @staticmethod
    def _generate_url_description(url: str) -> str:
        """Generate a semantic description from URL.

        Args:
            url: The URL to describe.

        Returns:
            A human-readable description of the page type.
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            path = parsed.path.lower()

            # Product Hunt specific patterns
            if 'producthunt.com' in url:
                if '/leaderboard/daily/' in path:
                    return "Product Hunt 每日排行榜页面"
                elif '/leaderboard/weekly/' in path:
                    return "Product Hunt 周排行榜页面"
                elif '/leaderboard/monthly/' in path:
                    return "Product Hunt 月排行榜页面"
                elif '/leaderboard/' in path:
                    return "Product Hunt 排行榜页面"
                elif '/posts/' in path:
                    return "Product Hunt 产品详情页面"
                elif '/topics/' in path:
                    return "Product Hunt 主题页面"
                elif path == '/' or path == '':
                    return "Product Hunt 首页"
                else:
                    return f"Product Hunt 页面 ({parsed.path})"

            # Common e-commerce patterns
            elif '/products/' in path or '/product/' in path or '/item/' in path:
                return "产品详情页面"
            elif '/search' in path or '/query' in path:
                return "搜索结果页面"
            elif '/category' in path or '/categories' in path:
                return "分类页面"
            elif '/cart' in path:
                return "购物车页面"
            elif '/checkout' in path:
                return "结账页面"

            # Common patterns
            elif path == '/' or path == '':
                return f"{parsed.netloc} 首页"
            elif '/home' in path:
                return "首页"
            elif '/login' in path or '/signin' in path:
                return "登录页面"
            elif '/signup' in path or '/register' in path:
                return "注册页面"
            elif '/settings' in path or '/profile' in path or '/account' in path:
                return "设置/个人资料页面"

            # Fallback: show domain + simplified path
            domain = parsed.netloc.replace('www.', '')
            if len(path) > 30:
                path = path[:30] + '...'
            return f"{domain}{path}"

        except Exception:
            # If parsing fails, return URL as-is
            return url

    @staticmethod
    def _format_navigation_path(states: List[Any], actions: List[Any]) -> str:
        """
        Format a navigation path into a workflow guide.

        This method converts Memory's states and actions into a
        human-readable navigation guide.

        Args:
            states: List of State objects from Memory.
            actions: List of Action objects from Memory.

        Returns:
            Formatted navigation guide string.
        """
        if not states:
            return ""

        lines = []
        lines.append("## Navigation Path Guide")
        lines.append("")
        lines.append("**Pages to visit**:")

        for i, state in enumerate(states, 1):
            # Extract state description - State has page_url, page_title, description
            desc = None

            # Try description first
            if hasattr(state, 'description') and state.description:
                desc = state.description
            # Try page_title + page_url
            elif hasattr(state, 'page_title') and state.page_title:
                title = state.page_title
                url = getattr(state, 'page_url', None)
                if url:
                    desc = f"{title} - {url}"
                else:
                    desc = title
            # Try page_url alone
            elif hasattr(state, 'page_url'):
                desc = state.page_url
            # Fallback to string representation
            else:
                str_repr = str(state)[:200]
                if str_repr and str_repr != "None":
                    desc = str_repr

            if desc:
                lines.append(f"  {i}. {desc}")

            # Add action if available
            if i <= len(actions):
                action = actions[i - 1]
                # Action has type and description
                if hasattr(action, 'description') and action.description:
                    lines.append(f"     Then: {action.description}")
                elif hasattr(action, 'type') and action.type:
                    # Also show target if available (Action has source/target)
                    target_id = getattr(action, 'target', None)
                    if target_id:
                        lines.append(f"     Then: {action.type} to state {target_id}")
                    else:
                        lines.append(f"     Then: {action.type}")

                trigger_line = AMITaskPlanner._format_action_trigger(action)
                if trigger_line:
                    lines.append(f"       Trigger: {trigger_line}")
                trigger_sequence_id = getattr(action, "trigger_sequence_id", None)
                if trigger_sequence_id:
                    lines.append(f"       Trigger sequence: {trigger_sequence_id}")

        return "\n".join(lines)

    # =========================================================================
    # Simple decomposition (without Memory) - uses fine-grained by default
    # =========================================================================

    async def simple_decompose(self, task: str) -> List[AMISubtask]:
        """
        Simple decomposition without Memory query.

        Use this when Memory is not available or not needed.
        Uses fine-grained decomposition by default.

        Args:
            task: The original task description.

        Returns:
            List of AMISubtask objects.
        """
        return await self._fine_grained_decompose(task)

    async def coarse_decompose(self, task: str) -> List[AMISubtask]:
        """
        Legacy coarse-grained decomposition (for backward compatibility).

        Splits task by agent type only (browser, document, code).
        Use fine_grained_decompose for better results.

        Args:
            task: The original task description.

        Returns:
            List of AMISubtask objects.
        """
        logger.info(f"[AMITaskPlanner] Coarse decomposing task (legacy mode)...")

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.1,
            message="Analyzing task types...",
            is_final=False,
        ))

        # Build the prompt
        prompt = COARSE_DECOMPOSE_PROMPT.format(task=task)

        # Call LLM for coarse decomposition
        self._task_agent.reset()
        response = self._task_agent.step(prompt)

        if not response or not response.msg:
            raise ValueError("Coarse decomposition returned empty response")

        response_text = response.msg.content
        logger.debug(f"[AMITaskPlanner] Coarse decompose raw response: {response_text[:500]}...")

        # Parse the JSON response
        subtasks = self._parse_coarse_subtasks(response_text)

        # Log summary
        type_counts: Dict[str, int] = {}
        for st in subtasks:
            type_counts[st.agent_type] = type_counts.get(st.agent_type, 0) + 1
        logger.info(
            f"[AMITaskPlanner] Coarse decomposition complete: {len(subtasks)} subtasks "
            f"(types: {type_counts})"
        )

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.3,
            message=f"Identified {len(subtasks)} subtasks",
            is_final=False,
        ))

        return subtasks
