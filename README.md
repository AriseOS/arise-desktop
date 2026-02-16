# Ami - AI-Powered Workflow Automation (Cloud Backend)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Building AI agents that learn from your actions and automate complex workflows.**

Ami allows you to record browser operations, describe tasks in natural language, and let AI automatically generate executable workflows. No programming required—just demonstrate once, and let AI handle the repetition.

> **From manual operations to automated workflows in minutes.**

## Core Features

- **Record Operations**: Capture browser actions in real-time and upload to cloud
- **Generate Workflows**: Describe tasks in natural language, AI generates executable workflows
- **Manage & Execute**: View, execute, and monitor your workflows with detailed results

## Architecture

This repository contains the **Cloud Backend** — the server-side services for AI-powered workflow generation and memory system.

The desktop app lives in a separate repository: [ami-desktop](https://github.com/your-org/ami-desktop).

```
┌─────────────────────────────────────────────────┐
│         Cloud Backend (Server)                  │
│         (Python FastAPI - Port 9000)            │
│                                                 │
│   • Recording Storage                           │
│   • Intent Extraction (LLM)                     │
│   • MetaFlow Generation (LLM)                   │
│   • Workflow Generation (LLM)                   │
│   • User Data Management                        │
└─────────────────────────────────────────────────┘
```

### Key Components

- **Intent Builder** (`src/cloud_backend/intent_builder/`) - Skills-based workflow generation using Claude Agent SDK
- **Memory System** (`src/cloud_backend/memgraph/`) - Graph-based memory for learning from user operations
- **Recording Service** - Receives and stores user operations
- **LLM Providers** (`src/common/llm/`) - LLM provider abstraction (Anthropic, OpenAI)

## Quick Start

### Prerequisites

- **Python 3.11+**

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/your-org/ami.git
cd ami
```

2. **Configure API Keys (Required)**
```bash
export OPENAI_API_KEY=your_openai_key
export ANTHROPIC_API_KEY=your_anthropic_key
```

3. **Install dependencies (use Python 3.11 virtualenv)**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start the Cloud Backend

```bash
./scripts/start_cloud_backend.sh
# Cloud Backend will start on port 9000
# API docs: http://localhost:9000/docs
```

## How It Works

### The Learning-Executing Loop

```
User performs task → Behavioral Memory Engine learns → Extracts reusable Intents → Stores in Memory Graph
                                                                                        ↓
User requests new task ← Generative Execution Engine executes ← Dynamic Planning Engine plans ← Retrieves & combines Intents
                                                                                        ↓
                                                        System continuously evolves with each new task
```

## Documentation

- **[CLAUDE.md](./CLAUDE.md)** - AI development guide and project overview
- **CONTEXT.md files** - Fractal documentation in each directory

## Testing

```bash
# Run cloud backend tests
./scripts/run_cloud_tests.sh

# Run integration tests
./scripts/run_integration_test.sh
```

## Contributing

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Follow the code style in [CLAUDE.md](./CLAUDE.md)
4. Write tests for new features
5. Submit a Pull Request

**Important**: Always use English for code comments, docstrings, and log messages.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

## Acknowledgments

- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) - Multi-turn agent framework
- [Anthropic Claude](https://www.anthropic.com/) - Powerful AI capabilities
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Neo4j](https://neo4j.com/) - Graph database for memory system
