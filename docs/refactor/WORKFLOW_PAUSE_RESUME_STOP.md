# Workflow Stop Design

## Overview

This document describes the design for adding stop functionality to the workflow engine.

**Scope**: Only stop functionality. Pause/resume deferred to future iteration due to complexity (checkpoint serialization, loop state recovery, etc.).

## Current Architecture

### Execution Flow

```
API Request → WorkflowExecutor → BaseAgent → WorkflowEngine → Step Agents
                    ↓
              ExecutionTask (state tracking)
              asyncio.create_task (background execution)
```

### Core Components

| Component | File | Responsibility |
|-----------|------|----------------|
| `WorkflowExecutor` | `services/workflow_executor.py` | Task management, background execution |
| `WorkflowEngine` | `base_agent/core/workflow_engine.py` | Step execution loop |
| `AgentContext` | `base_agent/core/schemas.py` | Execution state container |
| `ExecutionTask` | `models/execution.py` | Task status tracking |

### Current Limitations

1. **No external control**: Once started, workflows cannot be interrupted from outside
2. **Limited states**: `ExecutionTask.status` only supports `running`, `completed`, `failed`
3. **Unused enums**: `AgentStatus.PAUSED` and `AgentStatus.STOPPED` exist but are not used

---

## Design Goals

1. **User can stop a running workflow** via API call
2. **Cooperative + forced stop**: Check signal at step boundaries, force cancel after timeout
3. **Clean resource cleanup**: Browser session closed on stop
4. **Minimal code changes**: Leverage existing asyncio patterns

---

## Design Decisions

### Stop Signal Check Level

**Decision**: Check stop signal only at step boundaries (not inside agents).

| Approach | Complexity | Response Time |
|----------|------------|---------------|
| Step boundaries only | Low | Wait for current step to complete (up to timeout) |
| Inside agents | High | Faster, but requires all agents to cooperate |

Rationale: Step boundary checking is simpler and sufficient for most cases. Long-running steps will be force-cancelled after timeout.

### Stop Result Propagation

**Decision**: Add `stopped: bool` field to `WorkflowResult`.

This allows `_execute_workflow` to detect cooperative stop and update task status correctly, avoiding conflict between workflow result handling and stop API status updates.

### CancelledError Handling

**Decision**: `CancelledError` must be re-raised at key execution points to ensure force cancel works.

Layers that must re-raise `CancelledError`:
- `WorkflowEngine.execute_workflow()`
- `WorkflowEngine._execute_agent_step()`
- `WorkflowEngine._execute_while_step()`
- `WorkflowEngine._execute_foreach_step()`
- `WorkflowEngine._execute_if_step()`

Without this, existing `except Exception` blocks will swallow `CancelledError` and force cancel won't work.

### Resource Cleanup

**Decision**: Unified cleanup in `_execute_workflow` finally block.

All exit paths (success, failure, stop, cancel) go through the same cleanup to prevent resource leaks.

---

## Data Structure Changes

### 1. ExecutionTask

```python
# models/execution.py

@dataclass
class ExecutionTask:
    """Workflow execution task"""

    # Existing fields (unchanged)
    task_id: str
    workflow_id: str
    workflow_name: str
    user_id: str
    status: str  # running | stopping | stopped | completed | failed
    progress: int
    current_step: int
    total_steps: int
    message: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)

    # New field
    stopped_at_step: Optional[int] = None  # Step index when stopped
```

### 2. StopSignal

Simple stop signal using `asyncio.Event`:

```python
# base_agent/core/schemas.py

class StopSignal:
    """Signal for stopping workflow execution"""

    def __init__(self):
        self._stop_event = asyncio.Event()

    def request_stop(self):
        """Request workflow to stop"""
        self._stop_event.set()

    def is_stop_requested(self) -> bool:
        """Check if stop was requested"""
        return self._stop_event.is_set()

    def reset(self):
        """Reset the signal"""
        self._stop_event.clear()
```

### 3. WorkflowResult Extension

```python
# base_agent/core/schemas.py

class WorkflowResult(BaseModel):
    # Existing fields...
    success: bool
    workflow_id: str
    steps: List[StepResult]
    error_message: Optional[str]
    total_execution_time: float
    # ...

    # New field
    stopped: bool = Field(default=False, description="Whether workflow was stopped by user request")
```

---

## Execution Flow Changes

### WorkflowEngine Changes

Add stop signal check at step boundaries and proper CancelledError handling:

```python
# base_agent/core/workflow_engine.py

async def execute_workflow(
    self,
    steps: List[AgentWorkflowStep],
    workflow_id: str = None,
    input_data: Dict[str, Any] = None,
    step_callback: Optional[Any] = None,
    log_callback: Optional[Any] = None,
    stop_signal: Optional[StopSignal] = None  # New parameter
) -> WorkflowResult:
    """Execute workflow with stop support"""

    # ... existing initialization ...

    try:
        for step_index, step in enumerate(steps):
            context.step_id = step.id

            # ===== CHECK STOP SIGNAL =====
            if stop_signal and stop_signal.is_stop_requested():
                logger.info(f"Stop requested before step {step_index}: {step.name}")
                return WorkflowResult(
                    success=False,
                    stopped=True,  # New field
                    workflow_id=workflow_id,
                    steps=executed_steps,
                    error_message="Workflow stopped by user request",
                    total_execution_time=time.time() - start_time
                )

            # Notify step start
            if step_callback:
                await step_callback(step_index, step.name, 'in_progress', None)

            # Execute step (pass stop_signal to control flow steps)
            if step.agent_type == "if":
                step_result = await self._execute_if_step(step, context, stop_signal)
            elif step.agent_type == "while":
                step_result = await self._execute_while_step(step, context, stop_signal)
            elif step.agent_type == "foreach":
                step_result = await self._execute_foreach_step(step, context, stop_signal)
            else:
                if step.condition and not await self._evaluate_condition(step.condition, context):
                    continue
                step_result = await self._execute_agent_step(step, context)

            # Check if control flow step was stopped
            if hasattr(step_result, 'exit_reason') and step_result.exit_reason == 'stopped':
                return WorkflowResult(
                    success=False,
                    stopped=True,  # New field
                    workflow_id=workflow_id,
                    steps=executed_steps,
                    error_message="Workflow stopped by user request",
                    total_execution_time=time.time() - start_time
                )

            # ... rest of existing logic ...

    except asyncio.CancelledError:
        # Must re-raise to allow force cancel to work
        logger.info(f"Workflow {workflow_id} cancelled")
        raise

    except Exception as e:
        # ... existing error handling ...
```

### Agent Step with CancelledError Handling

```python
# base_agent/core/workflow_engine.py

async def _execute_agent_step(
    self,
    step: AgentWorkflowStep,
    context: AgentContext
) -> StepResult:
    """Execute agent step with proper cancellation handling"""
    step_start_time = time.time()

    try:
        # ... existing execution logic ...
        result = await self._execute_agent(agent_type, agent_input, context, agent_config)

        return StepResult(
            step_id=step.id,
            success=getattr(result, 'success', True),
            data=result,
            message=f"Agent {agent_type} executed successfully",
            execution_time=time.time() - step_start_time
        )

    except asyncio.CancelledError:
        # Must re-raise - do not catch as regular exception
        logger.info(f"Agent step {step.id} cancelled")
        raise

    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Agent step failed: {str(e)}\n{error_traceback}")
        return StepResult(
            step_id=step.id,
            success=False,
            data=None,
            message=str(e),
            error=error_traceback,
            execution_time=time.time() - step_start_time
        )
```

### Loop Control Flow Changes

Check stop signal at each iteration:

```python
# base_agent/core/workflow_engine.py

async def _execute_while_step(
    self,
    step: AgentWorkflowStep,
    context: AgentContext,
    stop_signal: Optional[StopSignal] = None  # New parameter
) -> StepResult:
    """Execute while loop with stop support"""
    step_start_time = time.time()

    try:
        max_iterations = step.max_iterations
        loop_timeout = step.loop_timeout
        iterations_executed = 0
        sub_step_results = []
        exit_reason = "condition_false"

        while max_iterations is None or iterations_executed < max_iterations:
            # ===== CHECK STOP SIGNAL =====
            if stop_signal and stop_signal.is_stop_requested():
                exit_reason = "stopped"
                logger.info(f"While loop stopped at iteration {iterations_executed}")
                break

            # Timeout check
            if loop_timeout and time.time() - step_start_time > loop_timeout:
                exit_reason = "timeout"
                break

            # Condition check
            condition_result = await self._evaluate_condition(step.condition, context)
            if not condition_result:
                exit_reason = "condition_false"
                break

            # Execute sub-steps
            for sub_step in step.steps:
                sub_result = await self._execute_single_step(sub_step, context, stop_signal)
                sub_step_results.append(sub_result)

                if not sub_result.success:
                    exit_reason = "step_failed"
                    break

            iterations_executed += 1

        return StepResult(
            step_id=step.id,
            success=(exit_reason not in ("stopped", "step_failed")),
            message=f"While loop: {iterations_executed} iterations, exit: {exit_reason}",
            execution_time=time.time() - step_start_time,
            step_type="while",
            iterations_executed=iterations_executed,
            exit_reason=exit_reason,
            sub_step_results=sub_step_results
        )

    except asyncio.CancelledError:
        logger.info(f"While step {step.id} cancelled")
        raise

    except Exception as e:
        # ... error handling ...
```

Similar changes for `_execute_foreach_step()` and `_execute_if_step()`.

### BaseAgent Changes

Pass stop signal through:

```python
# base_agent/core/base_agent.py

async def run_workflow(
    self,
    workflow: Union[Workflow, List[AgentWorkflowStep]],
    input_data: Dict[str, Any] = None,
    step_callback: Optional[Any] = None,
    log_callback: Optional[Any] = None,
    workflow_id: Optional[str] = None,
    stop_signal: Optional[StopSignal] = None  # New parameter
) -> WorkflowResult:
    """Execute workflow with stop support"""

    if isinstance(workflow, list):
        return await self.workflow_engine.execute_workflow(
            workflow,
            workflow_id=workflow_id,
            input_data=input_data or {},
            step_callback=step_callback,
            log_callback=log_callback,
            stop_signal=stop_signal
        )
    else:
        return await self.workflow_engine.execute_workflow(
            workflow.steps,
            workflow_id=workflow_id or workflow.workflow_id or workflow.name,
            input_data=input_data or {},
            step_callback=step_callback,
            log_callback=log_callback,
            stop_signal=stop_signal
        )
```

---

## WorkflowExecutor Changes

```python
# services/workflow_executor.py

class WorkflowExecutor:
    """Execute workflows using BaseAgent"""

    def __init__(self, ...):
        # Existing fields
        self.storage = storage_manager
        self.browser = browser_manager
        self.tasks: Dict[str, ExecutionTask] = {}
        # ...

        # New fields
        self.stop_signals: Dict[str, StopSignal] = {}
        self.task_handles: Dict[str, asyncio.Task] = {}

    async def execute_workflow_async(self, ...) -> Dict[str, str]:
        """Execute workflow asynchronously"""
        task_id = f"task_{workflow_id}_{uuid.uuid4().hex[:8]}"

        # Create stop signal
        stop_signal = StopSignal()
        self.stop_signals[task_id] = stop_signal

        # ... existing task creation ...

        # Store task handle
        task_handle = asyncio.create_task(
            self._execute_workflow(task_id, user_id, workflow_yaml, inputs, user_api_key, stop_signal)
        )
        self.task_handles[task_id] = task_handle

        return {"task_id": task_id, "status": "running"}

    async def stop_workflow(self, task_id: str) -> Dict[str, Any]:
        """Stop a running workflow

        Strategy:
        1. Set stop signal (cooperative stop)
        2. Wait up to STOP_TIMEOUT for graceful stop
        3. If timeout, force cancel the task
        4. Return result (cleanup happens in _execute_workflow finally)

        Args:
            task_id: Task ID to stop

        Returns:
            Dict with success status and details
        """
        STOP_TIMEOUT = 10  # seconds

        # Validate task exists and is running
        task = self.tasks.get(task_id)
        if not task:
            return {"success": False, "error": "Task not found"}

        if task.status not in ("running",):
            return {"success": False, "error": f"Task cannot be stopped (status: {task.status})"}

        stop_signal = self.stop_signals.get(task_id)
        task_handle = self.task_handles.get(task_id)

        if not stop_signal or not task_handle:
            return {"success": False, "error": "Task control not available"}

        # Update status to stopping
        task.status = "stopping"
        task.message = "Stopping workflow..."

        # Send progress update
        await self._send_progress_update(task_id, {
            "type": "progress_update",
            "task_id": task_id,
            "status": "stopping",
            "message": "Stopping workflow...",
            "timestamp": datetime.now().isoformat()
        })

        # Step 1: Request cooperative stop
        stop_signal.request_stop()
        logger.info(f"Stop signal sent for workflow {task_id}")

        # Step 2: Wait for graceful stop with timeout
        try:
            await asyncio.wait_for(task_handle, timeout=STOP_TIMEOUT)
            logger.info(f"Workflow {task_id} stopped gracefully")
        except asyncio.TimeoutError:
            # Step 3: Force cancel
            logger.warning(f"Workflow {task_id} did not stop gracefully, forcing cancel")
            task_handle.cancel()
            try:
                await task_handle
            except asyncio.CancelledError:
                logger.info(f"Workflow {task_id} force cancelled")

        # Note: Cleanup (browser, resources) happens in _execute_workflow finally block

        return {
            "success": True,
            "stopped_at_step": task.stopped_at_step,
            "message": task.message
        }

    def _cleanup_task_resources(self, task_id: str):
        """Cleanup task-related resources (signals, handles, context)"""
        if task_id in self.stop_signals:
            del self.stop_signals[task_id]
        if task_id in self.task_handles:
            del self.task_handles[task_id]
        if task_id in self._task_context:
            del self._task_context[task_id]

    async def _execute_workflow(
        self,
        task_id: str,
        user_id: str,
        workflow_yaml: str,
        inputs: Optional[dict],
        user_api_key: Optional[str],
        stop_signal: StopSignal
    ):
        """Internal execution logic with stop signal support"""
        task = self.tasks[task_id]

        try:
            # ... existing setup (browser, agent creation) ...

            # Execute workflow with stop signal
            result = await agent.run_workflow(
                workflow,
                input_data=inputs or {},
                step_callback=step_progress_callback,
                log_callback=log_callback,
                workflow_id=task.workflow_id,
                stop_signal=stop_signal
            )

            # Handle result based on stopped flag
            if result.stopped:
                # Cooperative stop completed
                task.status = "stopped"
                task.stopped_at_step = task.current_step
                task.completed_at = datetime.now()
                task.message = f"Stopped at step {task.current_step + 1}"

                await self._send_progress_update(task_id, {
                    "type": "progress_update",
                    "task_id": task_id,
                    "status": "stopped",
                    "stopped_at_step": task.stopped_at_step,
                    "message": task.message,
                    "timestamp": datetime.now().isoformat()
                })

            elif result.success:
                # Normal completion
                task.status = "completed"
                task.progress = 100
                task.completed_at = datetime.now()
                task.result = result.final_result
                task.message = "Execution completed"
                # ... existing completion logic ...

            else:
                # Failed
                task.status = "failed"
                task.error = result.error_message
                task.completed_at = datetime.now()
                task.message = f"Failed: {result.error_message}"
                # ... existing failure logic ...

        except asyncio.CancelledError:
            # Force cancellation (from stop_workflow timeout)
            logger.info(f"Workflow {task_id} was force cancelled")
            task.status = "stopped"
            task.stopped_at_step = task.current_step
            task.completed_at = datetime.now()
            task.message = f"Force stopped at step {task.current_step + 1}"

            await self._send_progress_update(task_id, {
                "type": "progress_update",
                "task_id": task_id,
                "status": "stopped",
                "stopped_at_step": task.stopped_at_step,
                "message": task.message,
                "timestamp": datetime.now().isoformat()
            })
            # Do not re-raise - we've handled the cancellation

        except Exception as e:
            # ... existing error handling ...
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now()
            task.message = f"Execution failed: {e}"

        finally:
            # ===== UNIFIED CLEANUP FOR ALL EXIT PATHS =====
            # 1. Cleanup task resources (signals, handles)
            self._cleanup_task_resources(task_id)

            # 2. Close browser session
            session_id = f"workflow_{task_id}"
            try:
                await self.browser.close_workflow_session(session_id)
                logger.info(f"Browser session {session_id} closed")
            except Exception as e:
                logger.warning(f"Failed to close browser session: {e}")

            # 3. Update history if needed
            # ... existing history logic ...
```

---

## API Endpoint

```python
# src/clients/desktop_app/ami_daemon/api/workflow_routes.py (or similar)

@router.post("/api/v1/executions/{task_id}/stop")
async def stop_workflow(task_id: str):
    """Stop a running workflow

    Args:
        task_id: Task ID (format: task_{workflow_id}_{random})

    Returns:
        - success: Whether stop was successful
        - stopped_at_step: Step index where workflow was stopped
        - message: Human-readable status
    """
    result = await executor.stop_workflow(task_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
```

**API Path**: `POST /api/v1/executions/{task_id}/stop`

This is consistent with existing execution APIs:
- `GET /api/v1/executions/{task_id}` - Get task status
- `POST /api/v1/executions/{task_id}/stop` - Stop task (new)

---

## WebSocket Progress Updates

Extend existing progress update format with new status values:

```python
# Status: stopping
{
    "type": "progress_update",
    "task_id": "task_workflow_xxx_abc123",
    "status": "stopping",
    "progress": 45,
    "current_step": 2,
    "total_steps": 5,
    "message": "Stopping workflow...",
    "timestamp": "2024-01-15T10:30:00.000Z"
}

# Status: stopped
{
    "type": "progress_update",
    "task_id": "task_workflow_xxx_abc123",
    "status": "stopped",
    "progress": 45,
    "current_step": 2,
    "total_steps": 5,
    "stopped_at_step": 2,
    "message": "Stopped at step 3",
    "timestamp": "2024-01-15T10:30:05.000Z"
}
```

Frontend should handle these new status values in the existing WebSocket handler and update UI accordingly.

---

## State Transitions

```
┌─────────┐    ┌─────────┐    ┌───────────┐
│ pending │───▶│ running │───▶│ completed │
└─────────┘    └────┬────┘    └───────────┘
                    │
                    │ stop_workflow()
                    ▼
               ┌──────────┐    ┌─────────┐
               │ stopping │───▶│ stopped │
               └──────────┘    └─────────┘

               ┌────────┐
               │ failed │ (from running on error)
               └────────┘
```

---

## Stop Behavior

| Scenario | Behavior |
|----------|----------|
| Stop during step gap | Immediate stop via cooperative signal |
| Stop during agent step | Wait up to 10s for step completion, then force cancel |
| Stop during while/foreach | Exit loop at next iteration boundary |
| Stop after completion | Return error "Task cannot be stopped" |
| Double stop | Second call returns error "Task cannot be stopped (status: stopping)" |

---

## Files to Modify

| File | Changes |
|------|---------|
| `models/execution.py` | Add `stopped_at_step` field |
| `base_agent/core/schemas.py` | Add `StopSignal` class, add `stopped` field to `WorkflowResult` |
| `base_agent/core/workflow_engine.py` | Add stop signal checks, CancelledError handling |
| `base_agent/core/base_agent.py` | Pass stop_signal through run_workflow |
| `services/workflow_executor.py` | Add stop_workflow method, unified cleanup in finally |
| API routes file | Add `POST /api/v1/executions/{task_id}/stop` endpoint |

---

## Implementation Checklist

### Data Structures
- [ ] Add `StopSignal` class to schemas.py
- [ ] Add `stopped: bool` field to `WorkflowResult`
- [ ] Add `stopped_at_step` to `ExecutionTask`

### WorkflowEngine
- [ ] Add `stop_signal` parameter to `execute_workflow()`
- [ ] Add stop signal check before each step
- [ ] Return `WorkflowResult(stopped=True)` when stopped
- [ ] Add `CancelledError` re-raise in `execute_workflow()`
- [ ] Add `CancelledError` re-raise in `_execute_agent_step()`
- [ ] Modify `_execute_while_step()` to accept and check stop_signal
- [ ] Modify `_execute_foreach_step()` to accept and check stop_signal
- [ ] Modify `_execute_if_step()` to pass stop_signal to sub-steps
- [ ] Modify `_execute_single_step()` to accept and pass stop_signal
- [ ] Add `CancelledError` re-raise in all control flow methods

### BaseAgent
- [ ] Add `stop_signal` parameter to `run_workflow()`
- [ ] Pass stop_signal to workflow_engine

### WorkflowExecutor
- [ ] Add `stop_signals: Dict[str, StopSignal]` field
- [ ] Add `task_handles: Dict[str, asyncio.Task]` field
- [ ] Modify `execute_workflow_async()` to create and store stop signal/handle
- [ ] Add `stop_workflow()` method
- [ ] Add `_cleanup_task_resources()` helper
- [ ] Handle `result.stopped` in `_execute_workflow()`
- [ ] Handle `CancelledError` in `_execute_workflow()` (don't re-raise)
- [ ] Move all cleanup to finally block in `_execute_workflow()`

### API
- [ ] Add `POST /api/v1/executions/{task_id}/stop` endpoint

### Frontend
- [ ] Handle "stopping" status in WebSocket handler
- [ ] Handle "stopped" status in WebSocket handler
- [ ] Update stop button to call new API
- [ ] Show appropriate UI state for stopping/stopped

---

## Testing

1. **Unit tests:**
   - StopSignal event behavior
   - WorkflowResult.stopped field
   - State transitions

2. **Integration tests:**
   - Stop between steps (immediate cooperative stop)
   - Stop during loop iteration
   - Stop timeout → force cancel
   - Browser session cleanup after stop
   - Double stop handling
   - Verify no resource leaks (stop_signals, task_handles dicts)

3. **Manual tests:**
   - UI stop button during long workflow
   - Stop during browser navigation
   - Stop during LLM call

---

## Future Considerations (Out of Scope)

These features are intentionally deferred:

1. **Pause/Resume**: Requires checkpoint serialization, loop state recovery, complex coordination
2. **Persistent checkpoint**: Need to solve variable serialization (DOM, AgentOutput, etc.)
3. **Resume after restart**: Requires persisted state and browser session recreation
4. **Agent-level stop checking**: Could pass stop signal to AgentContext for agents to check internally
