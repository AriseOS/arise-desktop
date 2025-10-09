# Memory System - Graph-Based User Behavior Memory System

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-google-blue.svg)](https://google.github.io/styleguide/pyguide.html)

## 🎯 Overview

Memory System is a comprehensive, graph-based memory management platform designed to capture, process, and reason about user behaviors in web/app interactions. It implements a sophisticated four-level modeling architecture combined with a five-layer system design to provide intelligent memory storage, retrieval, and analysis capabilities.

**Current Version**: v1.0.0

### Key Features

- **🧩 Four-Level Modeling**: From atomic intents to user goals
- **🏗️ Five-Layer Architecture**: Modular design for scalability
- **📊 Graph-Based Storage**: Semantic states as nodes, actions as edges
- **🤖 Multi-LLM Support**: OpenAI, Anthropic Claude, and more
- **🔍 Intelligent Retrieval**: Goal-oriented semantic search
- **🔄 Workflow Processing**: Automated semantic extraction from user actions
- **⚡ Vector Embeddings**: Fast semantic similarity search
- **🎨 Cognitive Phrase Analysis**: High-level behavior pattern recognition

---

## 🏗️ Architecture

### Four-Level Modeling Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Four-Level Modeling                          │
├─────────────────────────────────────────────────────────────────┤
│ Level 1 - Atomic Intents                                        │
│   • Basic user operations: ClickElement, TypeText, CopyText     │
│   • Extracted from browser/app events                           │
│   • Stored with full context and metadata                       │
├─────────────────────────────────────────────────────────────────┤
│ Level 2 - Semantic States (Graph Nodes)                         │
│   • Meaningful behavioral states composed of intents            │
│   • Examples: InspectProductPrice, SelectProduct                │
│   • Core building blocks of the memory graph                    │
├─────────────────────────────────────────────────────────────────┤
│ Level 3 - Cognitive Phrases                                     │
│   • High-level workflow patterns for aggregation                │
│   • Examples: Browsing, Information Extraction                  │
│   • Used for statistical analysis and reporting                 │
├─────────────────────────────────────────────────────────────────┤
│ Level 4 - User Goals/Tasks                                      │
│   • Task-level understanding for intelligent retrieval          │
│   • Examples: Compare Coffee Products, Find Best Deal           │
│   • Supports goal-oriented memory search                        │
└─────────────────────────────────────────────────────────────────┘
```

### Five-Layer System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    System Architecture                          │
├─────────────────────────────────────────────────────────────────┤
│ 1. Data Capture Layer                                           │
│    • Event parsing and atomic intent extraction                 │
│    • Raw data collection from user interactions                 │
├─────────────────────────────────────────────────────────────────┤
│ 2. Semantic Abstraction Layer (Thinker)                         │
│    • Intent DAG building                                         │
│    • State generation from intent sequences                      │
│    • Cognitive phrase synthesis                                  │
├─────────────────────────────────────────────────────────────────┤
│ 3. Memory Graph Layer (GraphStore + Memory)                     │
│    • Graph-based state storage (NetworkX backend)                │
│    • State/Action/CognitivePhrase management                     │
│    • Relationship tracking and path finding                      │
├─────────────────────────────────────────────────────────────────┤
│ 4. Goal Index/Search Layer (Reasoner)                           │
│    • Task-level retrieval with vector embeddings                 │
│    • Semantic similarity search                                  │
│    • Goal decomposition and matching                             │
├─────────────────────────────────────────────────────────────────┤
│ 5. Services Layer                                                │
│    • LLM clients (OpenAI, Claude, Mock)                          │
│    • Embedding models (OpenAI, Local BGE)                        │
│    • Rerank models (Local BGE, MaaS)                             │
│    • Prompt management infrastructure                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Project Structure

```
Memory/
├── src/
│   ├── ontology/                    # Core data models
│   │   ├── intent.py                # Intent & AtomicIntent
│   │   ├── state.py                 # State & SemanticState
│   │   ├── action.py                # Action & TransitionEdge
│   │   └── cognitive_phrase.py      # CognitivePhrase
│   │
│   ├── memory/                      # Memory management
│   │   ├── memory.py                # Abstract interfaces
│   │   └── workflow_memory.py       # Concrete implementations
│   │
│   ├── graphstore/                  # Graph storage backends
│   │   ├── graph_store.py           # Abstract interface
│   │   ├── memory_graph.py          # MemoryGraph wrapper
│   │   └── networkx_graph.py        # NetworkX implementation
│   │
│   ├── services/                    # AI/ML services
│   │   ├── llm/                     # LLM clients
│   │   │   ├── llm_client.py        # Base client & factory
│   │   │   ├── openai_client.py     # OpenAI GPT models
│   │   │   ├── claude_client.py     # Anthropic Claude models
│   │   │   ├── mock_client.py       # Testing mock
│   │   │   └── llm_config_checker.py # Configuration validation
│   │   │
│   │   ├── embedding_model/         # Embedding models
│   │   │   ├── embedding_model.py   # Base model & factory
│   │   │   ├── openai_embedding.py  # OpenAI embeddings
│   │   │   └── local_bge_model.py   # Local BGE models
│   │   │
│   │   ├── rerank_model/            # Rerank models
│   │   │   ├── rerank_model.py      # Base model & factory
│   │   │   ├── local_bge_rerank_model.py
│   │   │   └── maas_rerank_model.py
│   │   │
│   │   └── prompt_base.py           # Prompt management
│   │
│   ├── thinker/                     # Workflow processing
│   │   ├── intent_dag_builder.py    # Intent DAG construction
│   │   ├── state_generator.py       # State generation
│   │   ├── cognitive_phrase_generator.py
│   │   └── workflow_processor.py    # Main processor
│   │
│   ├── reasoner/                    # Reasoning & retrieval
│   │   ├── reasoner.py              # Main reasoner
│   │   ├── task_dag.py              # Task DAG structure
│   │   ├── workflow_converter.py    # Workflow conversion
│   │   ├── retrieval_result.py      # Result models
│   │   ├── cognitive_phrase_checker.py
│   │   └── tools/                   # Reasoning tools
│   │       ├── retrieval_tool.py
│   │       └── task_tool.py
│   │
│   └── __init__.py                  # Package entry point
│
├── tests/                           # Test suite
├── examples/                        # Usage examples
├── docs/                            # Documentation
├── requirements.txt                 # Python dependencies
└── README.md                       # This file
```

---

## 🚀 Getting Started

### Prerequisites

- **Python**: 3.8 or higher
- **LLM API Keys**: OpenAI and/or Anthropic (optional for testing with mock)
- **Dependencies**: Listed in `requirements.txt`

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Memory
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Linux/Mac
   # venv\Scripts\activate   # On Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

   Example `.env` file:
   ```env
   # LLM API Keys
   OPENAI_API_KEY=your_openai_api_key_here
   ANTHROPIC_API_KEY=your_anthropic_api_key_here

   # Embedding Configuration (optional)
   EMBEDDING_PROVIDER=openai  # or local_bge
   EMBEDDING_MODEL=text-embedding-ada-002

   # Rerank Configuration (optional)
   RERANK_PROVIDER=local_bge  # or maas
   ```

---

## 💡 Quick Start

### Basic Usage Example

```python
from src import (
    Intent, State, Action, CognitivePhrase,
    WorkflowMemory, NetworkXGraphStorage,
    IntentType, StateType
)

# 1. Initialize the memory system
graph_storage = NetworkXGraphStorage()
memory = WorkflowMemory(graph_storage)

# 2. Create an atomic intent
intent = Intent(
    type=IntentType.CLICK_ELEMENT,
    timestamp=1609459200000,
    page_url="https://example.com/products",
    element_id="buy-button",
    text="Buy Now",
    user_id="user123",
    session_id="session456"
)

# 3. Create a semantic state
state = State(
    label="Product Selection",
    type=StateType.SELECT_PRODUCT,
    timestamp=1609459200000,
    page_url="https://example.com/products",
    atomic_intents=[intent],
    user_id="user123",
    session_id="session456",
    attributes={"product_id": "coffee-123", "price": 29.99}
)

# 4. Add state to memory
memory.create_state(state)

# 5. Create an action (transition)
action = Action(
    source_id=state1.id,
    target_id=state2.id,
    type="user_navigation",
    timestamp=1609459210000,
    attributes={"transition_time_ms": 10000}
)

# 6. Add action to memory
memory.create_action(action)

# 7. Query the memory
states = memory.state_manager.list_states(
    user_id="user123",
    session_id="session456"
)

print(f"Found {len(states)} states in memory")
```

### Workflow Processing Example

```python
from src import WorkflowProcessor, WorkflowMemory, NetworkXGraphStorage

# Initialize system
graph_storage = NetworkXGraphStorage()
memory = WorkflowMemory(graph_storage)
processor = WorkflowProcessor(memory)

# Process a user workflow
workflow_data = {
    "user_id": "user123",
    "session_id": "session456",
    "events": [
        {
            "type": "click",
            "element": "search-button",
            "timestamp": 1609459200000,
            "page_url": "https://example.com"
        },
        {
            "type": "input",
            "element": "search-box",
            "value": "coffee beans",
            "timestamp": 1609459205000,
            "page_url": "https://example.com"
        }
        # ... more events
    ]
}

# Process and extract semantic information
result = processor.process_user_workflow(workflow_data)
print(f"Extracted {len(result.states)} states")
print(f"Created {len(result.actions)} actions")
```

### LLM Integration Example

```python
from src import (
    create_llm_client,
    create_embedding_model,
    create_rerank_model,
    LLMProvider,
    EmbeddingProvider,
    RerankProvider
)
import openai

# Create LLM client
openai_client = openai.OpenAI(api_key="your-key")
llm_client = create_llm_client(
    provider=LLMProvider.OPENAI,
    api_client=openai_client,
    model_name="gpt-4"
)

# Create embedding model
embedding_model = create_embedding_model(
    provider=EmbeddingProvider.OPENAI,
    model_name="text-embedding-ada-002",
    api_key="your-key"
)

# Create rerank model
rerank_model = create_rerank_model(
    provider=RerankProvider.LOCAL_BGE,
    model_name="BAAI/bge-reranker-base"
)

# Use in reasoning
from src import Reasoner

reasoner = Reasoner(
    memory=memory,
    llm_client=llm_client,
    embedding_model=embedding_model,
    rerank_model=rerank_model
)

# Perform intelligent retrieval
query = "Find user actions related to product comparison"
results = reasoner.retrieve_similar_workflows(query, top_k=5)

for result in results:
    print(f"Workflow: {result.workflow_id}")
    print(f"Relevance: {result.score:.3f}")
    print(f"States: {len(result.states)}")
```

---

## 🔑 Core Components

### 1. Ontology - Core Data Models

#### Intent (Level 1)
Atomic user operations extracted from browser/app events.

```python
from src import Intent, IntentType

intent = Intent(
    type=IntentType.CLICK_ELEMENT,
    timestamp=1609459200000,
    page_url="https://example.com",
    element_id="button-1",
    text="Submit",
    user_id="user123",
    session_id="session456"
)
```

**Key Intent Types:**
- `CLICK_ELEMENT`, `DOUBLE_CLICK`, `RIGHT_CLICK`
- `TYPE_TEXT`, `COPY_TEXT`, `PASTE_TEXT`
- `NAVIGATE_TO`, `GO_BACK`, `REFRESH_PAGE`
- `FILL_INPUT`, `SELECT_OPTION`, `SUBMIT_FORM`
- `DRAG_ELEMENT`, `DROP_ELEMENT`, `HOVER_ELEMENT`

#### State (Level 2)
Semantic states composed of multiple intents - the primary graph nodes.

```python
from src import State, StateType

state = State(
    label="Product Search",
    type=StateType.SEARCH_PRODUCTS,
    timestamp=1609459200000,
    page_url="https://example.com/search",
    atomic_intents=[intent1, intent2],
    attributes={"query": "coffee", "results_count": 42},
    user_id="user123",
    session_id="session456"
)
```

**Key State Types:**
- **Browsing**: `BROWSE_CATALOG`, `BROWSE_PRODUCT`, `BROWSE_PAGE`
- **Information Extraction**: `INSPECT_PRODUCT_PRICE`, `EXTRACT_TEXT`
- **Comparison**: `COMPARE_PRODUCTS`, `COMPARE_PRICES`
- **Search**: `SEARCH_PRODUCTS`, `FILTER_RESULTS`, `SORT_RESULTS`
- **Selection**: `SELECT_PRODUCT`, `ADD_TO_CART`, `ADD_TO_WISHLIST`

#### Action (Graph Edges)
Transitions between states representing behavioral flows.

```python
from src import Action

action = Action(
    source_id=state1.id,
    target_id=state2.id,
    type="user_navigation",
    timestamp=1609459210000,
    duration=10000,  # milliseconds
    attributes={"trigger": "click", "confidence": 0.95}
)
```

#### CognitivePhrase (Level 3)
High-level workflow patterns for aggregation and analysis.

```python
from src import CognitivePhrase

phrase = CognitivePhrase(
    label="Product Comparison Workflow",
    description="User comparing multiple coffee products",
    state_ids=[state1.id, state2.id, state3.id],
    action_ids=[action1.id, action2.id],
    start_time=1609459200000,
    end_time=1609459500000,
    user_id="user123",
    session_id="session456",
    goal_id="coffee_shopping"
)
```

### 2. Memory - Memory Management

The memory layer provides CRUD operations for all memory entities.

```python
from src import WorkflowMemory, NetworkXGraphStorage

# Initialize memory
graph_storage = NetworkXGraphStorage()
memory = WorkflowMemory(graph_storage)

# State operations
memory.create_state(state)
retrieved_state = memory.get_state(state.id)
memory.update_state(updated_state)
memory.delete_state(state.id)

# Action operations
memory.create_action(action)
retrieved_action = memory.get_action(source_id, target_id)

# CognitivePhrase operations
memory.create_phrase(phrase)
retrieved_phrase = memory.get_phrase(phrase.id)

# High-level operations
memory.add_workflow_step(state, previous_state_id, action)
trajectory = memory.get_workflow_trajectory(session_id)
```

### 3. GraphStore - Graph Storage

Graph-based storage for semantic states and their relationships.

```python
from src import NetworkXGraphStorage, MemoryGraph

# Direct graph storage usage
graph_storage = NetworkXGraphStorage()

# Add nodes (states)
graph_storage.add_node(
    node_id=state.id,
    label=state.label,
    attributes=state.to_dict()
)

# Add edges (actions)
graph_storage.add_edge(
    source_id=action.source_id,
    target_id=action.target_id,
    edge_type=action.type,
    attributes=action.to_dict()
)

# Query graph
neighbors = graph_storage.get_neighbors(node_id)
path = graph_storage.find_shortest_path(start_id, end_id)
subgraph = graph_storage.get_subgraph(node_ids)
```

### 4. Services - AI/ML Services

#### LLM Clients

```python
from src import (
    create_llm_client,
    LLMProvider,
    LLMMessage
)

# Create client
llm_client = create_llm_client(
    provider=LLMProvider.OPENAI,
    api_client=openai_instance,
    model_name="gpt-4"
)

# Generate response
messages = [
    LLMMessage(role="system", content="You are a helpful assistant."),
    LLMMessage(role="user", content="Analyze this workflow...")
]
response = llm_client.generate(messages, temperature=0.7, max_tokens=1000)
print(response.content)
```

**Supported Providers:**
- OpenAI (GPT-3.5, GPT-4, GPT-4 Turbo)
- Anthropic (Claude 3 Opus, Sonnet, Haiku)
- Mock (for testing)

#### Embedding Models

```python
from src import create_embedding_model, EmbeddingProvider

# Create embedding model
embedding_model = create_embedding_model(
    provider=EmbeddingProvider.OPENAI,
    model_name="text-embedding-ada-002"
)

# Generate embeddings
text = "Search for coffee products"
response = embedding_model.embed(text)
print(f"Embedding dimension: {response.dimension}")
print(f"Vector: {response.embedding[:5]}...")  # First 5 dimensions

# Batch processing
texts = ["text1", "text2", "text3"]
responses = embedding_model.embed_batch(texts)
```

**Supported Providers:**
- OpenAI (text-embedding-ada-002, text-embedding-3-small/large)
- Local BGE (BAAI/bge-base-en-v1.5)

#### Rerank Models

```python
from src import create_rerank_model, RerankProvider

# Create rerank model
rerank_model = create_rerank_model(
    provider=RerankProvider.LOCAL_BGE,
    model_name="BAAI/bge-reranker-base"
)

# Rerank documents
query = "coffee products with best reviews"
documents = [
    "Coffee beans from Colombia",
    "Italian espresso machine",
    "Coffee grinder reviews"
]

response = rerank_model.rerank(query, documents)
top_results = response.get_top_k(2)

for result in top_results:
    print(f"Score: {result.score:.3f} - {result.document}")
```

### 5. Thinker - Workflow Processing

Transforms raw user interactions into semantic representations.

```python
from src import (
    WorkflowProcessor,
    IntentDAGBuilder,
    StateGenerator,
    CognitivePhraseGenerator
)

# Main workflow processor
processor = WorkflowProcessor(memory)
result = processor.process_user_workflow(workflow_data)

# Individual components
dag_builder = IntentDAGBuilder()
intent_dag = dag_builder.build_from_events(events)

state_generator = StateGenerator()
states = state_generator.generate_states_from_intents(intents)

phrase_generator = CognitivePhraseGenerator()
phrases = phrase_generator.generate_phrases(states, actions)
```

### 6. Reasoner - Intelligent Reasoning

Performs intelligent retrieval and goal decomposition.

```python
from src import Reasoner, RetrievalResult

# Initialize reasoner
reasoner = Reasoner(
    memory=memory,
    llm_client=llm_client,
    embedding_model=embedding_model
)

# Retrieve similar workflows
query = "Find workflows where user compares products"
results = reasoner.retrieve_similar_workflows(
    query=query,
    top_k=10,
    filters={"user_id": "user123"}
)

for result in results:
    print(f"Workflow: {result.workflow_id}")
    print(f"Score: {result.score:.3f}")
    print(f"States: {result.states}")

# Task decomposition
task = "Compare coffee products and find best deal"
task_dag = reasoner.decompose_task(task)
print(f"Decomposed into {len(task_dag.nodes)} subtasks")
```

---

## 🧪 Testing

### Run All Tests
```bash
pytest tests/
```

### Run Specific Test Categories
```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=src tests/
```

---

## 🛠️ Configuration

### LLM Configuration

Configure LLM providers via environment variables:

```env
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=4000

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-opus-20240229
ANTHROPIC_TEMPERATURE=0.7
ANTHROPIC_MAX_TOKENS=4000
```

### Embedding Configuration

```env
# OpenAI Embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002

# Local BGE Model
BGE_MODEL_NAME=BAAI/bge-base-en-v1.5
BGE_DEVICE=cpu  # or cuda
```

### System Configuration

```env
# Graph Storage
GRAPH_BACKEND=networkx
GRAPH_STORAGE_PATH=./data/graph.pkl

# Vector Index
VECTOR_INDEX_PATH=./data/vectors.pkl
VECTOR_DIMENSION=1536

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/memory_system.log
```

---

## 📊 Performance

### Benchmarks

- **State Creation**: ~1ms per state
- **Action Creation**: ~0.5ms per action
- **Vector Search**: ~10ms for top-10 (1000 states)
- **LLM Call**: 500-2000ms (provider-dependent)
- **Graph Traversal**: ~5ms for BFS (depth 3)

### Optimization Tips

1. **Batch Operations**: Use batch methods for bulk operations
2. **Vector Caching**: Pre-compute embeddings for frequent queries
3. **Graph Indexing**: Build indexes for frequently accessed paths
4. **LLM Caching**: Cache LLM responses for identical queries
5. **Async Processing**: Use async methods for I/O-bound operations

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

1. Fork and clone the repository
2. Create a virtual environment
3. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
4. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```
5. Run tests:
   ```bash
   pytest tests/
   ```

### Code Style

- Follow [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- Use type hints for all function signatures
- Write docstrings for all public APIs
- Maintain test coverage above 80%

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 📞 Contact & Support

- **Author**: Zheng Wang
- **Email**: your.email@example.com
- **GitHub**: [Repository URL]
- **Issues**: [GitHub Issues](https://github.com/yourusername/memory/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/memory/discussions)

---

## 🎯 Roadmap

### ✅ Phase 1: Core Foundation (Complete)
- [x] Four-level modeling architecture
- [x] Five-layer system design
- [x] Graph-based memory storage
- [x] Multi-LLM provider support
- [x] Embedding and rerank models
- [x] Basic workflow processing

### 🔄 Phase 2: Enhanced Intelligence (In Progress)
- [ ] Advanced semantic reasoning
- [ ] Goal decomposition algorithms
- [ ] Neighbor exploration with LLM evaluation
- [ ] Multi-user collaboration
- [ ] Real-time processing pipeline

### 🚀 Phase 3: Enterprise Features (Planned)
- [ ] Web-based visualization dashboard
- [ ] RESTful API service
- [ ] Distributed storage (Neo4j/ArangoDB)
- [ ] GPU-accelerated vector search
- [ ] Plugin system for extensibility
- [ ] Multi-tenant architecture

---

## 📚 Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [User Guide](docs/USER_GUIDE.md)
- [Developer Guide](docs/DEVELOPER_GUIDE.md)
- [Examples](examples/)

---

## 🙏 Acknowledgments

- NetworkX for graph data structures
- Sentence-Transformers for embedding models
- OpenAI and Anthropic for LLM APIs
- The open-source community

---

**Version**: 1.0.0 | **Last Updated**:  October 2025