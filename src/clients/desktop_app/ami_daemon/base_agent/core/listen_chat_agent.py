"""
ListenChatAgent - CAMEL ChatAgent with SSE event emission.

Ported from Eigent's ListenChatAgent to work with AMI's TaskState event system.
This agent wraps CAMEL's ChatAgent to emit SSE events for:
- Agent activation/deactivation
- Toolkit activation/deactivation
- Budget warnings
"""

import asyncio
import json
import logging
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from camel.agents import ChatAgent
from camel.agents.chat_agent import (
    StreamingChatAgentResponse,
    AsyncStreamingChatAgentResponse,
)
from camel.agents._types import ToolCallRequest
from camel.memories import AgentMemory
from camel.messages import BaseMessage
from camel.models import BaseModelBackend, ModelManager, ModelProcessingError
from camel.responses import ChatAgentResponse
from camel.terminators import ResponseTerminator
from camel.toolkits import FunctionTool, RegisteredAgentToolkit
from camel.types.agents import ToolCallingRecord
from camel.types import ModelPlatformType, ModelType

from ..events import (
    ActivateAgentData,
    DeactivateAgentData,
    ActivateToolkitData,
    DeactivateToolkitData,
    NoticeData,
)

logger = logging.getLogger(__name__)


class ListenChatAgent(ChatAgent):
    """
    CAMEL ChatAgent with SSE event emission for AMI.

    This agent extends CAMEL's ChatAgent to:
    - Emit activate_agent/deactivate_agent events on step()
    - Emit activate_toolkit/deactivate_toolkit events on tool execution
    - Handle budget exceeded errors
    - Support streaming responses with proper event emission

    Unlike Eigent's version which uses get_task_lock(), this uses
    a TaskState instance directly for event emission.
    """

    def __init__(
        self,
        task_state: Any,  # TaskState from quick_task_service
        agent_name: str,
        system_message: BaseMessage | str | None = None,
        model: (
            BaseModelBackend
            | ModelManager
            | Tuple[str, str]
            | str
            | ModelType
            | Tuple[ModelPlatformType, ModelType]
            | List[BaseModelBackend]
            | List[str]
            | List[ModelType]
            | List[Tuple[str, str]]
            | List[Tuple[ModelPlatformType, ModelType]]
            | None
        ) = None,
        memory: AgentMemory | None = None,
        message_window_size: int | None = None,
        token_limit: int | None = None,
        output_language: str | None = None,
        tools: List[FunctionTool | Callable[..., Any]] | None = None,
        toolkits_to_register_agent: List[RegisteredAgentToolkit] | None = None,
        external_tools: (
            List[FunctionTool | Callable[..., Any] | Dict[str, Any]] | None
        ) = None,
        response_terminators: List[ResponseTerminator] | None = None,
        scheduling_strategy: str = "round_robin",
        max_iteration: int | None = None,
        agent_id: str | None = None,
        stop_event: Event | None = None,
        tool_execution_timeout: float | None = None,
        mask_tool_output: bool = False,
        pause_event: asyncio.Event | None = None,
        prune_tool_calls_from_memory: bool = False,
        enable_snapshot_clean: bool = False,
        step_timeout: float | None = 900,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            system_message=system_message,
            model=model,
            memory=memory,
            message_window_size=message_window_size,
            token_limit=token_limit,
            output_language=output_language,
            tools=tools,
            toolkits_to_register_agent=toolkits_to_register_agent,
            external_tools=external_tools,
            response_terminators=response_terminators,
            scheduling_strategy=scheduling_strategy,
            max_iteration=max_iteration,
            agent_id=agent_id,
            stop_event=stop_event,
            tool_execution_timeout=tool_execution_timeout,
            mask_tool_output=mask_tool_output,
            pause_event=pause_event,
            prune_tool_calls_from_memory=prune_tool_calls_from_memory,
            enable_snapshot_clean=enable_snapshot_clean,
            step_timeout=step_timeout,
            **kwargs,
        )
        self._task_state = task_state
        self.agent_name = agent_name
        self.process_task_id: str = ""

        logger.info(f"[ListenChatAgent] Created: {agent_name}, agent_id={agent_id}")

    def set_task_state(self, task_state: Any) -> None:
        """Update the task state for event emission."""
        self._task_state = task_state

    async def _emit_event(self, event: Any) -> None:
        """Emit an event via task state."""
        if self._task_state and hasattr(self._task_state, 'put_event'):
            await self._task_state.put_event(event)

    def step(
        self,
        input_message: BaseMessage | str,
        response_format: type[BaseModel] | None = None,
    ) -> ChatAgentResponse | StreamingChatAgentResponse:
        """Execute a step with SSE event emission."""
        task_id = self._task_state.task_id if self._task_state else None

        # Emit activation event
        asyncio.create_task(self._emit_event(ActivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=(
                input_message.content
                if isinstance(input_message, BaseMessage)
                else input_message
            )[:500],
        )))

        error_info = None
        message = None
        res = None
        total_tokens = 0

        logger.debug(f"[ListenChatAgent] {self.agent_name} starting step")

        try:
            res = super().step(input_message, response_format)
        except ModelProcessingError as e:
            res = None
            error_info = e
            if "Budget has been exceeded" in str(e):
                message = "Budget has been exceeded"
                logger.warning(f"[ListenChatAgent] {self.agent_name} budget exceeded")
                asyncio.create_task(self._emit_event(NoticeData(
                    task_id=task_id,
                    level="error",
                    title="Budget Exceeded",
                    message="The budget for this task has been exceeded",
                )))
            else:
                message = str(e)
                logger.error(f"[ListenChatAgent] {self.agent_name} model error: {e}")
        except Exception as e:
            res = None
            error_info = e
            logger.error(f"[ListenChatAgent] {self.agent_name} error: {e}", exc_info=True)
            message = f"Error processing message: {e!s}"

        if res is not None:
            if isinstance(res, StreamingChatAgentResponse):
                # Wrap streaming response to emit deactivation at end
                def _stream_with_deactivate():
                    last_response: ChatAgentResponse | None = None
                    accumulated_content = ""
                    try:
                        for chunk in res:
                            last_response = chunk
                            if chunk.msg and chunk.msg.content:
                                accumulated_content += chunk.msg.content
                            yield chunk
                    finally:
                        tokens = 0
                        if last_response:
                            usage_info = (
                                last_response.info.get("usage")
                                or last_response.info.get("token_usage")
                                or {}
                            )
                            if usage_info:
                                tokens = usage_info.get("total_tokens", 0)
                        asyncio.create_task(self._emit_event(DeactivateAgentData(
                            task_id=task_id,
                            agent_name=self.agent_name,
                            agent_id=self.agent_id,
                            process_task_id=self.process_task_id,
                            message=accumulated_content[:500],
                            total_tokens=tokens,
                        )))

                return StreamingChatAgentResponse(_stream_with_deactivate())

            message = res.msg.content if res.msg else ""
            usage_info = res.info.get("usage") or res.info.get("token_usage") or {}
            total_tokens = usage_info.get("total_tokens", 0) if usage_info else 0
            logger.info(f"[ListenChatAgent] {self.agent_name} completed, tokens={total_tokens}")

        assert message is not None

        # Emit deactivation event
        asyncio.create_task(self._emit_event(DeactivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=message[:500] if message else "",
            total_tokens=total_tokens,
        )))

        if error_info is not None:
            raise error_info
        assert res is not None
        return res

    async def astep(
        self,
        input_message: BaseMessage | str,
        response_format: type[BaseModel] | None = None,
    ) -> ChatAgentResponse | AsyncStreamingChatAgentResponse:
        """Execute an async step with SSE event emission."""
        task_id = self._task_state.task_id if self._task_state else None

        # Emit activation event
        await self._emit_event(ActivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=(
                input_message.content
                if isinstance(input_message, BaseMessage)
                else input_message
            )[:500],
        ))

        error_info = None
        message = None
        res = None
        total_tokens = 0

        logger.debug(f"[ListenChatAgent] {self.agent_name} starting async step")

        try:
            res = await super().astep(input_message, response_format)
            if isinstance(res, AsyncStreamingChatAgentResponse):
                res = await res._get_final_response()
        except ModelProcessingError as e:
            res = None
            error_info = e
            if "Budget has been exceeded" in str(e):
                message = "Budget has been exceeded"
                logger.warning(f"[ListenChatAgent] {self.agent_name} budget exceeded")
                await self._emit_event(NoticeData(
                    task_id=task_id,
                    level="error",
                    title="Budget Exceeded",
                    message="The budget for this task has been exceeded",
                ))
            else:
                message = str(e)
                logger.error(f"[ListenChatAgent] {self.agent_name} model error: {e}")
        except Exception as e:
            res = None
            error_info = e
            logger.error(f"[ListenChatAgent] {self.agent_name} async error: {e}", exc_info=True)
            message = f"Error processing message: {e!s}"

        if res is not None:
            message = res.msg.content if res.msg else ""
            usage_info = res.info.get("usage") or res.info.get("token_usage") or {}
            total_tokens = usage_info.get("total_tokens", 0)
            logger.info(f"[ListenChatAgent] {self.agent_name} completed, tokens={total_tokens}")

        assert message is not None

        # Emit deactivation event
        await self._emit_event(DeactivateAgentData(
            task_id=task_id,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            process_task_id=self.process_task_id,
            message=message[:500] if message else "",
            total_tokens=total_tokens,
        ))

        if error_info is not None:
            raise error_info
        assert res is not None
        return res

    def _execute_tool(self, tool_call_request: ToolCallRequest) -> ToolCallingRecord:
        """Execute a tool with SSE event emission."""
        func_name = tool_call_request.tool_name
        tool: FunctionTool = self._internal_tools[func_name]
        task_id = self._task_state.task_id if self._task_state else None

        # Route async functions to async execution
        if asyncio.iscoroutinefunction(tool.func):
            return asyncio.run(self._aexecute_tool(tool_call_request))

        args = tool_call_request.args
        tool_call_id = tool_call_request.tool_call_id

        # Check for @listen_toolkit decorator
        has_listen_decorator = hasattr(tool.func, "__wrapped__")

        try:
            toolkit_name = (
                getattr(tool, "_toolkit_name")
                if hasattr(tool, "_toolkit_name")
                else "unknown_toolkit"
            )

            logger.debug(f"[ListenChatAgent] {self.agent_name} executing tool: {func_name}")

            # Emit activation if not handled by decorator
            if not has_listen_decorator:
                asyncio.create_task(self._emit_event(ActivateToolkitData(
                    task_id=task_id,
                    agent_name=self.agent_name,
                    toolkit_name=toolkit_name,
                    method_name=func_name,
                    message=json.dumps(args, ensure_ascii=False)[:500],
                )))

            raw_result = tool(**args)

            if self.mask_tool_output:
                self._secure_result_store[tool_call_id] = raw_result
                result = "[Tool executed successfully, output masked]"
                mask_flag = True
            else:
                result = raw_result
                mask_flag = False

            # Prepare result message
            if isinstance(result, str):
                result_msg = result[:500]
            else:
                result_str = repr(result)
                result_msg = result_str[:500]

            # Emit deactivation if not handled by decorator
            if not has_listen_decorator:
                asyncio.create_task(self._emit_event(DeactivateToolkitData(
                    task_id=task_id,
                    agent_name=self.agent_name,
                    toolkit_name=toolkit_name,
                    method_name=func_name,
                    message=result_msg,
                )))

        except Exception as e:
            error_msg = f"Error executing tool '{func_name}': {e!s}"
            result = f"Tool execution failed: {error_msg}"
            mask_flag = False
            logger.error(f"[ListenChatAgent] Tool execution failed: {e}", exc_info=True)

        return self._record_tool_calling(
            func_name,
            args,
            result,
            tool_call_id,
            mask_output=mask_flag,
            extra_content=tool_call_request.extra_content,
        )

    async def _aexecute_tool(self, tool_call_request: ToolCallRequest) -> ToolCallingRecord:
        """Execute a tool asynchronously with SSE event emission."""
        func_name = tool_call_request.tool_name
        tool: FunctionTool = self._internal_tools[func_name]
        task_id = self._task_state.task_id if self._task_state else None
        args = tool_call_request.args
        tool_call_id = tool_call_request.tool_call_id

        # Get toolkit name
        toolkit_name = None
        if hasattr(tool, "_toolkit_name"):
            toolkit_name = tool._toolkit_name
        elif hasattr(tool, "func") and hasattr(tool.func, "__self__"):
            toolkit_instance = tool.func.__self__
            if hasattr(toolkit_instance, "toolkit_name") and callable(toolkit_instance.toolkit_name):
                toolkit_name = toolkit_instance.toolkit_name()
        if not toolkit_name:
            toolkit_name = "unknown_toolkit"

        logger.debug(f"[ListenChatAgent] {self.agent_name} executing async tool: {func_name}")

        # Emit activation event
        await self._emit_event(ActivateToolkitData(
            task_id=task_id,
            agent_name=self.agent_name,
            toolkit_name=toolkit_name,
            method_name=func_name,
            message=json.dumps(args, ensure_ascii=False)[:500],
        ))

        try:
            # Execute tool based on its type
            if hasattr(tool, "func") and hasattr(tool.func, "async_call"):
                if hasattr(tool, "is_async") and not tool.is_async:
                    result = tool(**args)
                    if asyncio.iscoroutine(result):
                        result = await result
                else:
                    result = await tool.func.async_call(**args)
            elif hasattr(tool, "async_call") and callable(tool.async_call):
                if hasattr(tool, "is_async") and not tool.is_async:
                    result = tool(**args)
                    if asyncio.iscoroutine(result):
                        result = await result
                else:
                    result = await tool.async_call(**args)
            elif hasattr(tool, "func") and asyncio.iscoroutinefunction(tool.func):
                result = await tool.func(**args)
            elif asyncio.iscoroutinefunction(tool):
                result = await tool(**args)
            else:
                result = tool(**args)
                if asyncio.iscoroutine(result):
                    result = await result

        except Exception as e:
            error_msg = f"Error executing async tool '{func_name}': {e!s}"
            result = {"error": error_msg}
            logger.error(f"[ListenChatAgent] Async tool execution failed: {e}", exc_info=True)

        # Prepare result message
        if isinstance(result, str):
            result_msg = result[:500]
        else:
            result_str = repr(result)
            result_msg = result_str[:500]

        # Emit deactivation event
        await self._emit_event(DeactivateToolkitData(
            task_id=task_id,
            agent_name=self.agent_name,
            toolkit_name=toolkit_name,
            method_name=func_name,
            message=result_msg,
        ))

        return self._record_tool_calling(
            func_name,
            args,
            result,
            tool_call_id,
            extra_content=tool_call_request.extra_content,
        )

    def clone(self, with_memory: bool = False) -> ChatAgent:
        """Clone the agent."""
        system_message = None if with_memory else self._original_system_message
        cloned_tools, toolkits_to_register = self._clone_tools()

        new_agent = ListenChatAgent(
            task_state=self._task_state,
            agent_name=self.agent_name,
            system_message=system_message,
            model=self.model_backend.models,
            memory=None,
            message_window_size=getattr(self.memory, "window_size", None),
            token_limit=getattr(self.memory.get_context_creator(), "token_limit", None),
            output_language=self._output_language,
            tools=cloned_tools,
            toolkits_to_register_agent=toolkits_to_register,
            external_tools=[schema for schema in self._external_tool_schemas.values()],
            response_terminators=self.response_terminators,
            scheduling_strategy=self.model_backend.scheduling_strategy.__name__,
            max_iteration=self.max_iteration,
            stop_event=self.stop_event,
            tool_execution_timeout=self.tool_execution_timeout,
            mask_tool_output=self.mask_tool_output,
            pause_event=self.pause_event,
            prune_tool_calls_from_memory=self.prune_tool_calls_from_memory,
            step_timeout=self.step_timeout,
        )

        new_agent.process_task_id = self.process_task_id

        if with_memory:
            context_records = self.memory.retrieve()
            for context_record in context_records:
                new_agent.memory.write_record(context_record.memory_record)

        return new_agent
