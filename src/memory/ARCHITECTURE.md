# Memory System - Architecture Documentation

**Version**: 1.0.0
**Last Updated**: October 2025
**Author**: Zheng Wang

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Principles](#2-architecture-principles)
3. [Four-Level Modeling Architecture](#3-four-level-modeling-architecture)
4. [Five-Layer System Design](#4-five-layer-system-design)
5. [Core Components](#5-core-components)
6. [Data Flow](#6-data-flow)
7. [Storage Architecture](#7-storage-architecture)
8. [Intelligent Retrieval System](#8-intelligent-retrieval-system)
9. [API Design](#9-api-design)
10. [Scalability & Performance](#10-scalability--performance)
11. [Future Enhancements](#11-future-enhancements)

---

## 1. System Overview

### 1.1 Purpose

Memory System is a comprehensive, graph-based memory management platform designed to:

- **Capture** user behaviors in web/app interactions
- **Abstract** atomic operations into semantic states
- **Organize** semantic states as a directed graph structure
- **Support** LLM-driven goal decomposition and intelligent retrieval
- **Enable** semantic-driven memory retrieval and matching

### 1.2 Key Capabilities

| Capability | Description |
|------------|-------------|
| 🧩 Multi-Level Modeling | Four levels: Atomic Intents → Semantic States → Cognitive Phrases → User Goals |
| 📊 Graph-Based Storage | States as nodes, actions as edges in directed graph |
| 🤖 LLM Integration | Multi-provider support (OpenAI, Claude, Mock) |
| 🔍 Vector Search | Fast semantic similarity using embeddings |
| 🎯 Goal Decomposition | Task-level DAG decomposition and matching |
| 🔄 Workflow Processing | Automated semantic extraction from raw events |
| ⚡ Intelligent Retrieval | Vector similarity + Graph traversal + LLM evaluation |

### 1.3 Design Philosophy

```
User Behavior → Semantic Understanding → Knowledge Graph → Intelligent Retrieval
```

The system bridges the gap between **low-level user interactions** and **high-level task understanding** through a hierarchical modeling approach.

---

## 2. Architecture Principles

### 2.1 Core Principles

1. **Semantic-First Design**
   - Every operation is grounded in semantic meaning
   - States represent meaningful behavioral units, not raw events
   - Retrieval based on semantic similarity, not keyword matching

2. **Graph-Centric Storage**
   - Semantic states as first-class graph nodes
   - Behavioral flow as directed edges
   - Path-based reasoning and trajectory analysis

3. **LLM-Augmented Intelligence**
   - Goal decomposition powered by LLMs
   - Semantic satisfaction evaluation via LLM reasoning
   - Cognitive phrase generation using natural language understanding

4. **Modular & Extensible**
   - Clear separation of concerns across layers
   - Plugin architecture for LLM/embedding/rerank providers
   - Abstract interfaces for storage backends

5. **Scalability & Performance**
   - Vector indexing for fast retrieval
   - Graph algorithms for efficient traversal
   - Batch processing for bulk operations
   - Async support for I/O-bound operations

---

## 3. Four-Level Modeling Architecture

The system employs a hierarchical modeling approach with four distinct levels:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Four-Level Modeling                          │
├─────────────────────────────────────────────────────────────────┤
│ Level 4: User Goals/Tasks                                       │
│   Purpose: Task-level understanding for intelligent retrieval   │
│   Examples: "Compare Coffee Products", "Find Best Deal"         │
│   Representation: Goal ID + Description + Entry States          │
│   Usage: Query matching, task decomposition                     │
├─────────────────────────────────────────────────────────────────┤
│ Level 3: Cognitive Phrases                                      │
│   Purpose: High-level workflow patterns for aggregation         │
│   Examples: "Browsing", "Information Extraction"                │
│   Representation: Label + State IDs + Action IDs + Time Range   │
│   Usage: Statistical analysis, reporting, behavioral insights   │
├─────────────────────────────────────────────────────────────────┤
│ Level 2: Semantic States (Graph Nodes) ⭐                       │
│   Purpose: Core building blocks of memory graph                 │
│   Examples: "InspectProductPrice", "SelectProduct"              │
│   Representation: State ID + Label + Type + Attributes + Vector │
│   Usage: Primary graph nodes, retrieval targets                 │
├─────────────────────────────────────────────────────────────────┤
│ Level 1: Atomic Intents                                         │
│   Purpose: Basic user operations from browser/app events        │
│   Examples: ClickElement, TypeText, CopyText                    │
│   Representation: Type + Timestamp + Context + Metadata         │
│   Usage: Replay data, state composition, fine-grained analysis  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Level 1: Atomic Intents

**Definition**: Smallest unit of user interaction, extracted from browser/app events.

**Data Model**:
```python
@dataclass
class Intent:
    type: IntentType              # e.g., CLICK_ELEMENT, TYPE_TEXT
    timestamp: int                # Unix timestamp in milliseconds
    page_url: str                 # Current page URL
    element_id: Optional[str]     # DOM element identifier
    text: Optional[str]           # Text content (for text-based intents)
    user_id: str                  # User identifier
    session_id: str               # Session identifier
    attributes: Dict[str, Any]    # Additional context
```

**Intent Types** (20+ types):
- **Click**: `CLICK_ELEMENT`, `DOUBLE_CLICK`, `RIGHT_CLICK`
- **Text**: `TYPE_TEXT`, `COPY_TEXT`, `PASTE_TEXT`, `DELETE_TEXT`
- **Navigation**: `NAVIGATE_TO`, `GO_BACK`, `GO_FORWARD`, `REFRESH_PAGE`
- **Form**: `FILL_INPUT`, `SELECT_OPTION`, `SUBMIT_FORM`
- **Drag**: `DRAG_ELEMENT`, `DROP_ELEMENT`, `HOVER_ELEMENT`
- **Scroll**: `SCROLL_PAGE`, `SCROLL_ELEMENT`

### 3.2 Level 2: Semantic States

**Definition**: Meaningful behavioral units composed of multiple atomic intents. **Primary graph nodes**.

**Data Model**:
```python
@dataclass
class State:
    id: str                           # Unique state identifier
    label: str                        # Human-readable label
    type: StateType                   # Semantic state type
    timestamp: int                    # State start time
    page_url: str                     # Associated page
    atomic_intents: List[Intent]      # Constituent intents
    attributes: Dict[str, Any]        # Extracted semantic info
    user_id: str
    session_id: str
    embedding: Optional[np.ndarray]   # Vector representation
```

**State Types** (30+ types across 6 categories):
1. **Browsing**: `BROWSE_CATALOG`, `BROWSE_PRODUCT`, `BROWSE_PAGE`
2. **Information Extraction**: `INSPECT_PRODUCT_PRICE`, `EXTRACT_TEXT`, `READ_DESCRIPTION`
3. **Search**: `SEARCH_PRODUCTS`, `FILTER_RESULTS`, `SORT_RESULTS`
4. **Comparison**: `COMPARE_PRODUCTS`, `COMPARE_PRICES`, `COMPARE_FEATURES`
5. **Selection**: `SELECT_PRODUCT`, `ADD_TO_CART`, `ADD_TO_WISHLIST`
6. **Transaction**: `CHECKOUT`, `PAYMENT`, `ORDER_CONFIRMATION`

**Graph Node Properties**:
- **Unique Identifier**: Each state has a unique ID
- **Temporal Ordering**: States have timestamps for sequential analysis
- **Semantic Embedding**: Vector representation for similarity search
- **Rich Attributes**: Extracted information (prices, product IDs, etc.)

### 3.3 Level 3: Cognitive Phrases

**Definition**: High-level workflow patterns aggregating multiple states for analysis.

**Data Model**:
```python
@dataclass
class CognitivePhrase:
    id: str                       # Unique phrase identifier
    label: str                    # Phrase name
    description: str              # Natural language description
    state_ids: List[str]          # Associated states
    action_ids: List[str]         # Associated actions
    start_time: int               # Phrase start timestamp
    end_time: int                 # Phrase end timestamp
    user_id: str
    session_id: str
    goal_id: Optional[str]        # Associated goal
    attributes: Dict[str, Any]    # Aggregated metrics
```

**Common Phrase Types**:
- **Browsing**: Exploratory navigation through catalog/pages
- **Information Extraction**: Systematic data collection
- **Decision Making**: Comparison and evaluation activities
- **Execution**: Task completion actions (purchase, submit, etc.)

**Usage Scenarios**:
- Statistical reporting and analytics
- Behavioral pattern analysis
- User journey visualization
- Aggregated metrics computation

### 3.4 Level 4: User Goals/Tasks

**Definition**: Task-level understanding for intelligent retrieval and matching.

**Representation**:
```python
{
    "goal_id": "compare_coffee_001",
    "description": "Compare different coffee products and find best deal",
    "entry_states": ["state_00120", "state_00125"],
    "cognitive_phrases": ["Browsing", "InformationExtraction", "DecisionMaking"],
    "task_dag": TaskDAG(...)  # Decomposed task structure
}
```

**Purpose**:
- Query matching: Map user queries to relevant goals
- Task decomposition: Break down complex queries into semantic requirements
- Retrieval optimization: Find most relevant state subgraphs

---

## 4. Five-Layer System Design

The system is organized into five distinct layers, each with clear responsibilities:

```
┌─────────────────────────────────────────────────────────────────┐
│                    System Architecture                          │
├─────────────────────────────────────────────────────────────────┤
│ Layer 5: Services (Cross-cutting)                               │
│   Components: LLM Clients, Embedding Models, Rerank Models      │
│   Technologies: OpenAI API, Anthropic API, Sentence-Transformers│
│   Responsibilities: AI/ML service abstraction                   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Reasoner (Goal Index/Search)                           │
│   Components: Reasoner, TaskDAG, Retrieval Tools                │
│   Technologies: Vector search, Graph algorithms, LLM reasoning  │
│   Responsibilities: Intelligent retrieval, goal decomposition   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Memory Graph (Storage & Management)                    │
│   Components: WorkflowMemory, StateManager, GraphStore          │
│   Technologies: NetworkX, Vector index, Graph databases         │
│   Responsibilities: State/action/phrase CRUD, graph operations  │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Thinker (Semantic Abstraction)                         │
│   Components: WorkflowProcessor, StateGenerator, DAG Builder    │
│   Technologies: LLM extraction, Intent parsing                  │
│   Responsibilities: Semantic extraction, workflow processing    │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Data Capture (Event Recording)                         │
│   Components: Event parsers, Intent extractors                  │
│   Technologies: Browser extensions, App instrumentation         │
│   Responsibilities: Raw event capture, atomic intent extraction │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Layer 1: Data Capture

**Purpose**: Capture raw user interactions and convert them to atomic intents.

**Components**:
- Event listeners (click, keyboard, navigation, etc.)
- Intent parsers (convert DOM events to Intent objects)
- Context extractors (page URL, element info, etc.)

**Outputs**: Stream of `Intent` objects

### 4.2 Layer 2: Thinker (Semantic Abstraction)

**Purpose**: Transform atomic intents into semantic states and cognitive phrases.

**Components**:

1. **IntentDAGBuilder** (`src/thinker/intent_dag_builder.py`)
   - Builds directed acyclic graph of intent dependencies
   - Identifies intent sequences and relationships

2. **StateGenerator** (`src/thinker/state_generator.py`)
   - Aggregates intent sequences into semantic states
   - Uses LLM to extract semantic meaning
   - Assigns state types and labels

3. **CognitivePhraseGenerator** (`src/thinker/cognitive_phrase_generator.py`)
   - Groups states into high-level phrases
   - Identifies workflow patterns
   - Computes aggregated metrics

4. **WorkflowProcessor** (`src/thinker/workflow_processor.py`)
   - Orchestrates entire semantic extraction pipeline
   - Processes user workflows end-to-end
   - Integrates with memory layer for storage

**Outputs**: `State`, `Action`, and `CognitivePhrase` objects

### 4.3 Layer 3: Memory Graph (Storage & Management)

**Purpose**: Store and manage semantic states as a directed graph.

**Components**:

1. **GraphStore Interface** (`src/graphstore/graph_store.py`)
   - Abstract interface for graph storage backends
   - Core operations: add_node, add_edge, get_neighbors, find_path

2. **NetworkXGraphStorage** (`src/graphstore/networkx_graph.py`)
   - In-memory graph storage using NetworkX
   - Supports directed graphs with node/edge attributes
   - Efficient graph algorithms (BFS, DFS, shortest path)

3. **MemoryGraph** (`src/graphstore/memory_graph.py`)
   - Wrapper providing high-level graph operations
   - Handles state-specific graph logic

4. **StateManager** (`src/memory/memory.py`)
   - CRUD operations for semantic states
   - State querying and filtering

5. **ActionManager** (`src/memory/memory.py`)
   - CRUD operations for actions (edges)
   - Edge querying and relationship tracking

6. **CognitivePhraseManager** (`src/memory/memory.py`)
   - CRUD operations for cognitive phrases
   - Phrase-level aggregations

7. **WorkflowMemory** (`src/memory/workflow_memory.py`)
   - High-level memory interface
   - Combines state, action, and phrase managers
   - Workflow-level operations

**Storage Schema**:
- **Nodes**: States with IDs, labels, types, attributes, embeddings
- **Edges**: Actions with source/target, types, timestamps, attributes
- **Indexes**: User ID, session ID, timestamp, state type, vector similarity

### 4.4 Layer 4: Reasoner (Goal Index/Search)

**Purpose**: Intelligent retrieval through goal decomposition and semantic matching.

**Components**:

1. **Reasoner** (`src/reasoner/reasoner.py`)
   - Main reasoning engine
   - Coordinates retrieval, decomposition, and evaluation
   - Integrates LLM, embedding, and rerank models

2. **TaskDAG** (`src/reasoner/task_dag.py`)
   - Represents decomposed task structure
   - Nodes: Semantic requirements
   - Edges: Task dependencies
   - Supports topological sorting for execution order

3. **WorkflowConverter** (`src/reasoner/workflow_converter.py`)
   - Converts memory graph paths to workflow representations
   - Serialization and deserialization

4. **RetrievalTool** (`src/reasoner/tools/retrieval_tool.py`)
   - Vector-based state retrieval
   - Graph traversal algorithms
   - Hybrid search strategies

5. **TaskTool** (`src/reasoner/tools/task_tool.py`)
   - Task decomposition utilities
   - Semantic requirement matching

**Retrieval Strategies**:
- **Vector Similarity**: Embedding-based semantic search
- **Graph Traversal**: BFS/DFS exploration from entry points
- **Hybrid Search**: Combined vector + graph approaches
- **LLM Evaluation**: Semantic satisfaction assessment

### 4.5 Layer 5: Services (AI/ML Services)

**Purpose**: Provide unified interfaces for AI/ML capabilities.

**Components**:

1. **LLM Clients** (`src/services/llm/`)
   - Abstract `LLMClient` interface
   - Implementations: OpenAI, Anthropic Claude, Mock
   - Factory pattern: `create_llm_client()`
   - Configuration validation

2. **Embedding Models** (`src/services/embedding_model/`)
   - Abstract `EmbeddingModel` interface
   - Implementations: OpenAI, Local BGE
   - Factory pattern: `create_embedding_model()`
   - Batch processing support

3. **Rerank Models** (`src/services/rerank_model/`)
   - Abstract `RerankModel` interface
   - Implementations: Local BGE, MaaS API
   - Factory pattern: `create_rerank_model()`
   - Top-K result selection

4. **Prompt Management** (`src/services/prompt_base.py`)
   - Prompt templates and registry
   - Prompt versioning and validation

**Design Patterns**:
- **Factory Pattern**: Provider-agnostic client creation
- **Strategy Pattern**: Pluggable provider implementations
- **Adapter Pattern**: Unified interface for different APIs

---

## 5. Core Components

### 5.1 Ontology (Data Models)

Location: `src/ontology/`

**Files**:
- `intent.py`: Intent, AtomicIntent, IntentType
- `state.py`: State, SemanticState, StateType
- `action.py`: Action, TransitionEdge
- `cognitive_phrase.py`: CognitivePhrase

**Responsibilities**:
- Define core data structures
- Provide Pydantic models for validation
- Ensure type safety across the system

### 5.2 Memory (Memory Management)

Location: `src/memory/`

**Files**:
- `memory.py`: Abstract interfaces (StateManager, ActionManager, CognitivePhraseManager, Memory)
- `workflow_memory.py`: Concrete implementation (WorkflowMemory)

**Responsibilities**:
- CRUD operations for all memory entities
- Query interfaces for filtering and searching
- Workflow-level operations (add_workflow_step, get_trajectory)

### 5.3 GraphStore (Storage Backend)

Location: `src/graphstore/`

**Files**:
- `graph_store.py`: GraphStore abstract interface
- `networkx_graph.py`: NetworkXGraphStorage implementation
- `memory_graph.py`: MemoryGraph wrapper

**Responsibilities**:
- Graph structure persistence
- Node/edge operations
- Graph algorithms (pathfinding, traversal, subgraph extraction)

### 5.4 Thinker (Workflow Processing)

Location: `src/thinker/`

**Files**:
- `intent_dag_builder.py`: IntentDAGBuilder
- `state_generator.py`: StateGenerator
- `cognitive_phrase_generator.py`: CognitivePhraseGenerator
- `workflow_processor.py`: WorkflowProcessor

**Responsibilities**:
- Parse raw workflows into intents
- Generate semantic states from intent sequences
- Synthesize cognitive phrases
- Orchestrate entire processing pipeline

### 5.5 Reasoner (Intelligent Reasoning)

Location: `src/reasoner/`

**Files**:
- `reasoner.py`: Main Reasoner class
- `task_dag.py`: TaskDAG structure
- `workflow_converter.py`: WorkflowConverter utilities
- `retrieval_result.py`: Result data models
- `cognitive_phrase_checker.py`: Phrase validation
- `tools/`: Reasoning tools (retrieval, task decomposition)

**Responsibilities**:
- Goal decomposition into semantic requirements
- Vector-based state retrieval
- Graph traversal and exploration
- LLM-driven semantic evaluation
- Result ranking and reranking

### 5.6 Services (AI/ML Infrastructure)

Location: `src/services/`

**Submodules**:
- `llm/`: LLM client implementations
- `embedding_model/`: Embedding model implementations
- `rerank_model/`: Rerank model implementations
- `prompt_base.py`: Prompt management

**Responsibilities**:
- Abstract AI/ML provider differences
- Provide unified APIs for LLM, embedding, rerank operations
- Handle API keys, configuration, error handling
- Support both sync and async operations

---

## 6. Data Flow

### 6.1 Workflow Processing Flow

```
User Interactions
      ↓
┌─────────────────┐
│ Event Capture   │  Layer 1: Data Capture
└────────┬────────┘
         ↓
    Intent Stream
         ↓
┌─────────────────┐
│ Intent DAG      │  Layer 2: Thinker
│   Builder       │
└────────┬────────┘
         ↓
   Intent DAG
         ↓
┌─────────────────┐
│ State Generator │  Layer 2: Thinker
│  (LLM-powered)  │
└────────┬────────┘
         ↓
 Semantic States
         ↓
┌─────────────────┐
│ Workflow Memory │  Layer 3: Memory Graph
│   (GraphStore)  │
└────────┬────────┘
         ↓
  Memory Graph
  (States + Actions)
```

### 6.2 Intelligent Retrieval Flow

```
User Query
    ↓
┌──────────────────┐
│ Goal Decomposer  │  Layer 4: Reasoner
│   (LLM-powered)  │
└────────┬─────────┘
         ↓
    Task DAG
  (Requirements)
         ↓
┌──────────────────┐
│ Vector Search    │  Layer 4: Reasoner
│ (Embeddings)     │  Layer 5: Services
└────────┬─────────┘
         ↓
  Candidate States
         ↓
┌──────────────────┐
│ Graph Traversal  │  Layer 4: Reasoner
│ (Neighbors)      │  Layer 3: Memory Graph
└────────┬─────────┘
         ↓
 Expanded States
         ↓
┌──────────────────┐
│ Reranking        │  Layer 4: Reasoner
│ (Rerank Model)   │  Layer 5: Services
└────────┬─────────┘
         ↓
┌──────────────────┐
│ LLM Evaluation   │  Layer 4: Reasoner
│ (Satisfaction)   │  Layer 5: Services
└────────┬─────────┘
         ↓
 Retrieval Results
 (Ranked Workflows)
```

### 6.3 End-to-End Example

**Scenario**: User searches for and compares coffee products

**Step 1: Capture Events**
```python
events = [
    {"type": "click", "element": "search-button", "timestamp": 1000},
    {"type": "input", "element": "search-box", "value": "coffee", "timestamp": 1500},
    {"type": "click", "element": "product-1", "timestamp": 2000},
    {"type": "click", "element": "price-tag", "timestamp": 2500},
    # ... more events
]
```

**Step 2: Extract Intents**
```python
intents = [
    Intent(type=CLICK_ELEMENT, element_id="search-button", timestamp=1000),
    Intent(type=TYPE_TEXT, text="coffee", timestamp=1500),
    Intent(type=CLICK_ELEMENT, element_id="product-1", timestamp=2000),
    # ...
]
```

**Step 3: Generate States**
```python
states = [
    State(label="Search Products", type=SEARCH_PRODUCTS,
          atomic_intents=[intent1, intent2], timestamp=1000),
    State(label="Inspect Product Price", type=INSPECT_PRODUCT_PRICE,
          atomic_intents=[intent3, intent4], timestamp=2000),
    # ...
]
```

**Step 4: Store in Graph**
```python
memory.create_state(state1)
memory.create_state(state2)
memory.create_action(Action(source=state1.id, target=state2.id))
```

**Step 5: Query**
```python
query = "Find instances where user compared coffee products"
results = reasoner.retrieve_similar_workflows(query, top_k=5)
# Returns: List of workflow paths with similarity scores
```

---

## 7. Storage Architecture

### 7.1 Graph Storage

**Backend**: NetworkX (in-memory), extensible to Neo4j/ArangoDB

**Schema**:

**Nodes (States)**:
```python
{
    "id": "state_00123",
    "label": "Inspect Product Price",
    "type": "INSPECT_PRODUCT_PRICE",
    "timestamp": 1609459200000,
    "page_url": "https://example.com/product/coffee-123",
    "user_id": "user_123",
    "session_id": "session_456",
    "attributes": {
        "product_id": "coffee-123",
        "price": 29.99,
        "currency": "USD"
    },
    "embedding": [0.1, 0.2, ..., 0.5]  # 1536-dim vector
}
```

**Edges (Actions)**:
```python
{
    "source": "state_00122",
    "target": "state_00123",
    "type": "user_navigation",
    "timestamp": 1609459201000,
    "duration": 1000,
    "attributes": {
        "transition_trigger": "click",
        "confidence": 0.95
    }
}
```

**Indexes**:
- `user_id_index`: Fast lookup by user
- `session_id_index`: Fast lookup by session
- `timestamp_index`: Temporal queries
- `state_type_index`: Type-based filtering
- `vector_index`: KNN similarity search (FAISS/Annoy)

### 7.2 Vector Storage

**Purpose**: Fast semantic similarity search

**Technology**: FAISS (GPU), Annoy, or custom index

**Vector Dimensions**:
- OpenAI `text-embedding-ada-002`: 1536
- OpenAI `text-embedding-3-large`: 3072
- Local BGE `bge-base-en-v1.5`: 768

**Operations**:
- `add_vector(state_id, embedding)`: Add state embedding
- `search_similar(query_embedding, top_k)`: KNN search
- `batch_search(query_embeddings, top_k)`: Batch KNN

### 7.3 Persistence

**Current**: In-memory with pickle serialization

**Future**:
- Graph DB: Neo4j, ArangoDB for distributed storage
- Vector DB: Pinecone, Weaviate for cloud-native vector search
- Blob Storage: S3 for embeddings and large attributes

---

## 8. Intelligent Retrieval System

### 8.1 Goal Decomposition

**Purpose**: Break down complex user queries into semantic requirements.

**Algorithm**:

```python
def decompose_goal_to_dag(user_goal: str, llm_client: LLMClient) -> TaskDAG:
    """
    1. Send user goal to LLM with decomposition prompt
    2. Parse LLM response into semantic requirements
    3. Build DAG with dependencies
    4. Assign priority and node types
    """
    prompt = f"""
    Decompose the following user goal into a DAG of semantic requirements:

    Goal: {user_goal}

    Output format:
    - Nodes: List of semantic requirements
    - Edges: Dependencies between requirements
    - Priority: Execution order
    """

    response = llm_client.generate(prompt)
    dag = parse_dag_from_response(response)
    return dag
```

**Example**:

Input: "Find the best coffee product with good reviews and reasonable price"

Output DAG:
```
search_coffee_products (priority: 1)
        ↓
extract_product_info (priority: 2)
        ↓
    ┌───┴───┐
filter_reviews  filter_prices (priority: 3)
    └───┬───┘
        ↓
compare_and_rank (priority: 4)
```

### 8.2 Vector Retrieval

**Purpose**: Find semantically similar states using embeddings.

**Algorithm**:

```python
def search_semantic_states(
    requirement: str,
    embedding_model: EmbeddingModel,
    vector_index: VectorIndex,
    top_k: int = 10
) -> List[Tuple[State, float]]:
    """
    1. Embed semantic requirement
    2. KNN search in vector index
    3. Return top-k states with similarity scores
    """
    query_embedding = embedding_model.embed(requirement)
    state_ids, scores = vector_index.search(query_embedding, top_k)
    states = [get_state(sid) for sid in state_ids]
    return list(zip(states, scores))
```

**Similarity Metrics**:
- Cosine Similarity (default)
- Euclidean Distance
- Dot Product

### 8.3 Graph Traversal

**Purpose**: Explore neighboring states for contextual enrichment.

**Algorithm**:

```python
def explore_neighbors(
    current_state: State,
    graph_store: GraphStore,
    max_depth: int = 2,
    max_neighbors: int = 5
) -> List[State]:
    """
    1. Get immediate neighbors (1-hop)
    2. Recursively explore up to max_depth
    3. Filter by relevance
    4. Return expanded state list
    """
    visited = set()
    queue = [(current_state, 0)]
    neighbors = []

    while queue:
        state, depth = queue.pop(0)
        if state.id in visited or depth > max_depth:
            continue
        visited.add(state.id)
        neighbors.append(state)

        if depth < max_depth:
            adjacent = graph_store.get_neighbors(state.id)
            queue.extend([(s, depth+1) for s in adjacent[:max_neighbors]])

    return neighbors
```

### 8.4 Semantic Satisfaction Evaluation

**Purpose**: Use LLM to evaluate if retrieved states satisfy semantic requirements.

**Algorithm**:

```python
def evaluate_satisfaction(
    requirement: str,
    states: List[State],
    llm_client: LLMClient
) -> SatisfactionResult:
    """
    1. Format states as context for LLM
    2. Ask LLM to evaluate semantic match
    3. Parse satisfaction level and confidence
    4. Return evaluation result
    """
    prompt = f"""
    Semantic Requirement: {requirement}

    Retrieved States:
    {format_states(states)}

    Question: Do these states satisfy the semantic requirement?

    Output:
    - Satisfaction Level: FULLY_SATISFIED / PARTIALLY_SATISFIED / NOT_SATISFIED
    - Confidence Score: 0.0 to 1.0
    - Reasoning: Brief explanation
    """

    response = llm_client.generate(prompt)
    result = parse_satisfaction_result(response)
    return result
```

**Satisfaction Levels**:
- `FULLY_SATISFIED`: States completely match requirement (score >= 0.8)
- `PARTIALLY_SATISFIED`: States partially match (0.5 <= score < 0.8)
- `NOT_SATISFIED`: States do not match (score < 0.5)

### 8.5 Reranking

**Purpose**: Improve retrieval quality using cross-encoder reranking.

**Algorithm**:

```python
def rerank_results(
    query: str,
    states: List[State],
    rerank_model: RerankModel,
    top_k: int = 10
) -> List[Tuple[State, float]]:
    """
    1. Convert states to documents (text representations)
    2. Use rerank model to compute relevance scores
    3. Sort by relevance
    4. Return top-k reranked results
    """
    documents = [state.to_document() for state in states]
    response = rerank_model.rerank(query, documents, top_k=top_k)

    reranked_states = []
    for result in response.results:
        state = states[result.index]
        reranked_states.append((state, result.score))

    return reranked_states
```

---

## 9. API Design

### 9.1 Memory API

**StateManager**:
```python
class StateManager:
    def create_state(self, state: State) -> State
    def get_state(self, state_id: str) -> Optional[State]
    def update_state(self, state: State) -> State
    def delete_state(self, state_id: str) -> bool
    def list_states(self, user_id: str = None, session_id: str = None,
                   state_type: StateType = None) -> List[State]
    def find_states_by_attributes(self, **filters) -> List[State]
```

**ActionManager**:
```python
class ActionManager:
    def create_action(self, action: Action) -> Action
    def get_action(self, source_id: str, target_id: str) -> Optional[Action]
    def update_action(self, action: Action) -> Action
    def delete_action(self, source_id: str, target_id: str) -> bool
    def list_actions(self, source_id: str = None, target_id: str = None) -> List[Action]
```

**WorkflowMemory**:
```python
class WorkflowMemory:
    def add_workflow_step(self, state: State, previous_state_id: str = None,
                         action: Action = None) -> None
    def get_workflow_trajectory(self, session_id: str) -> List[State]
    def find_workflow_paths(self, start_state_id: str, end_state_id: str) -> List[List[State]]
```

### 9.2 Reasoner API

```python
class Reasoner:
    def retrieve_similar_workflows(
        self, query: str, top_k: int = 10,
        filters: Dict[str, Any] = None
    ) -> List[RetrievalResult]

    def decompose_task(self, task: str) -> TaskDAG

    def evaluate_workflow_match(
        self, workflow: List[State], requirement: str
    ) -> SatisfactionResult

    def find_goal_relevant_states(
        self, goal: str, entry_states: List[str] = None
    ) -> List[State]
```

### 9.3 Services API

**LLM Client**:
```python
class LLMClient:
    def generate(self, messages: List[LLMMessage], temperature: float = 0.7,
                max_tokens: int = 1000, **kwargs) -> LLMResponse
    def generate_async(self, messages: List[LLMMessage], **kwargs) -> LLMResponse
    def generate_batch(self, message_lists: List[List[LLMMessage]], **kwargs) -> List[LLMResponse]
```

**Embedding Model**:
```python
class EmbeddingModel:
    def embed(self, text: str) -> EmbeddingResponse
    def embed_batch(self, texts: List[str]) -> List[EmbeddingResponse]
    def embed_async(self, text: str) -> EmbeddingResponse
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float
```

**Rerank Model**:
```python
class RerankModel:
    def rerank(self, query: str, documents: List[str], top_k: int = None) -> RerankResponse
    def rerank_batch(self, queries: List[str], documents_list: List[List[str]]) -> List[RerankResponse]
    def rerank_async(self, query: str, documents: List[str]) -> RerankResponse
```

---

## 10. Scalability & Performance

### 10.1 Current Performance Benchmarks

| Operation | Time (ms) | Notes |
|-----------|-----------|-------|
| State Creation | ~1 | In-memory NetworkX |
| Action Creation | ~0.5 | In-memory NetworkX |
| Vector Search (top-10) | ~10 | 1K states, FAISS |
| Graph BFS (depth 3) | ~5 | NetworkX |
| LLM Call (GPT-4) | 500-2000 | API latency dependent |
| Embedding (single) | 50-100 | OpenAI API |
| Reranking (10 docs) | 20-50 | Local BGE model |

### 10.2 Scalability Strategies

**Horizontal Scaling**:
- Distributed graph storage (Neo4j cluster)
- Sharded vector index (Pinecone, Weaviate)
- Load-balanced LLM API calls

**Vertical Scaling**:
- GPU-accelerated vector search (FAISS-GPU)
- In-memory caching (Redis)
- Batch processing for bulk operations

**Optimization Techniques**:
- Pre-compute embeddings for frequent queries
- Cache LLM responses (TTL-based)
- Graph indexing for common access patterns
- Lazy loading of state attributes
- Async I/O for API calls

### 10.3 Future Enhancements

1. **Distributed Architecture**
   - Microservices for each layer
   - Message queue (Kafka, RabbitMQ) for event streaming
   - Service mesh for inter-service communication

2. **Advanced Indexing**
   - Multi-modal embeddings (text + visual)
   - Temporal indexes for time-series queries
   - Geospatial indexes for location-based retrieval

3. **Real-time Processing**
   - Stream processing (Apache Flink)
   - Incremental graph updates
   - Live dashboard with WebSocket updates

4. **Multi-tenancy**
   - User isolation and data partitioning
   - Role-based access control (RBAC)
   - Resource quotas and rate limiting

---

## 11. Future Enhancements

### 11.1 Short-term (3-6 months)

- [ ] Advanced semantic reasoning with chain-of-thought prompting
- [ ] Multi-user collaboration and shared workflows
- [ ] Real-time processing pipeline with streaming
- [ ] Enhanced cognitive phrase detection algorithms
- [ ] Plugin system for custom state generators

### 11.2 Mid-term (6-12 months)

- [ ] Web-based visualization dashboard (React + D3.js)
- [ ] RESTful API service with OpenAPI spec
- [ ] Neo4j integration for distributed graph storage
- [ ] GPU-accelerated vector search with FAISS-GPU
- [ ] Automated testing framework with 90%+ coverage

### 11.3 Long-term (12+ months)

- [ ] Multi-modal understanding (text, image, video)
- [ ] Federated learning for privacy-preserving memory
- [ ] Active learning for continuous model improvement
- [ ] Cross-platform support (mobile, desktop, web)
- [ ] Enterprise features (SSO, audit logs, compliance)

---

## Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| Atomic Intent | Smallest unit of user interaction (e.g., click, type) |
| Semantic State | Meaningful behavioral unit composed of intents |
| Cognitive Phrase | High-level workflow pattern for aggregation |
| Goal/Task | Task-level understanding for retrieval |
| Memory Graph | Directed graph with states as nodes, actions as edges |
| Vector Embedding | Dense numerical representation of semantic meaning |
| Task DAG | Directed acyclic graph of decomposed task requirements |
| Semantic Satisfaction | LLM evaluation of requirement-state match |
| Reranking | Cross-encoder based relevance scoring |

### B. Technology Stack

| Component | Technology |
|-----------|-----------|
| Graph Storage | NetworkX (in-memory), Neo4j (future) |
| Vector Search | FAISS, Annoy |
| LLM APIs | OpenAI GPT, Anthropic Claude |
| Embeddings | OpenAI, Sentence-Transformers (BGE) |
| Reranking | BGE Cross-Encoder, MaaS API |
| Data Models | Pydantic, dataclasses |
| Testing | pytest, unittest |
| Code Style | Google Python Style Guide, pylint |

### C. References

- [NetworkX Documentation](https://networkx.org/)
- [Sentence-Transformers](https://www.sbert.net/)
- [FAISS](https://github.com/facebookresearch/faiss)
- [OpenAI API](https://platform.openai.com/docs/api-reference)
- [Anthropic Claude API](https://docs.anthropic.com/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

---

**Document Version**: 1.0.0
**Last Updated**: January 2025
**Maintained by**: Zheng Wang