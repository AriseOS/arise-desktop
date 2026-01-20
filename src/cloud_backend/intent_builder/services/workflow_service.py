"""
WorkflowService - Unified API for workflow generation and dialogue

This service provides the main entry points for:
1. Generating workflows from recordings/intents
2. Interactive dialogue for workflow understanding and modification
3. Streaming progress updates for frontend display

Replaces the old MetaFlowGenerator + WorkflowGenerator flow.
"""

import os
import asyncio
import logging
import uuid
from typing import Dict, List, Any, Optional, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

from ..agents.workflow_builder import (
    WorkflowBuilder,
    WorkflowBuilderSession,
    GenerationResult,
    StreamEvent,
    DialogueMessage,
    SessionState,
)
from ..validators import WorkflowValidator, FullValidationResult
from ..extractors.intent_extractor import IntentExtractor
from ..core.intent_memory_graph import IntentMemoryGraph
from ..storage.in_memory_storage import InMemoryIntentStorage

if TYPE_CHECKING:
    from src.common.config_service import ConfigService

logger = logging.getLogger(__name__)


class GenerationStatus(Enum):
    """Status of workflow generation"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    UNDERSTANDING = "understanding"
    GENERATING = "generating"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GenerationRequest:
    """Request to generate a workflow"""
    recording_id: Optional[str] = None
    task_description: str = ""
    user_query: Optional[str] = None  # User's goal/intent (e.g., "repeat for 10 items")
    intent_sequence: Optional[List[Dict[str, Any]]] = None
    operations: Optional[List[Dict[str, Any]]] = None  # Raw operations from recording
    graph: Optional[Dict[str, Any]] = None  # StateActionGraph from Graph Builder (preferred)
    enable_semantic_validation: bool = True
    dom_snapshots: Optional[Dict[str, Dict]] = None  # URL -> DOM dict for script generation
    workflow_dir: Optional[str] = None  # Directory to save workflow and scripts


@dataclass
class GenerationResponse:
    """Response from workflow generation"""
    success: bool
    workflow_id: Optional[str] = None
    workflow: Optional[Dict[str, Any]] = None
    workflow_yaml: Optional[str] = None
    session_id: Optional[str] = None  # For continuing dialogue
    error: Optional[str] = None
    validation_result: Optional[FullValidationResult] = None


@dataclass
class GenerationProgress:
    """Progress update during generation"""
    status: GenerationStatus
    progress: int  # 0-100
    message: str
    details: Optional[str] = None


@dataclass
class ChatRequest:
    """Request to chat about a workflow"""
    session_id: str
    message: str


@dataclass
class ChatResponse:
    """Response from workflow chat"""
    reply: str
    workflow_updated: bool = False
    workflow: Optional[Dict[str, Any]] = None
    workflow_yaml: Optional[str] = None
    changes: Optional[List[Dict[str, Any]]] = None


class WorkflowService:
    """
    Unified service for workflow generation and dialogue.

    Example usage:

    ```python
    service = WorkflowService()

    # One-shot generation
    response = await service.generate(GenerationRequest(
        task_description="Extract product info",
        intent_sequence=[...]
    ))

    # Or with streaming progress
    async for progress in service.generate_stream(request):
        print(f"{progress.status}: {progress.progress}% - {progress.message}")

    # Interactive dialogue
    chat_response = await service.chat(ChatRequest(
        session_id=response.session_id,
        message="Why did you use browser_agent here?"
    ))
    ```
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3
    ):
        """
        Initialize WorkflowService.

        Args:
            config_service: ConfigService for reading configuration
            api_key: Anthropic API key
            model: Model to use
            base_url: API proxy URL
            max_retries: Max retries for generation with validation feedback
        """
        self.config_service = config_service
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_retries = max_retries

        # Active sessions for dialogue
        self._sessions: Dict[str, WorkflowBuilderSession] = {}

        # Cached generation results from generate_stream (session_id -> GenerationResponse)
        self._stream_results: Dict[str, GenerationResponse] = {}

        # Intent extractor for processing raw operations
        self._intent_extractor: Optional[IntentExtractor] = None

        logger.info("WorkflowService initialized")

    def _get_api_key(self) -> Optional[str]:
        """Get API key from config or environment"""
        if self.api_key:
            return self.api_key
        if self.config_service:
            return (
                self.config_service.get("claude_agent.api_key") or
                self.config_service.get("agent.llm.api_key") or
                os.environ.get("ANTHROPIC_API_KEY")
            )
        return os.environ.get("ANTHROPIC_API_KEY")

    async def generate(
        self,
        request: GenerationRequest,
        enable_dialogue: bool = True
    ) -> GenerationResponse:
        """
        Generate workflow from request.

        If enable_dialogue is True, creates a session for follow-up dialogue.

        Args:
            request: Generation request
            enable_dialogue: Whether to keep session open for dialogue

        Returns:
            GenerationResponse with workflow or error
        """
        logger.info(f"Starting workflow generation: {request.task_description[:50]}...")

        # Prioritize graph input if provided (from Graph Builder)
        if request.graph:
            logger.info("Using graph input from Graph Builder")
            if enable_dialogue:
                return await self._generate_with_session(
                    request=request,
                    intent_sequence=None,
                    graph=request.graph
                )
            return await self._generate_oneshot(
                request=request,
                intent_sequence=None,
                graph=request.graph
            )

        # Fall back to intent sequence (legacy path)
        intent_sequence = request.intent_sequence
        if not intent_sequence and request.operations:
            # Extract intents from operations
            intent_sequence = await self._extract_intents(
                request.operations,
                request.task_description
            )

        if not intent_sequence:
            return GenerationResponse(
                success=False,
                error="No graph, intent sequence, or operations provided"
            )

        if enable_dialogue:
            # Use session-based generation for dialogue support
            return await self._generate_with_session(
                request=request,
                intent_sequence=intent_sequence,
                graph=None
            )
        # Use one-shot generation
        return await self._generate_oneshot(
            request=request,
            intent_sequence=intent_sequence,
            graph=None
        )

    async def _generate_oneshot(
        self,
        request: GenerationRequest,
        intent_sequence: Optional[List[Dict[str, Any]]],
        graph: Optional[Dict[str, Any]]
    ) -> GenerationResponse:
        """One-shot generation without session"""
        builder = WorkflowBuilder(
            config_service=self.config_service,
            api_key=self._get_api_key(),
            model=self.model,
            base_url=self.base_url
        )

        result = await builder.build(
            request.task_description,
            intent_sequence=intent_sequence,
            user_query=request.user_query,
            graph=graph
        )

        if not result.success:
            return GenerationResponse(
                success=False,
                error=result.error
            )

        # Validate
        if request.enable_semantic_validation:
            validator = WorkflowValidator(
                config_service=self.config_service,
                api_key=self._get_api_key(),
                model=self.model,
                base_url=self.base_url
            )
            # Use user_query (the actual user goal) for semantic validation
            # Never fall back to task_description as it may mislead validation
            validation = await validator.validate(
                request.user_query or "",
                intent_sequence,
                result.workflow
            )
        else:
            validation = None

        workflow_id = str(uuid.uuid4())

        return GenerationResponse(
            success=True,
            workflow_id=workflow_id,
            workflow=result.workflow,
            workflow_yaml=result.workflow_yaml,
            validation_result=validation
        )

    async def _generate_with_session(
        self,
        request: GenerationRequest,
        intent_sequence: Optional[List[Dict[str, Any]]],
        graph: Optional[Dict[str, Any]]
    ) -> GenerationResponse:
        """Generate with session for dialogue support"""
        session_id = str(uuid.uuid4())

        session = WorkflowBuilderSession(
            config_service=self.config_service,
            api_key=self._get_api_key(),
            model=self.model,
            base_url=self.base_url,
            session_id=session_id
        )

        try:
            await session.__aenter__()

            result = await session.generate(
                request.task_description,
                intent_sequence=intent_sequence,
                user_query=request.user_query,
                graph=graph
            )

            # If initial generation failed (e.g., rule validation failed), try to fix via dialogue
            retry_count = 0
            while not result.success and retry_count < self.max_retries:
                retry_count += 1
                logger.info(f"Generation failed, retry {retry_count}/{self.max_retries}: {result.error}")

                # Send error feedback to Claude for correction
                feedback = f"The workflow generation failed with error:\n{result.error}\n\nPlease fix this issue and regenerate the workflow."
                response = await session.chat(feedback)

                # Check if a new workflow was generated
                if response.workflow_yaml:
                    result = GenerationResult(
                        success=True,
                        workflow=session.get_current_workflow(),
                        workflow_yaml=session.get_current_workflow_yaml(),
                        session_id=session_id
                    )
                else:
                    # Still no valid workflow, continue retry loop
                    result = GenerationResult(
                        success=False,
                        error=f"Failed to fix: {result.error}",
                        iterations=retry_count
                    )

            if not result.success:
                await session.close()
                return GenerationResponse(
                    success=False,
                    error=result.error
                )

            # Validate
            if request.enable_semantic_validation:
                validator = WorkflowValidator(
                    config_service=self.config_service,
                    api_key=self._get_api_key(),
                    model=self.model,
                    base_url=self.base_url
                )
                # Use user_query (the actual user goal) for semantic validation
                validation = await validator.validate(
                    request.user_query or "",
                    intent_sequence,
                    result.workflow
                )

                # If validation fails and we have retries left, retry with feedback
                retry_count = 0
                while not validation.valid and retry_count < self.max_retries:
                    retry_count += 1
                    logger.info(f"Validation failed, retry {retry_count}/{self.max_retries}")

                    # Send feedback via dialogue
                    feedback = f"The workflow validation failed:\n{validation.get_feedback()}\n\nPlease fix these issues and regenerate the workflow."
                    response = await session.chat(feedback)

                    # Check if a new workflow was generated
                    if response.workflow_yaml:
                        result = GenerationResult(
                            success=True,
                            workflow=session.get_current_workflow(),
                            workflow_yaml=session.get_current_workflow_yaml(),
                            session_id=session_id
                        )
                        validation = await validator.validate(
                            request.user_query or "",
                            intent_sequence,
                            result.workflow
                        )
            else:
                validation = None

            # Store session for future dialogue
            self._sessions[session_id] = session

            workflow_id = str(uuid.uuid4())

            return GenerationResponse(
                success=True,
                workflow_id=workflow_id,
                workflow=result.workflow,
                workflow_yaml=result.workflow_yaml,
                session_id=session_id,
                validation_result=validation
            )

        except Exception as e:
            logger.error(f"Session generation error: {e}")
            await session.close()
            return GenerationResponse(
                success=False,
                error=str(e)
            )

    async def generate_stream(
        self,
        request: GenerationRequest
    ) -> AsyncIterator[GenerationProgress]:
        """
        Generate workflow with streaming progress updates.

        This provides a Lovable-style experience with simulated progress
        messages for frontend display.

        Args:
            request: Generation request

        Yields:
            GenerationProgress updates
        """
        # Log all inputs for debugging
        logger.info(f"🚀 [WorkflowService.generate_stream] Starting")
        logger.info(f"  📋 Task description: {request.task_description[:100]}...")
        logger.info(f"  🎯 User query: {request.user_query or '(not provided)'}")
        logger.info(f"  📝 Recording ID: {request.recording_id or '(not provided)'}")
        logger.info(f"  📊 Intent sequence: {len(request.intent_sequence or [])} intents")
        logger.info(f"  🔧 Operations: {len(request.operations or [])} operations")

        # Initial progress
        yield GenerationProgress(
            status=GenerationStatus.PENDING,
            progress=0,
            message="Starting workflow generation..."
        )

        # Prioritize graph input over intent extraction
        graph = request.graph
        intent_sequence = request.intent_sequence

        if graph:
            # Graph path (preferred, no LLM for intent extraction)
            logger.info("📊 [Stream] Using graph input from Graph Builder")
            yield GenerationProgress(
                status=GenerationStatus.ANALYZING,
                progress=10,
                message="Using State/Action Graph...",
                details=f"{len(graph.get('states', {}))} states, {len(graph.get('edges', []))} edges"
            )
            await asyncio.sleep(0.2)
        else:
            # Intent/Operations path (legacy)
            yield GenerationProgress(
                status=GenerationStatus.ANALYZING,
                progress=10,
                message="Analyzing recording content...",
                details=f"Processing {len(request.operations or [])} operations"
            )

            if not intent_sequence and request.operations:
                intent_sequence = await self._extract_intents(
                    request.operations,
                    request.task_description
                )
                await asyncio.sleep(0.3)  # Simulated delay

            if not intent_sequence:
                yield GenerationProgress(
                    status=GenerationStatus.FAILED,
                    progress=0,
                    message="Failed: No graph, intent sequence, or operations available"
                )
                return

            yield GenerationProgress(
                status=GenerationStatus.UNDERSTANDING,
                progress=30,
                message="Understanding user intent...",
                details=f"Identified {len(intent_sequence)} intents"
            )

            await asyncio.sleep(0.3)  # Simulated delay

        # Generate workflow
        yield GenerationProgress(
            status=GenerationStatus.GENERATING,
            progress=50,
            message="Generating workflow steps..."
        )

        session_id = str(uuid.uuid4())
        session = WorkflowBuilderSession(
            config_service=self.config_service,
            api_key=self._get_api_key(),
            model=self.model,
            base_url=self.base_url,
            session_id=session_id
        )

        try:
            await session.__aenter__()

            # Track progress from session
            progress_updates = []

            def on_progress(event: StreamEvent):
                progress_updates.append(event)

            # Convert workflow_dir to Path if provided
            from pathlib import Path
            workflow_dir = Path(request.workflow_dir) if request.workflow_dir else None

            # Pass graph (preferred) or intent_sequence (legacy)
            result = await session.generate(
                request.task_description,
                intent_sequence=intent_sequence,
                user_query=request.user_query,
                on_progress=on_progress,
                dom_snapshots=request.dom_snapshots,
                workflow_dir=workflow_dir,
                graph=graph
            )

            # If initial generation failed (e.g., rule validation failed), try to fix via dialogue
            retry_count = 0
            while not result.success and retry_count < self.max_retries:
                retry_count += 1
                yield GenerationProgress(
                    status=GenerationStatus.GENERATING,
                    progress=60 + retry_count * 3,
                    message=f"Fixing errors (attempt {retry_count})...",
                    details=result.error[:200] if result.error else None
                )

                # Send error feedback to Claude for correction
                feedback = f"The workflow generation failed with error:\n{result.error}\n\nPlease fix this issue and regenerate the workflow."
                response = await session.chat(feedback)

                # Check if a new workflow was generated
                if response.workflow_yaml:
                    result = GenerationResult(
                        success=True,
                        workflow=session.get_current_workflow(),
                        workflow_yaml=session.get_current_workflow_yaml(),
                        session_id=session_id
                    )
                else:
                    result = GenerationResult(
                        success=False,
                        error=f"Failed to fix: {result.error}",
                        iterations=retry_count
                    )

            if not result.success:
                # Store failure result
                self._stream_results[session_id] = GenerationResponse(
                    success=False,
                    error=result.error,
                    session_id=session_id
                )
                yield GenerationProgress(
                    status=GenerationStatus.FAILED,
                    progress=0,
                    message=f"Generation failed: {result.error}"
                )
                await session.close()
                return

            yield GenerationProgress(
                status=GenerationStatus.GENERATING,
                progress=70,
                message="Workflow generated, validating..."
            )

            # Validation
            yield GenerationProgress(
                status=GenerationStatus.VALIDATING,
                progress=85,
                message="Validating workflow..."
            )

            if request.enable_semantic_validation:
                validator = WorkflowValidator(
                    config_service=self.config_service,
                    api_key=self._get_api_key(),
                    model=self.model,
                    base_url=self.base_url
                )
                # Use user_query (the actual user goal) for semantic validation
                validation = await validator.validate(
                    request.user_query or "",
                    intent_sequence,
                    result.workflow
                )

                if not validation.valid:
                    yield GenerationProgress(
                        status=GenerationStatus.VALIDATING,
                        progress=90,
                        message="Fixing validation issues...",
                        details=validation.get_feedback()[:200]
                    )
                    # Retry with feedback
                    feedback = f"The workflow validation failed:\n{validation.get_feedback()}\n\nPlease fix these issues."
                    await session.chat(feedback)
            else:
                validation = None

            # Store session and result
            self._sessions[session_id] = session
            workflow = session.get_current_workflow()
            workflow_yaml = session.get_current_workflow_yaml()

            self._stream_results[session_id] = GenerationResponse(
                success=True,
                workflow_id=session_id,
                workflow=workflow,
                workflow_yaml=workflow_yaml,
                session_id=session_id,
                validation_result=validation
            )

            # Log final output
            logger.info(f"✅ [WorkflowService.generate_stream] Generation completed")
            logger.info(f"  📄 Session ID: {session_id}")
            logger.info(f"  📋 Workflow name: {workflow.get('metadata', {}).get('name', 'unknown') if workflow else 'N/A'}")
            logger.info(f"  📊 Steps count: {len(workflow.get('steps', [])) if workflow else 0}")
            logger.info(f"  📝 YAML size: {len(workflow_yaml) if workflow_yaml else 0} chars")

            yield GenerationProgress(
                status=GenerationStatus.COMPLETED,
                progress=100,
                message="Workflow generated successfully!",
                details=f"Session ID: {session_id}"
            )

        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            # Store failure result
            self._stream_results[session_id] = GenerationResponse(
                success=False,
                error=str(e),
                session_id=session_id
            )
            yield GenerationProgress(
                status=GenerationStatus.FAILED,
                progress=0,
                message=f"Error: {str(e)}"
            )
            await session.close()

    def get_stream_result(self, session_id: str) -> Optional[GenerationResponse]:
        """
        Get the cached result from generate_stream.

        This should be called after generate_stream completes to get the final result
        instead of calling generate() again.

        Args:
            session_id: Session ID from the COMPLETED progress event

        Returns:
            GenerationResponse or None if not found
        """
        return self._stream_results.get(session_id)

    def pop_stream_result(self, session_id: str) -> Optional[GenerationResponse]:
        """
        Get and remove the cached result from generate_stream.

        This is a one-time retrieval that also cleans up the cache.

        Args:
            session_id: Session ID from the COMPLETED progress event

        Returns:
            GenerationResponse or None if not found
        """
        return self._stream_results.pop(session_id, None)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Send a message in an existing workflow dialogue session.

        Args:
            request: Chat request with session_id and message

        Returns:
            ChatResponse with reply and potential workflow updates
        """
        session = self._sessions.get(request.session_id)
        if not session:
            return ChatResponse(
                reply=f"Session not found: {request.session_id}. Please generate a workflow first."
            )

        if session.state == SessionState.CLOSED:
            return ChatResponse(
                reply="This session has been closed."
            )

        old_workflow = session.get_current_workflow()

        response = await session.chat(request.message)

        new_workflow = session.get_current_workflow()
        workflow_updated = (
            response.workflow_yaml is not None and
            new_workflow != old_workflow
        )

        return ChatResponse(
            reply=response.content,
            workflow_updated=workflow_updated,
            workflow=new_workflow if workflow_updated else None,
            workflow_yaml=response.workflow_yaml if workflow_updated else None
        )

    async def close_session(self, session_id: str) -> bool:
        """
        Close a dialogue session.

        Args:
            session_id: Session ID to close

        Returns:
            True if session was closed, False if not found
        """
        session = self._sessions.pop(session_id, None)
        if session:
            await session.close()
            return True
        return False

    async def get_session_workflow(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get current workflow from a session.

        Args:
            session_id: Session ID

        Returns:
            Current workflow dictionary or None
        """
        session = self._sessions.get(session_id)
        if session:
            return session.get_current_workflow()
        return None

    async def get_session_dialogue_history(
        self,
        session_id: str
    ) -> List[DialogueMessage]:
        """
        Get dialogue history from a session.

        Args:
            session_id: Session ID

        Returns:
            List of DialogueMessage objects
        """
        session = self._sessions.get(session_id)
        if session:
            return session.get_dialogue_history()
        return []

    async def _extract_intents(
        self,
        operations: List[Dict[str, Any]],
        task_description: str
    ) -> List[Dict[str, Any]]:
        """Extract intents from raw operations"""
        if not self._intent_extractor:
            # Initialize with LLM provider
            from src.common.llm import AnthropicProvider
            api_key = self._get_api_key()
            if not api_key:
                raise ValueError("API key required for intent extraction")

            provider = AnthropicProvider(
                api_key=api_key,
                model_name=self.model or "claude-sonnet-4-5",
                base_url=self.base_url
            )
            self._intent_extractor = IntentExtractor(provider)

        # Extract intents
        intents = await self._intent_extractor.extract(
            operations=operations,
            task_description=task_description
        )

        # Convert to dict format
        return [intent.model_dump() for intent in intents]

    async def cleanup(self):
        """Cleanup all sessions"""
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)
        logger.info("All sessions cleaned up")

    async def add_intents_to_graph(
        self,
        operations: List[Dict[str, Any]],
        graph_filepath: str,
        task_description: Optional[str] = None
    ) -> int:
        """
        Extract intents from operations and add to existing Intent Memory Graph.

        This is used for building up a user's intent graph over time as they
        record more operations.

        Args:
            operations: User operation list
            graph_filepath: Path to existing intent_graph.json file
            task_description: User's description of what they did (optional)

        Returns:
            Number of new intents added
        """
        from pathlib import Path

        logger.info(f"Adding intents from {len(operations)} operations to graph")

        if task_description:
            logger.info(f"Task description: {task_description}")

        # Initialize intent extractor if needed
        if not self._intent_extractor:
            from src.common.llm import AnthropicProvider
            api_key = self._get_api_key()
            if not api_key:
                logger.error("No API key available for intent extraction")
                return 0

            provider = AnthropicProvider(
                api_key=api_key,
                model_name=self.model or "claude-sonnet-4-5",
                base_url=self.base_url
            )
            self._intent_extractor = IntentExtractor(llm_provider=provider)

        # Extract intents
        logger.info("Extracting intents...")
        try:
            new_intents = await self._intent_extractor.extract_intents(
                operations=operations,
                task_description=task_description or "",
                source_session_id="cloud-backend"
            )
            logger.info(f"Extracted {len(new_intents)} new intents")
        except Exception as e:
            logger.error(f"Failed to extract intents: {e}", exc_info=True)
            return 0

        # Load existing Intent Graph or create new one
        storage = InMemoryIntentStorage()

        if Path(graph_filepath).exists():
            logger.info(f"Loading existing graph from {graph_filepath}")
            storage.load(graph_filepath)
            existing_count = len(storage.get_all_intents())
            logger.info(f"Loaded {existing_count} existing intents")
        else:
            logger.info("Creating new graph (file doesn't exist yet)")
            existing_count = 0

        graph = IntentMemoryGraph(storage=storage)

        # Add new intents to graph
        added_count = 0
        for intent in new_intents:
            try:
                graph.add_intent(intent)
                added_count += 1
            except Exception as e:
                logger.warning(f"Failed to add intent: {e}")

        # Save updated graph
        storage.save(graph_filepath)
        logger.info(f"Added {added_count} intents, saved to {graph_filepath}")

        return added_count
