"""Memory System - Graph-Based User Behavior Memory System.

This is a comprehensive memory system based on graph structure, designed to capture,
process, and reason about user behaviors in web/app interactions. The system
implements a four-level modeling architecture and five-layer system design.

Graph-Based Ontology Model:
    - Domain: Represents an app or website domain (main page/homepage)
              Central hub nodes connecting to all States within that app/website
    - State: Represents a page (web) or screen (app) where the user is located
             States are graph nodes containing multiple Intents
    - Intent: Atomic operations performed within a State (ClickElement, TypeText)
              Intents belong to exactly one State and don't cause state transitions
    - Action: State transitions (navigation) connecting two different States
              Actions are graph edges representing navigation events
    - Manage: Edges connecting Domain to States, tracking visit metadata
              Stores visit timestamps, counts, and duration information
    - CognitivePhrase: High-level behavioral patterns composed of States and Actions
                      Representing complete workflows (e.g., "Compare Products")

Five-Layer System Design:
    1. Data Capture Layer: Event parsing and atomic intent extraction
    2. Semantic Abstraction: Semantic state construction from intents
    3. Memory Graph Layer: Core graph structure for state storage and relationships
    4. Goal Index/Search: Task-level retrieval and recommendation
    5. Replay & Visualization: Behavior path reconstruction and analysis

Core Features:
    - Graph-based semantic state storage
    - Goal-oriented intelligent retrieval
    - Behavior replay and recommendation
    - Cognitive phrase-based aggregation and analysis
    - Multi-provider LLM/embedding/rerank support

Project Structure:
    - ontology: Core ontology models (State, Intent, Action, CognitivePhrase)
    - memory: Memory management with graph-based state/action storage
    - graphstore: Graph storage backends (NetworkX, etc.)
    - services: AI/ML services (LLM, Embedding, Rerank, Prompt)
    - thinker: Workflow processing and state/intent extraction
    - reasoner: Intelligent reasoning, retrieval, and workflow analysis

Typical usage example:

    from src import (
        Intent, State, Action, CognitivePhrase,
        WorkflowMemory, NetworkXGraphStorage,
        WorkflowProcessor, Reasoner
    )

    # Initialize memory system
    graph_storage = NetworkXGraphStorage()
    memory = WorkflowMemory(graph_storage)

    # Process workflow
    processor = WorkflowProcessor(memory)
    processor.process_user_workflow(workflow_data)

    # Query and reason
    reasoner = Reasoner(memory)
    results = reasoner.retrieve_similar_workflows(query)
"""

# Graph storage components
from src.cloud_backend.memgraph.graphstore import GraphStore, MemoryGraph, NetworkXGraph

# Memory management components
from src.cloud_backend.memgraph.memory import (
    ActionManager,
    CognitivePhraseManager,
    GraphActionManager,
    GraphStateManager,
    InMemoryCognitivePhraseManager,
    Memory,
    StateManager,
    WorkflowMemory,
)

# Ontology definitions (core data models)
from src.cloud_backend.memgraph.ontology import (
    Action,
    AtomicIntent,
    CognitivePhrase,
    Domain,
    Intent,
    IntentSequence,
    Manage,
    PageInstance,
    SemanticState,
    State,
    TransitionEdge,
)

# Reasoning and retrieval components
from src.cloud_backend.memgraph.reasoner import (
    CognitivePhraseChecker,
    Reasoner,
    RetrievalResult,
    RetrievalTool,
    TaskDAG,
    TaskTool,
    ToolResult,
    WorkflowConverter,
    WorkflowResult,
)

# Services layer (LLM, Embedding, Rerank)
from src.cloud_backend.memgraph.services import (
    BasePrompt,
    EmbeddingConfigValidationError,
    EmbeddingModel,
    EmbeddingModelConfigChecker,
    EmbeddingProvider,
    EmbeddingResponse,
    LLMClient,
    LLMConfigChecker,
    LLMConfigValidationError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LocalBGEModel,
    LocalBGERerankModel,
    MaaSRerankModel,
    OpenAIEmbedding,
    OpenAILLMClient,
    PromptInput,
    PromptOutput,
    PromptRegistry,
    PromptTemplate,
    RerankConfigValidationError,
    RerankModel,
    RerankModelConfigChecker,
    RerankProvider,
    RerankResponse,
    RerankResult,
    check_all_embedding_configs,
    check_all_llm_configs,
    check_all_rerank_configs,
    create_embedding_model,
    create_rerank_model,
    get_available_embedding_providers,
    get_available_rerank_providers,
    prompt_registry,
)

# Workflow processing (URL-based pipeline)
from src.cloud_backend.memgraph.thinker import (
    URLSegment,
    WorkflowProcessor,
    WorkflowProcessingResult,
)

__all__ = [
    # Ontology - Core data models
    "Domain",
    "Manage",
    "Intent",
    "AtomicIntent",
    "IntentSequence",
    "PageInstance",
    "State",
    "SemanticState",
    "Action",
    "TransitionEdge",
    "CognitivePhrase",
    # Memory - Memory management
    "StateManager",
    "ActionManager",
    "CognitivePhraseManager",
    "Memory",
    "GraphStateManager",
    "GraphActionManager",
    "InMemoryCognitivePhraseManager",
    "WorkflowMemory",
    # Graphstore - Graph storage
    "GraphStore",
    "MemoryGraph",
    "NetworkXGraph",
    # Reasoner - Reasoning and retrieval
    "Reasoner",
    "RetrievalResult",
    "WorkflowResult",
    "TaskDAG",
    "CognitivePhraseChecker",
    "WorkflowConverter",
    "TaskTool",
    "ToolResult",
    "RetrievalTool",
    # Thinker - Workflow processing (URL-based pipeline)
    "WorkflowProcessor",
    "WorkflowProcessingResult",
    "URLSegment",
    # Services - LLM clients
    "LLMClient",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "OpenAILLMClient",
    "LLMConfigChecker",
    "LLMConfigValidationError",
    "check_all_llm_configs",
    # Services - Embedding models
    "EmbeddingModel",
    "EmbeddingProvider",
    "EmbeddingResponse",
    "OpenAIEmbedding",
    "LocalBGEModel",
    "create_embedding_model",
    "EmbeddingModelConfigChecker",
    "EmbeddingConfigValidationError",
    "check_all_embedding_configs",
    "get_available_embedding_providers",
    # Services - Rerank models
    "RerankModel",
    "RerankProvider",
    "RerankResponse",
    "RerankResult",
    "LocalBGERerankModel",
    "MaaSRerankModel",
    "create_rerank_model",
    "RerankModelConfigChecker",
    "RerankConfigValidationError",
    "check_all_rerank_configs",
    "get_available_rerank_providers",
    # Services - Prompt management
    "BasePrompt",
    "PromptInput",
    "PromptOutput",
    "PromptRegistry",
    "PromptTemplate",
    "prompt_registry",
]


__version__ = "1.0.0"
__author__ = "Zheng Wang"
