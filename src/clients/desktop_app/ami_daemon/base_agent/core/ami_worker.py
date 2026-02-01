"""
AMI Single Agent Worker - Extends CAMEL SingleAgentWorker for AMI.

Ported from Eigent's SingleAgentWorker to work with AMI's event system.
This worker wraps ListenChatAgent for Workforce execution.
"""

import datetime
import logging
from typing import Any, List, Optional

from camel.agents.chat_agent import AsyncStreamingChatAgentResponse
from camel.societies.workforce.single_agent_worker import (
    SingleAgentWorker as BaseSingleAgentWorker,
)
from camel.societies.workforce.prompts import PROCESS_TASK_PROMPT
from camel.societies.workforce.utils import TaskResult
from camel.tasks.task import Task, TaskState, is_task_result_insufficient
from camel.utils.context_utils import ContextUtility

from .listen_chat_agent import ListenChatAgent
from ..events import (
    SubtaskStateData,
    WorkerAssignedData,
    WorkerStartedData,
    WorkerCompletedData,
    WorkerFailedData,
)

logger = logging.getLogger(__name__)


class AMISingleAgentWorker(BaseSingleAgentWorker):
    """
    AMI's SingleAgentWorker that wraps ListenChatAgent for Workforce.

    This worker:
    - Extends CAMEL's SingleAgentWorker
    - Uses ListenChatAgent for SSE event emission
    - Emits worker_assigned, worker_started, worker_completed events
    - Handles structured output parsing

    Ported from Eigent's SingleAgentWorker with AMI adaptations.
    """

    def __init__(
        self,
        description: str,
        worker: ListenChatAgent,
        task_state: Optional[Any] = None,
        use_agent_pool: bool = True,
        pool_initial_size: int = 1,
        pool_max_size: int = 10,
        auto_scale_pool: bool = True,
        use_structured_output_handler: bool = True,
        context_utility: Optional[ContextUtility] = None,
        enable_workflow_memory: bool = False,
    ) -> None:
        """
        Initialize AMISingleAgentWorker.

        Args:
            description: Worker description (used for task assignment)
            worker: ListenChatAgent instance
            task_state: TaskState for additional event emission
            use_agent_pool: Whether to use agent pooling
            pool_initial_size: Initial pool size
            pool_max_size: Maximum pool size
            auto_scale_pool: Whether to auto-scale pool
            use_structured_output_handler: Use structured output parsing
            context_utility: Context utility for memory
            enable_workflow_memory: Enable workflow memory
        """
        logger.info(f"[AMISingleAgentWorker] Initializing: {description}")
        logger.info(f"[AMISingleAgentWorker] Worker agent: {worker.agent_name}")

        super().__init__(
            description=description,
            worker=worker,
            use_agent_pool=use_agent_pool,
            pool_initial_size=pool_initial_size,
            pool_max_size=pool_max_size,
            auto_scale_pool=auto_scale_pool,
            use_structured_output_handler=use_structured_output_handler,
            context_utility=context_utility,
            enable_workflow_memory=enable_workflow_memory,
        )

        self.worker = worker  # Type hint override
        self._task_state = task_state

    def set_task_state(self, task_state: Any) -> None:
        """Set task state for event emission."""
        self._task_state = task_state
        if hasattr(self.worker, 'set_task_state'):
            self.worker.set_task_state(task_state)

    async def _emit_event(self, event: Any) -> None:
        """Emit SSE event via task state."""
        if self._task_state and hasattr(self._task_state, 'put_event'):
            await self._task_state.put_event(event)

    async def _process_task(self, task: Task, dependencies: List[Task]) -> TaskState:
        """
        Process a task with SSE event emission.

        Overrides parent to add AMI-specific event emission.

        Args:
            task: The task to process
            dependencies: Completed dependency tasks

        Returns:
            TaskState.DONE or TaskState.FAILED
        """
        task_id = self._task_state.task_id if self._task_state else None

        # Emit worker_started event
        await self._emit_event(WorkerStartedData(
            task_id=task_id,
            worker_name=self.worker.agent_name,
            worker_id=self.worker.agent_id,
            subtask_id=task.id,
        ))

        # Emit subtask state: RUNNING
        await self._emit_event(SubtaskStateData(
            task_id=task_id,
            subtask_id=task.id,
            state="RUNNING",
        ))

        logger.info(f"[AMISingleAgentWorker] Processing task: {task.id}")

        response_content = ""
        final_response = None
        start_time = datetime.datetime.now()

        try:
            # Check if the ORIGINAL worker has execute() method (e.g., ListenBrowserAgent)
            # We check self.worker instead of clone because clone might lose the execute() method
            if hasattr(self.worker, 'execute') and callable(getattr(self.worker, 'execute')):
                # Use the original worker directly for agents with execute() method
                # These agents have internal task decomposition and execution loops
                # and should not be cloned as it would lose browser session state
                worker_agent = self.worker
                worker_agent.process_task_id = task.id

                # Pass workflow_guide to agent before execution
                # This is needed because execute() only receives task.content
                if hasattr(worker_agent, 'set_memory_context') and task.additional_info:
                    workflow_guide = task.additional_info.get('workflow_guide')
                    memory_level = task.additional_info.get('memory_level', 'L3')
                    if workflow_guide:
                        worker_agent.set_memory_context(
                            memory_result=None,  # Not needed, workflow_guide is pre-formatted
                            memory_level=memory_level,
                            workflow_guide=workflow_guide,
                        )
                        logger.info(
                            f"[AMISingleAgentWorker] Set memory context for {type(worker_agent).__name__}: "
                            f"level={memory_level}, workflow_guide_len={len(workflow_guide)}"
                        )

                # Use agent's specialized execute() method
                logger.info(
                    f"[AMISingleAgentWorker] Using {type(worker_agent).__name__}.execute() "
                    f"for task {task.id}"
                )
                result_content = await worker_agent.execute(task.content)

                # Convert result to TaskResult format
                task_result = TaskResult(
                    content=result_content if result_content else "Task completed",
                    failed=False,  # If execute() completes without exception, assume success
                )
                response_content = result_content or ""
                total_tokens = 0  # execute() handles its own token tracking
            else:
                # Standard flow: use cloned agent with astep() for regular agents
                worker_agent = await self._get_worker_agent()
                worker_agent.process_task_id = task.id

                dependency_tasks_info = self._get_dep_tasks_info(dependencies)
                prompt = PROCESS_TASK_PROMPT.format(
                    content=task.content,
                    parent_task_content=task.parent.content if task.parent else "",
                    dependency_tasks_info=dependency_tasks_info,
                    additional_info=task.additional_info,
                )

                if self.use_structured_output_handler and self.structured_handler:
                    # Use structured output handler
                    enhanced_prompt = self.structured_handler.generate_structured_prompt(
                        base_prompt=prompt,
                        schema=TaskResult,
                        examples=[
                            {
                                "content": "I have successfully completed the task...",
                                "failed": False,
                            }
                        ],
                        additional_instructions=(
                            "Ensure you provide a clear description of what was done "
                            "and whether the task succeeded or failed."
                        ),
                    )
                    response = await worker_agent.astep(enhanced_prompt)

                    # Handle streaming response
                    if isinstance(response, AsyncStreamingChatAgentResponse):
                        accumulated_content = ""
                        async for chunk in response:
                            if chunk.msg and chunk.msg.content:
                                accumulated_content += chunk.msg.content
                        response_content = accumulated_content
                    else:
                        response_content = response.msg.content if response.msg else ""

                    task_result = self.structured_handler.parse_structured_response(
                        response_text=response_content,
                        schema=TaskResult,
                        fallback_values={
                            "content": "Task processing failed",
                            "failed": True,
                        },
                    )
                else:
                    # Use native structured output
                    response = await worker_agent.astep(prompt, response_format=TaskResult)

                    if isinstance(response, AsyncStreamingChatAgentResponse):
                        task_result = None
                        accumulated_content = ""
                        async for chunk in response:
                            if chunk.msg:
                                if chunk.msg.content:
                                    accumulated_content += chunk.msg.content
                                if chunk.msg.parsed:
                                    task_result = chunk.msg.parsed
                        response_content = accumulated_content
                        if task_result is None:
                            task_result = TaskResult(
                                content="Failed to parse streaming response",
                                failed=True,
                            )
                    else:
                        task_result = response.msg.parsed
                        response_content = response.msg.content if response.msg else ""

                # Get token usage (only for standard flow)
                if isinstance(response, AsyncStreamingChatAgentResponse):
                    final_response = await response
                    usage_info = final_response.info.get("usage") or final_response.info.get("token_usage")
                else:
                    usage_info = response.info.get("usage") or response.info.get("token_usage")
                total_tokens = usage_info.get("total_tokens", 0) if usage_info else 0

            # Transfer memory if enabled
            if self.enable_workflow_memory:
                accumulator = self._get_conversation_accumulator()
                try:
                    work_records = worker_agent.memory.retrieve()
                    memory_records = [record.memory_record for record in work_records]
                    accumulator.memory.write_records(memory_records)
                    logger.debug(f"Transferred {len(memory_records)} memory records")
                except Exception as e:
                    logger.warning(f"Failed to transfer conversation: {e}")

        except Exception as e:
            logger.error(f"[AMISingleAgentWorker] Task {task.id} error: {e}", exc_info=True)
            task.result = f"{type(e).__name__}: {e!s}"

            duration = (datetime.datetime.now() - start_time).total_seconds()

            # Emit failure events
            # BUG-2 fix: Use failure_count instead of retry_count
            await self._emit_event(WorkerFailedData(
                task_id=task_id,
                worker_name=self.worker.agent_name,
                worker_id=self.worker.agent_id,
                subtask_id=task.id,
                error=str(e),
                failure_count=task.failure_count,
                will_retry=task.failure_count < 3,
            ))
            await self._emit_event(SubtaskStateData(
                task_id=task_id,
                subtask_id=task.id,
                state="FAILED",
                result=str(e)[:500],
                failure_count=task.failure_count,
            ))

            return TaskState.FAILED
        finally:
            await self._return_worker_agent(worker_agent)

        # Populate additional_info
        if task.additional_info is None:
            task.additional_info = {}

        response_for_info = final_response if final_response is not None else response
        worker_attempt_details = {
            "agent_id": getattr(worker_agent, "agent_id", worker_agent.role_name),
            "original_worker_id": getattr(self.worker, "agent_id", self.worker.role_name),
            "timestamp": str(datetime.datetime.now()),
            "description": f"Attempt by {getattr(worker_agent, 'agent_id', worker_agent.role_name)}",
            "response_content": response_content[:50] if response_content else "",
            "total_tokens": total_tokens,
        }

        if "worker_attempts" not in task.additional_info:
            task.additional_info["worker_attempts"] = []
        task.additional_info["worker_attempts"].append(worker_attempt_details)
        task.additional_info["token_usage"] = {"total_tokens": total_tokens}

        logger.info(f"[AMISingleAgentWorker] Task {task.id} response: {response_content[:100]}...")

        if not self.use_structured_output_handler:
            if task_result is None:
                logger.error("Invalid task result")
                task_result = TaskResult(
                    content="Failed to generate valid task result.",
                    failed=True,
                )

        duration = (datetime.datetime.now() - start_time).total_seconds()

        if task_result.failed:
            logger.error(f"[AMISingleAgentWorker] Task {task.id} failed: {task_result.content}")
            task.result = task_result.content

            # BUG-2 fix: Use failure_count instead of retry_count
            await self._emit_event(WorkerFailedData(
                task_id=task_id,
                worker_name=self.worker.agent_name,
                worker_id=self.worker.agent_id,
                subtask_id=task.id,
                error=task_result.content,
                failure_count=task.failure_count,
                will_retry=task.failure_count < 3,
            ))
            await self._emit_event(SubtaskStateData(
                task_id=task_id,
                subtask_id=task.id,
                state="FAILED",
                result=task_result.content[:500],
                failure_count=task.failure_count,
            ))

            return TaskState.FAILED

        task.result = task_result.content

        if is_task_result_insufficient(task):
            logger.warning(f"[AMISingleAgentWorker] Task {task.id} content validation failed")

            # BUG-2 fix: Use failure_count instead of retry_count
            await self._emit_event(WorkerFailedData(
                task_id=task_id,
                worker_name=self.worker.agent_name,
                worker_id=self.worker.agent_id,
                subtask_id=task.id,
                error="Content validation failed",
                failure_count=task.failure_count,
            ))

            return TaskState.FAILED

        logger.info(f"[AMISingleAgentWorker] Task {task.id} completed successfully")

        # Emit completion events
        await self._emit_event(WorkerCompletedData(
            task_id=task_id,
            worker_name=self.worker.agent_name,
            worker_id=self.worker.agent_id,
            subtask_id=task.id,
            result_preview=task_result.content[:200] if task_result.content else None,
            duration_seconds=duration,
        ))
        await self._emit_event(SubtaskStateData(
            task_id=task_id,
            subtask_id=task.id,
            state="DONE",
            result=task_result.content[:500] if task_result.content else None,
        ))

        return TaskState.DONE
