"""
AMI Task Executor - Lightweight task execution system.

This module replaces CAMEL Workforce with a simpler, more controllable system:
- Direct control over prompt format (workflow_guide as explicit instruction)
- Sequential execution with dependency resolution
- SSE event emission for real-time UI updates
- Pause/resume support for multi-turn conversations

No CAMEL dependencies - uses AMIAgent for execution.
"""

import asyncio
import html as html_mod
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .ami_agent import AMIAgent

from ..events import (
    SubtaskStateData,
    AssignTaskData,
    WorkerAssignedData,
    NoticeData,
    AgentReportData,
    DynamicTasksAddedData,
)
from ..i18n import t

logger = logging.getLogger(__name__)

REPLAN_INSTRUCTION = """
## Task Splitting

When your task involves processing many items (>5), use replan tools to split the remaining work. Before splitting, **save all data you have collected so far to a file**.

When creating follow-up tasks, apply these rules:

1. **Self-Contained**: Each task must include ALL context needed to execute it independently — specific URLs, search keywords, output file name, data format. The agent executing the task has NO knowledge of your current task or what you have done. Never use references like "the previous result", "continue where I left off", or "remaining items".
   - Good: "Visit <url>, extract <specific fields>, save to <filename> as <format>"
   - Bad: "Continue extracting the next batch"

2. **Clear Deliverables**: Each task must specify what it produces and in what format. Do NOT use vague verbs like "research" or "look into" without defining the output.
   - Good: "Extract name, price, and rating, append to results.json"
   - Bad: "Research more items"

3. **Atomic**: Each task should be a small, focused unit of work (1-2 tool calls). Browser: one navigation or one data extraction. Document: one file operation.

4. **Parallel by Default**: Tasks that don't depend on each other's output MUST NOT have dependencies. When processing multiple items, create one task per item or small batch — they can all run in parallel.

5. **Strategic Grouping**: Sequential actions of the same type that MUST happen in order should be grouped into one task. Do not split what naturally belongs together (e.g., navigate to a page + extract data from it = one task).

6. **Preserve the Full Goal**: Your split must cover ALL remaining work. Do not drop final steps like consolidating results, creating a report, or producing the final deliverable.
""".strip()


class SubtaskState(Enum):
    """State of a subtask during execution."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class AMISubtask:
    """
    Subtask representation for AMI task execution.

    Contains all information needed for execution including workflow guidance.
    This is a simpler alternative to CAMEL's Task object.
    """
    id: str
    content: str
    agent_type: str  # "browser" | "document" | "code" | "multi_modal"
    depends_on: List[str] = field(default_factory=list)

    # Memory/workflow guidance - injected directly into prompt
    workflow_guide: Optional[str] = None
    memory_level: str = "L3"  # L1=exact match, L2=partial, L3=no match

    # Execution state
    state: SubtaskState = SubtaskState.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0


class AMITaskExecutor:
    """
    Task executor that replaces CAMEL Workforce.

    Key features:
    - workflow_guide is injected as an explicit instruction in the prompt
    - Sequential execution with dependency resolution
    - SSE events for real-time UI updates
    - Pause/resume for multi-turn conversations
    - Simple retry logic

    Unlike CAMEL Workforce:
    - No agent pooling or cloning
    - No complex coordinator agent
    - Direct control over prompt format
    - ~250 lines vs ~6000 lines
    """

    def __init__(
        self,
        task_id: str,
        task_state: Any,  # TaskState for SSE events
        agents: Dict[str, "AMIAgent"],  # {"browser": agent, "document": agent, ...}
        max_retries: int = 2,
        user_request: str = "",  # User's original request for context
        cloud_client: Optional[Any] = None,
        user_id: Optional[str] = None,
    ):
        """
        Initialize the executor.

        Args:
            task_id: Unique task identifier for events.
            task_state: TaskState instance for SSE event emission.
            agents: Dictionary mapping agent_type to ChatAgent instances.
            max_retries: Maximum retry attempts for failed subtasks.
            user_request: The user's original request (for agent context).
            cloud_client: CloudClient for saving recorded operations to Memory.
            user_id: User ID for Memory API calls.
        """
        self.task_id = task_id
        self._task_state = task_state
        self._agents = agents
        self._max_retries = max_retries
        self._user_request = user_request
        self._cloud_client = cloud_client
        self._user_id = user_id

        # Subtask management
        self._subtasks: List[AMISubtask] = []
        self._subtask_map: Dict[str, AMISubtask] = {}

        # Pause/resume control
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        # Stop control
        self._stopped = False

        logger.info(
            f"[AMITaskExecutor] Initialized for task {task_id} "
            f"with agents: {list(agents.keys())}"
        )

    @property
    def _lang(self) -> str:
        return getattr(self._task_state, 'user_language', 'en') if self._task_state else 'en'

    def set_subtasks(self, subtasks: List[AMISubtask]) -> None:
        """Set subtasks to execute."""
        self._subtasks = subtasks
        self._subtask_map = {s.id: s for s in subtasks}
        logger.info(f"[AMITaskExecutor] Set {len(subtasks)} subtasks")
        for st in subtasks:
            deps = f" depends_on={st.depends_on}" if st.depends_on else ""
            guide = f" guide={st.memory_level}" if st.memory_level else ""
            logger.info(
                f"[AMITaskExecutor] Subtask {st.id} ({st.agent_type}): "
                f"{st.content[:120]}{deps}{guide}"
            )

    async def add_subtasks_async(
        self,
        new_subtasks: List[AMISubtask],
        after_subtask_id: Optional[str] = None,
    ) -> List[str]:
        """Add subtasks dynamically during execution.

        Called by ReplanToolkit when the agent decides to split work.
        New subtasks are inserted after the specified subtask.

        Args:
            new_subtasks: Subtasks to add.
            after_subtask_id: Insert after this subtask. If None, append to end.

        Returns:
            List of new subtask IDs.
        """
        # Find insertion position: after the specified subtask AND after any
        # previously inserted dynamic subtasks (those whose ID starts with
        # the parent's ID + "_dyn_"). This ensures multiple add_subtasks_async
        # calls append in chronological order.
        insert_idx = len(self._subtasks)
        if after_subtask_id:
            dyn_prefix = f"{after_subtask_id}_dyn_"
            found = False
            for i, s in enumerate(self._subtasks):
                if s.id == after_subtask_id:
                    found = True
                    insert_idx = i + 1
                elif found and s.id.startswith(dyn_prefix):
                    # Skip past existing dynamic subtasks from the same parent
                    insert_idx = i + 1
                elif found:
                    # First non-dynamic subtask — insert here
                    insert_idx = i
                    break

        # Insert into list and update map
        for i, subtask in enumerate(new_subtasks):
            self._subtasks.insert(insert_idx + i, subtask)
            self._subtask_map[subtask.id] = subtask

        new_ids = [s.id for s in new_subtasks]

        logger.info(
            f"[AMITaskExecutor] Dynamically added {len(new_subtasks)} subtasks "
            f"after '{after_subtask_id}': {new_ids}"
        )
        for st in new_subtasks:
            logger.info(
                f"[AMITaskExecutor]   {st.id} ({st.agent_type}): "
                f"{st.content[:120]} depends_on={st.depends_on}"
            )

        # Emit SSE events
        if self._task_state:
            new_tasks_data = [
                {"id": s.id, "content": s.content, "status": "pending"}
                for s in new_subtasks
            ]
            await self._task_state.put_event(DynamicTasksAddedData(
                task_id=self.task_id,
                new_tasks=new_tasks_data,
                added_by_worker=after_subtask_id,
                reason="Agent-initiated task splitting",
                total_tasks_now=len(self._subtasks),
                total_tasks=len(self._subtasks),
            ))
            await self._task_state.put_event(AgentReportData(
                task_id=self.task_id,
                message=t("executor.tasks_added", self._lang,
                          count=len(new_subtasks), total=len(self._subtasks)),
                report_type="info",
            ))

        return new_ids

    def _remove_dynamic_subtasks(self, parent_subtask_id: str) -> None:
        """Remove all dynamic subtasks spawned by a parent subtask.

        Called before retrying a failed subtask to prevent duplicate
        dynamic subtasks from being re-added on retry.
        """
        dyn_prefix = f"{parent_subtask_id}_dyn_"
        to_remove = [s for s in self._subtasks if s.id.startswith(dyn_prefix)]

        if not to_remove:
            return

        for s in to_remove:
            self._subtasks.remove(s)
            self._subtask_map.pop(s.id, None)

        removed_ids = [s.id for s in to_remove]
        logger.info(
            f"[AMITaskExecutor] Removed {len(removed_ids)} dynamic subtasks "
            f"from failed attempt: {removed_ids}"
        )

    async def execute(self) -> Dict[str, Any]:
        """
        Execute all subtasks respecting dependencies.

        Returns:
            Dictionary with execution results:
            - completed: number of completed subtasks
            - failed: number of failed subtasks
            - stopped: whether execution was stopped
        """
        logger.info(
            f"[AMITaskExecutor] Starting execution of {len(self._subtasks)} subtasks"
        )

        completed = 0
        failed = 0

        while not self._stopped:
            # Wait if paused
            await self._wait_if_paused()

            if self._stopped:
                break

            # Find next executable subtask (dependencies satisfied)
            subtask = self._get_next_subtask()
            if subtask is None:
                # No more subtasks to execute
                break

            # Execute the subtask
            success = await self._execute_subtask(subtask)

            if success:
                completed += 1
            else:
                failed += 1
                # Continue with other subtasks even if one fails
                # (unless they depend on the failed one)

        result = {
            "completed": completed,
            "failed": failed,
            "stopped": self._stopped,
            "total": len(self._subtasks),
        }

        logger.info(f"[AMITaskExecutor] Execution finished: {result}")
        return result

    def _get_next_subtask(self) -> Optional[AMISubtask]:
        """
        Get the next subtask that can be executed.

        A subtask can execute if:
        - Its state is PENDING
        - All its dependencies are DONE

        Returns None if no executable subtask found.
        """
        for subtask in self._subtasks:
            if subtask.state != SubtaskState.PENDING:
                continue

            # Check if all dependencies are satisfied
            deps_satisfied = True
            for dep_id in subtask.depends_on:
                dep = self._subtask_map.get(dep_id)
                if dep is None:
                    # Dependency reference is invalid - log and treat as unsatisfied
                    logger.warning(
                        f"[AMITaskExecutor] Subtask {subtask.id} depends on "
                        f"non-existent task '{dep_id}'. Marking as blocked."
                    )
                    deps_satisfied = False
                    break
                if dep.state != SubtaskState.DONE:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                return subtask

        return None

    async def _execute_subtask(self, subtask: AMISubtask) -> bool:
        """
        Execute a single subtask using astep().

        Each subtask starts with a fresh conversation history (agent.reset()).
        Cross-subtask context is passed explicitly via _build_prompt()
        (dependency results injected into prompt, not via conversation history).

        Returns:
            True if successful, False otherwise.
        """
        # Get the appropriate agent
        agent = self._agents.get(subtask.agent_type)
        if agent is None:
            logger.error(
                f"[AMITaskExecutor] No agent for type: {subtask.agent_type}"
            )
            subtask.state = SubtaskState.FAILED
            subtask.error = f"No agent available for type: {subtask.agent_type}"
            await self._emit_subtask_state(subtask)
            return False

        # Reset agent conversation history — each subtask starts fresh.
        # Cross-subtask context is passed via prompt (dependency results + browser state).
        agent.reset()

        # Capture browser page state from live Playwright browser (not affected by reset).
        # This gives the new subtask awareness of where the browser currently is.
        browser_context = await self._get_browser_context(agent)

        # Wire up retry notification: emit SSE when provider retries API calls
        self._setup_retry_notification(agent, subtask)

        # Inject replan tools — agent can dynamically add follow-up tasks
        replan_toolkit = self._inject_replan_tools(agent, subtask)

        # Mark as running and emit event
        subtask.state = SubtaskState.RUNNING
        await self._emit_subtask_running(subtask)

        # Online Learning: recorder is created per-attempt inside the retry loop
        # to avoid accumulating operations from failed attempts.
        recorder = None

        # Execute with retries
        try:
            while subtask.retry_count <= self._max_retries:
                try:
                    if self._stopped:
                        return False

                    await self._wait_if_paused()

                    # Online Learning: fresh recorder for each attempt
                    if subtask.agent_type == "browser":
                        recorder = await self._start_behavior_recorder()

                    # Reset handoff state on each attempt to prevent stale data
                    # from a failed previous attempt leaking into the retry
                    if replan_toolkit:
                        replan_toolkit._handoff_result = None

                    logger.info(
                        f"[AMITaskExecutor] Executing subtask {subtask.id} "
                        f"(attempt {subtask.retry_count + 1}/{self._max_retries + 1})"
                    )

                    # Set memory context if agent supports it
                    if hasattr(agent, 'set_memory_context') and subtask.workflow_guide:
                        agent.set_memory_context(
                            memory_result=None,
                            memory_level=subtask.memory_level,
                            workflow_guide=subtask.workflow_guide,
                        )
                        logger.info(
                            f"[AMITaskExecutor] Set memory context for {type(agent).__name__}: "
                            f"level={subtask.memory_level}, workflow_guide_len={len(subtask.workflow_guide)}"
                        )

                    # Unified execution: build prompt and call astep()
                    prompt = self._build_prompt(subtask, browser_context=browser_context)
                    # Dump full prompt to file for debugging (logger truncates long messages)
                    try:
                        import pathlib, datetime
                        debug_dir = pathlib.Path.home() / ".ami" / "logs" / "prompts"
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        ts = datetime.datetime.now().strftime("%H%M%S")
                        dump_path = debug_dir / f"{ts}_{subtask.id}.txt"
                        dump_path.write_text(prompt, encoding="utf-8")
                        logger.info(
                            f"[AMITaskExecutor] Prompt for subtask {subtask.id} "
                            f"dumped to {dump_path} ({len(prompt)} chars)"
                        )
                    except Exception as e:
                        logger.warning(f"[AMITaskExecutor] Failed to dump prompt: {e}")
                    logger.info(
                        f"[AMITaskExecutor] Executing {type(agent).__name__}.astep() "
                        f"for subtask {subtask.id}"
                    )
                    response = await agent.astep(prompt)

                    # Check if agent used complete_and_handoff (replan toolkit)
                    if replan_toolkit and replan_toolkit._handoff_result is not None:
                        subtask.result = replan_toolkit._handoff_result
                    else:
                        subtask.result = response.text

                    subtask.state = SubtaskState.DONE
                    await self._emit_subtask_state(subtask)

                    # Online Learning: save recorded operations to Memory on success
                    if recorder:
                        await self._save_recorded_operations(recorder, subtask)

                    result_preview = str(subtask.result)[:200] if subtask.result else "(empty)"
                    logger.info(
                        f"[AMITaskExecutor] Subtask {subtask.id} completed: "
                        f"{result_preview}"
                    )
                    return True

                except Exception as e:
                    # Online Learning: stop recorder from failed attempt
                    # before creating a fresh one on retry
                    if recorder:
                        await self._stop_behavior_recorder(recorder)
                        recorder = None

                    subtask.retry_count += 1
                    subtask.error = str(e)

                    logger.warning(
                        f"[AMITaskExecutor] Subtask {subtask.id} failed "
                        f"(attempt {subtask.retry_count}): {e}"
                    )

                    # Clean up dynamic subtasks added during this failed attempt
                    # to prevent duplicates on retry
                    self._remove_dynamic_subtasks(subtask.id)

                    # Reset replan toolkit state for retry
                    if replan_toolkit:
                        replan_toolkit._add_tasks_call_count = 0
                    agent._should_stop_after_tool = False

                    if subtask.retry_count > self._max_retries:
                        subtask.state = SubtaskState.FAILED
                        await self._emit_subtask_state(subtask)
                        return False

            return False

        finally:
            # Online Learning: stop recorder to release CDP session
            if recorder:
                await self._stop_behavior_recorder(recorder)
                recorder = None
            # Always clean up replan tools to prevent leaking between subtasks
            self._remove_replan_tools(agent)
            # Tab cleanup: close all non-current tabs to prevent accumulation
            await self._cleanup_subtask_tabs(agent)

    async def _get_browser_context(self, agent: "AMIAgent") -> Optional[str]:
        """Get current browser page URL and title if agent has browser tools.

        Returns a lightweight context string (URL + title only, no full snapshot)
        so the agent knows where the browser is without wasting tokens.
        """
        snapshot_tool = agent.get_tool("browser_get_page_snapshot")
        if snapshot_tool is None:
            return None

        try:
            # Call the underlying toolkit method to get just page context.
            # The tool's func is a bound method on BrowserToolkit.
            toolkit = snapshot_tool.func.__self__
            context = await toolkit._get_page_context()
            if context:
                logger.info(f"[AMITaskExecutor] Browser context captured: {context[:120]}")
            return context or None
        except Exception as e:
            logger.debug(f"[AMITaskExecutor] Failed to get browser context: {e}")
            return None

    # =========================================================================
    # Tab Cleanup Between Subtasks
    # =========================================================================

    async def _cleanup_subtask_tabs(self, agent: "AMIAgent") -> None:
        """Close all tabs except the current active tab.

        Called after each subtask to prevent tab accumulation during
        long multi-subtask executions. Only the current active tab is
        preserved so the next subtask can continue from the same page.
        """
        tool = agent.get_tool("browser_get_page_snapshot")
        if tool is None:
            return

        toolkit = tool.func.__self__
        session = toolkit._session
        if session is None:
            return

        try:
            tab_info = await session.get_tab_info()
            current_tab_id = session._current_tab_id

            tabs_to_close = [
                t["tab_id"] for t in tab_info
                if t["tab_id"] != current_tab_id
            ]

            if not tabs_to_close:
                return

            for tab_id in tabs_to_close:
                await session.close_tab(tab_id)

            logger.info(
                f"[AMITaskExecutor] Tab cleanup: closed {len(tabs_to_close)} tabs "
                f"(kept current: {current_tab_id})"
            )
        except Exception as e:
            logger.warning(f"[AMITaskExecutor] Tab cleanup failed: {e}")

    # =========================================================================
    # Online Learning (BehaviorRecorder)
    # =========================================================================

    async def _start_behavior_recorder(self):
        """Start BehaviorRecorder for a browser subtask.

        Returns the recorder instance, or None if startup fails.
        All errors are caught — recorder failure must not block task execution.
        """
        try:
            from ..tools.eigent_browser.behavior_recorder import BehaviorRecorder
            from ..tools.eigent_browser.browser_session import HybridBrowserSession

            session = await HybridBrowserSession.get_session(session_id=self.task_id)
            recorder = BehaviorRecorder(enable_snapshot_capture=False)
            await recorder.start_recording(session)
            logger.info("[OnlineLearning] Recorder started")
            return recorder
        except Exception as e:
            logger.warning(f"[OnlineLearning] Failed to start recorder: {e}")
            return None

    async def _stop_behavior_recorder(self, recorder) -> None:
        """Stop a running BehaviorRecorder."""
        try:
            await recorder.stop_recording()
            logger.info("[OnlineLearning] Recorder stopped")
        except Exception as e:
            logger.warning(f"[OnlineLearning] Failed to stop recorder: {e}")

    async def _save_recorded_operations(self, recorder, subtask: AMISubtask) -> None:
        """Save recorded operations to Memory via CloudClient.

        Only called when a subtask succeeds (SubtaskState.DONE).
        """
        if not self._cloud_client or not self._user_id:
            logger.debug("[OnlineLearning] No cloud_client or user_id, skipping memory save")
            return

        operations = recorder.operations
        if not operations:
            logger.debug("[OnlineLearning] No operations recorded, skipping")
            return

        try:
            logger.info(
                f"[OnlineLearning] Saving {len(operations)} operations to memory "
                f"(subtask={subtask.id})"
            )
            result = await self._cloud_client.add_to_memory(
                user_id=self._user_id,
                operations=operations,
                session_id=f"{self.task_id}_{subtask.id}",
                generate_embeddings=True,
                skip_cognitive_phrase=True,
            )
            logger.info(f"[OnlineLearning] Memory save result: {result}")
        except Exception as e:
            logger.warning(f"[OnlineLearning] Failed to save to memory: {e}")

    # =========================================================================
    # Replan Tool Injection
    # =========================================================================

    _REPLAN_TOOL_NAMES = [
        "replan_get_subtask_list",
        "replan_report_progress",
        "replan_add_tasks",
        "replan_complete_and_handoff",
    ]

    def _inject_replan_tools(self, agent: "AMIAgent", subtask: AMISubtask):
        """Inject ReplanToolkit tools into the agent for the current subtask.

        Returns the ReplanToolkit instance so the executor can check
        _handoff_result after execution.
        """
        from ..tools.toolkits.replan_toolkit import ReplanToolkit

        toolkit = ReplanToolkit(
            executor=self,
            current_subtask_id=subtask.id,
            agent=agent,
        )
        toolkit.set_task_state(self._task_state)

        for tool in toolkit.get_tools():
            agent.add_tool(tool)

        logger.info(
            f"[AMITaskExecutor] Injected replan tools for subtask {subtask.id}"
        )
        return toolkit

    def _remove_replan_tools(self, agent: "AMIAgent") -> None:
        """Remove ReplanToolkit tools from agent after subtask completes."""
        for name in self._REPLAN_TOOL_NAMES:
            agent.remove_tool(name)

    def _build_prompt(self, subtask: AMISubtask, browser_context: Optional[str] = None) -> str:
        """
        Build the execution prompt for a subtask.

        The workflow_guide is injected as an explicit instruction,
        not just as metadata. This ensures the LLM follows the steps.
        """
        parts = []

        # Browser state — tell agent where the browser currently is
        if browser_context:
            parts.append(f"## Current Browser State\n{browser_context}\n\nThe browser is already open on this page. You do NOT need to navigate here again — start working directly.")

        # Task content - this is the ONLY thing the agent should focus on
        parts.append(f"## Your Task\n{subtask.content}")

        # Workflow guide - as reference context
        if subtask.workflow_guide:
            parts.append(f"""
## Reference: Historical Workflow

The following is a workflow from a SIMILAR past task. Use it as background reference, NOT as a step-by-step instruction.

{subtask.workflow_guide}

**Important**:
- Your current task is ONLY what's described in "Your Task" above
- This workflow covers the ENTIRE original task, but you are only responsible for YOUR subtask
- Use this workflow to understand context (e.g. which site to visit, what elements look like)
- Do NOT execute steps that go beyond your assigned task
- When your specific task is complete, STOP immediately
""")
        else:
            parts.append("""
## Note
No historical workflow guide available. Please explore and complete the task using your best judgment.
""")

        # Previous results from dependencies
        dep_results = []
        logger.info(
            f"[AMITaskExecutor] _build_prompt for subtask {subtask.id}: "
            f"depends_on={subtask.depends_on}"
        )
        for dep_id in subtask.depends_on:
            dep = self._subtask_map.get(dep_id)
            if dep is None:
                logger.warning(
                    f"[AMITaskExecutor] Dependency '{dep_id}' NOT FOUND in _subtask_map "
                    f"(map keys: {list(self._subtask_map.keys())[:20]})"
                )
            elif not dep.result:
                logger.warning(
                    f"[AMITaskExecutor] Dependency '{dep_id}' found but has NO RESULT "
                    f"(status={getattr(dep, 'status', 'unknown')})"
                )
            else:
                logger.info(
                    f"[AMITaskExecutor] Dependency '{dep_id}' has result "
                    f"({len(dep.result)} chars)"
                )
                if len(dep.result) > 2000:
                    # Large result: write to workspace file, inject file reference
                    file_ref = self._save_result_to_file(dep_id, dep.result)
                    dep_results.append(
                        f"### Result from task '{dep_id}':\n"
                        f"Result saved to file: {file_ref}\n"
                        f"Use `read_file` to read the full data."
                    )
                else:
                    dep_results.append(f"### Result from task '{dep_id}':\n{dep.result}")

        if dep_results:
            logger.info(
                f"[AMITaskExecutor] Injecting {len(dep_results)} dependency results "
                f"into prompt for subtask {subtask.id}"
            )
            parts.append("## Results from Previous Tasks\n" + "\n\n".join(dep_results))
        else:
            logger.warning(
                f"[AMITaskExecutor] NO dependency results injected for subtask {subtask.id} "
                f"(depends_on={subtask.depends_on})"
            )

        # Workspace files — let agent know what data is available
        workspace_listing = self._get_workspace_listing()
        if workspace_listing:
            parts.append(
                f"## Workspace Files\n"
                f"The following files were created by earlier tasks. "
                f"Use `read_file` to read files, or `list_files` to list contents.\n\n"
                f"```\n{workspace_listing}\n```"
            )

        # Replan instruction — guide agent to split large tasks
        parts.append(REPLAN_INSTRUCTION)

        return "\n\n".join(parts)

    def _save_result_to_file(self, subtask_id: str, result: str) -> str:
        """Save large subtask result to a file in workspace.

        Returns:
            The relative filename (shell_exec cwd is already workspace).

        Raises:
            RuntimeError: If no WorkingDirectoryManager is available.
        """
        from ..workspace import get_current_manager

        manager = get_current_manager()
        if not manager:
            raise RuntimeError(
                f"WorkingDirectoryManager required to save result for {subtask_id}"
            )

        file_name = f"{subtask_id}_result.md"
        file_path = manager.workspace / file_name
        file_path.write_text(result, encoding="utf-8")
        logger.info(
            f"[AMITaskExecutor] Saved large result for {subtask_id} "
            f"to {file_path} ({len(result)} chars)"
        )
        return file_name

    def _get_workspace_listing(self) -> Optional[str]:
        """List files in workspace for prompt injection.

        Returns a compact file listing so the agent knows what data
        is available from earlier tasks without an extra tool call.
        """
        from ..workspace import get_current_manager

        manager = get_current_manager()
        if not manager:
            return None

        workspace_dir = manager.workspace
        if not workspace_dir.exists():
            return None

        files = sorted(workspace_dir.iterdir())
        if not files:
            return None

        lines = []
        for f in files:
            if f.is_file():
                size_kb = f.stat().st_size / 1024
                lines.append(f"{f.name} ({size_kb:.1f}KB)")

        return "\n".join(lines) if lines else None

    # =========================================================================
    # Provider Retry Notification
    # =========================================================================

    def _setup_retry_notification(self, agent: "AMIAgent", subtask: AMISubtask) -> None:
        """Wire up provider retry callback to emit SSE events."""
        provider = getattr(agent, '_provider', None)
        if provider is None or not hasattr(provider, 'set_on_retry_callback'):
            return

        progress = self._get_subtask_progress(subtask)

        lang = self._lang

        async def on_retry(attempt: int, max_retries: int, delay: float, error_msg: str) -> None:
            if not self._task_state:
                return
            await self._task_state.put_event(AgentReportData(
                task_id=self.task_id,
                message=t("executor.api_retry", lang,
                          progress=progress, attempt=attempt,
                          max_retries=max_retries, delay=f"{delay:.0f}"),
                report_type="warning",
            ))

        provider.set_on_retry_callback(on_retry)

    def _classify_error(self, error_msg: str) -> str:
        """Classify error into user-friendly category."""
        if not error_msg:
            return ""
        lang = self._lang
        lower = error_msg.lower()
        if any(kw in lower for kw in ("connection", "timeout", "timed out", "network", "unreachable", "dns")):
            return t("executor.error.network", lang)
        if any(kw in lower for kw in ("429", "rate limit", "too many requests")):
            return t("executor.error.rate_limit", lang)
        if any(kw in lower for kw in ("500", "502", "503", "504", "internal server error")):
            return t("executor.error.server", lang)
        if any(kw in lower for kw in ("400", "bad request")):
            return t("executor.error.bad_request", lang)
        if any(kw in lower for kw in ("401", "unauthorized", "authentication")):
            return t("executor.error.unauthorized", lang)
        return t("executor.error.unexpected", lang)

    # =========================================================================
    # SSE Event Emission
    # =========================================================================

    def _get_subtask_progress(self, subtask: AMISubtask) -> str:
        """Get [index/total] progress string for a subtask."""
        total = len(self._subtasks)
        try:
            index = next(i for i, s in enumerate(self._subtasks, 1) if s.id == subtask.id)
        except StopIteration:
            index = 0
        return f"[{index}/{total}]"

    async def _emit_subtask_running(self, subtask: AMISubtask) -> None:
        """Emit events when subtask starts running."""
        if not self._task_state:
            return

        # Get agent name for display
        agent = self._agents.get(subtask.agent_type)
        agent_name = getattr(agent, 'agent_name', subtask.agent_type)

        # Report: Subtask starting with progress counter
        progress = self._get_subtask_progress(subtask)
        content_preview = subtask.content[:80]
        if len(subtask.content) > 80:
            content_preview += "..."
        await self._task_state.put_event(AgentReportData(
            task_id=self.task_id,
            message=t("executor.running", self._lang,
                      progress=progress, preview=html_mod.escape(content_preview)),
            report_type="info",
        ))

        # Emit assign_task event (for compatibility)
        await self._task_state.put_event(AssignTaskData(
            task_id=self.task_id,
            assignee_id=subtask.agent_type,
            subtask_id=subtask.id,
            content=subtask.content,
            state="running",
            failure_count=subtask.retry_count,
            worker_name=agent_name,
            agent_type=subtask.agent_type,
            agent_id=subtask.agent_type,
        ))

        # Emit subtask state
        await self._task_state.put_event(SubtaskStateData(
            task_id=self.task_id,
            subtask_id=subtask.id,
            state="RUNNING",
        ))

    async def _emit_subtask_state(self, subtask: AMISubtask) -> None:
        """Emit SSE event for subtask state change."""
        if not self._task_state:
            return

        # Report: Subtask state change with progress counter
        progress = self._get_subtask_progress(subtask)
        content_preview = subtask.content[:50]
        if len(subtask.content) > 50:
            content_preview += "..."
        safe_preview = html_mod.escape(content_preview)

        if subtask.state == SubtaskState.DONE:
            await self._task_state.put_event(AgentReportData(
                task_id=self.task_id,
                message=t("executor.completed", self._lang,
                          progress=progress, preview=safe_preview),
                report_type="success",
            ))
        elif subtask.state == SubtaskState.FAILED:
            # Classify error for user-friendly message
            error_hint = self._classify_error(subtask.error) if subtask.error else ""
            error_suffix = f" ({error_hint})" if error_hint else ""
            await self._task_state.put_event(AgentReportData(
                task_id=self.task_id,
                message=t("executor.failed", self._lang,
                          progress=progress, preview=safe_preview,
                          error_suffix=error_suffix),
                report_type="error",
            ))

        await self._task_state.put_event(SubtaskStateData(
            task_id=self.task_id,
            subtask_id=subtask.id,
            state=subtask.state.value,
        ))

    # =========================================================================
    # Pause/Resume/Stop Control
    # =========================================================================

    async def _wait_if_paused(self) -> None:
        """Wait if execution is paused."""
        if self._paused:
            logger.info(f"[AMITaskExecutor] Waiting (paused)")
            await self._pause_event.wait()

    def pause(self) -> None:
        """Pause execution."""
        self._paused = True
        self._pause_event.clear()
        logger.info(f"[AMITaskExecutor] Paused")

    def resume(self) -> None:
        """Resume execution."""
        self._paused = False
        self._pause_event.set()
        logger.info(f"[AMITaskExecutor] Resumed")

    def stop(self) -> None:
        """Stop execution."""
        self._stopped = True
        self._pause_event.set()  # Unblock if paused
        logger.info(f"[AMITaskExecutor] Stopped")

    @property
    def is_paused(self) -> bool:
        """Check if executor is paused."""
        return self._paused

    @property
    def is_stopped(self) -> bool:
        """Check if executor is stopped."""
        return self._stopped

    # =========================================================================
    # Progress Tracking
    # =========================================================================

    def get_progress(self) -> Dict[str, int]:
        """Get execution progress."""
        counts = {
            "total": len(self._subtasks),
            "pending": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
        }

        for subtask in self._subtasks:
            if subtask.state == SubtaskState.PENDING:
                counts["pending"] += 1
            elif subtask.state == SubtaskState.RUNNING:
                counts["running"] += 1
            elif subtask.state == SubtaskState.DONE:
                counts["done"] += 1
            elif subtask.state == SubtaskState.FAILED:
                counts["failed"] += 1

        return counts

    def get_subtask(self, subtask_id: str) -> Optional[AMISubtask]:
        """Get a subtask by ID."""
        return self._subtask_map.get(subtask_id)

    def get_results(self) -> Dict[str, Optional[str]]:
        """Get all subtask results."""
        return {s.id: s.result for s in self._subtasks}
