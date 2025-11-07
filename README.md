# Ami - AI That Learns by Watching You Work

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**We're building AI that replaces clicking and typing with natural collaboration.**

Ami learns by observing how human experts actually work, continuously accumulating professional knowledge to autonomously complete complex tasks like a human would. This isn't "better automation tools"—**it's the next generation of human-computer interaction.**

> **Computers that work for you, not the other way around.**

## 🌟 Core Vision

Ami is the first **Evolvable Agent** that inherits human experts' tacit knowledge and continuously evolves through three technical engines:

- **🧠 Behavioral Memory Engine**: Learns from real operations, not programmed rules
- **🎯 Dynamic Planning Engine**: Proactively understands goals and plans workflows
- **⚡ Generative Execution Engine**: Operates any software UI via dynamic code generation

**Key Metrics**:
- ✅ Task success rate: >95% (on learned scenarios)
- 💰 Execution cost: $0.02–$0.05 per task (95% cheaper than general AI agents)
- 🚀 Zero learning curve: Just do it once, Ami learns automatically

## 🏗️ System Architecture

Ami v2.0 uses a **Local-First + Cloud-Enhanced** architecture with 4 core components:

```
┌────────────────────────────────────────┐
│       User's Computer (Local)          │
│                                        │
│  ┌──────────────┐  ┌───────────────┐  │
│  │ Desktop App  │  │   Chrome      │  │
│  │  (Tauri)     │  │  Extension    │  │
│  └──────┬───────┘  └───────┬───────┘  │
│         │                  │          │
│         └─────────┬────────┘          │
│                   ↓                   │
│    ┌─────────────────────────────┐   │
│    │   Local Backend             │   │
│    │   (Python + FastAPI)        │   │
│    │                             │   │
│    │   • Workflow Execution      │   │
│    │   • Browser Automation      │   │
│    │   • Local Storage (~/.ami)  │   │
│    │   • Cloud API Proxy         │   │
│    └────────────┬────────────────┘   │
└─────────────────┼─────────────────────┘
                  │ HTTPS
                  ↓
┌────────────────────────────────────────┐
│     Cloud Backend (Server)             │
│     (Python + FastAPI)                 │
│                                        │
│   • User Authentication                │
│   • Intent Extraction (LLM)            │
│   • MetaFlow Generation (LLM)          │
│   • Workflow Generation (LLM)          │
│   • Data Storage (File System + DB)    │
└────────────────────────────────────────┘
```

### Key Design Principles

- **Local-First Execution**: Workflows run on your computer with your browser session - fast, private, and cost-effective
- **Cloud-Powered Intelligence**: AI analysis (Intent extraction, Workflow generation) happens in the cloud with powerful LLMs
- **Clean Separation**: Local Backend handles execution, Cloud Backend handles learning and storage
- **User Privacy**: Sensitive operations stay local; only anonymized data used for improvement

### Three Technical Engines

**1. Behavioral Memory Engine** - Learning from Real Operations
- **Intent Block Abstraction**: Extracts standardized "intent units" from diverse operations
- **Temporal Graph Construction**: Records operation sequences as graph structures
- **Dual-Temporal Model**: Handles both software updates (hard rules) and habit evolution (soft rules)

**2. Dynamic Planning Engine** - Proactive Workflow Generation
- **Online-Offline Hybrid Analysis**: Mines conditional branches, loops, and periodic patterns from massive temporal data
- **Knowledge Memory Graph**: Understands logical relationships between tasks
- **Proactive Intelligence**: Actively understands high-level goals and plans workflows instead of passively waiting for instructions

**3. Generative Execution Engine** - Operating Any Software
- **Vibe Coding**: Dynamically generates execution code leveraging LLM capabilities
- **Computer Use Agent**: Directly operates software UI, escaping API ecosystem limitations
- **Cost Optimization**: Only uses LLM when learning; execution is nearly free

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 16+ (for frontend)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/your-org/agentcrafter.git
cd agentcrafter
```

2. **Set up environment variables**
```bash
# Required: LLM API keys
export OPENAI_API_KEY=your_openai_key
export ANTHROPIC_API_KEY=your_anthropic_key
```

3. **Install dependencies**
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install browser automation dependencies
playwright install chromium --with-deps
```

4. **Start the services**

**Using convenience scripts (Recommended)**:
```bash
# Start both backends
./scripts/start_both_backends.sh

# Or start individually
./scripts/start_local_backend.sh   # Port 8000
./scripts/start_cloud_backend.sh   # Port 9000
```

**Or manually**:
```bash
# Local Backend (Required - runs on your computer)
cd src/local_backend
pip install -r requirements.txt
python main.py
# Accessible at: http://localhost:8000

# Cloud Backend (Development - runs locally for testing)
cd src/cloud_backend
pip install -r requirements.txt
python main.py
# Accessible at: http://localhost:9000
```

### First Steps

1. Open your browser and install the Chrome Extension (dev mode)
2. Click "Start Recording" and perform a task normally
3. Click "Stop Recording" - Ami will generate a workflow
4. Execute the workflow with one click - Ami handles the automation

**API Documentation**:
- Local Backend: http://localhost:8000/docs
- Cloud Backend: http://localhost:9000/docs

## 💡 How It Works

### The Learning-Executing Loop

```
User performs task → Behavioral Memory Engine learns → Extracts reusable Intents → Stores in Memory Graph
                                                                                        ↓
User requests new task ← Generative Execution Engine executes ← Dynamic Planning Engine plans ← Retrieves & combines Intents
                                                                                        ↓
                                                        System continuously evolves with each new task
```

### Example: Market Analyst Workflow

**First Time (Learning)**:
```
You manually scrape coffee product data from Allegro.pl
→ Ami observes: search, pagination, extraction, export
→ Ami creates: "scrape_allegro_products" Intent
```

**Second Time (Reuse)**:
```
You ask: "Scrape tea products"
→ Ami recognizes: same website, different parameter
→ Ami executes: reuses Intent with parameter="tea"
```

**Third Time (Composition)**:
```
You ask: "Compare coffee prices on Allegro and Amazon"
→ Ami understands: needs to combine two Intents
→ Ami executes: parallel scraping + comparison report
```

## 🔧 Core Components

### 1️⃣ Chrome Extension (User Interface)

**Location**: `src/chrome_extension/`

Records user operations in the browser:
- Captures clicks, inputs, navigation
- Real-time operation tracking
- One-click workflow execution
- Progress monitoring

### 2️⃣ Local Backend (Execution Engine)

**Location**: `src/local_backend/`

Runs on your computer to execute workflows:
- **Workflow Executor**: Loads and executes YAML workflows using BaseAgent
- **Browser Manager**: Manages global browser session (reused across workflows)
- **Storage Manager**: Local file system management (`~/.ami/`)
- **Cloud Client**: Proxies requests to Cloud Backend (secure Token management)

```python
from src.local_backend.services.workflow_executor import WorkflowExecutor

executor = WorkflowExecutor()
task_id = await executor.execute_workflow_async(user_id, workflow_name)
```

### 3️⃣ Cloud Backend (AI Analysis)

**Location**: `src/cloud_backend/`

Runs on server to generate workflows:
- **Recording Service**: Receives and stores user operations
- **Intent Extraction**: LLM-based semantic understanding
- **MetaFlow Generation**: Intermediate workflow representation
- **Workflow Generation**: Creates executable YAML from MetaFlow
- **Storage Service**: File system + PostgreSQL database

### 4️⃣ BaseAgent Framework

**Location**: `src/base_app/`

The core execution engine used by Local Backend:
- **Workflow Engine**: Executes YAML-based workflow definitions
- **Memory System**: Three-layer architecture (Variables, KV Storage, Long-term Memory)
- **Tool Integration**: Browser automation, Android tools, custom tools
- **Agent Types**: TextAgent, ToolAgent, CodeAgent for different step types

## 📖 Documentation

### Quick Links
- **[CLAUDE.md](./CLAUDE.md)** - AI development guide and project overview
- **[docs/README.md](./docs/README.md)** - Complete documentation index

### Architecture Documents
- [v2.0 Architecture Overview](./docs/platform/architecture.md) - Complete system design
- [Component Overview](./docs/platform/components_overview.md) - Four core components explained
- [Refactoring Plan](./docs/platform/refactoring_plan_2025-11-07.md) - Migration to v2.0 architecture
- [System Flow Analysis](./docs/platform/flow_analysis.md) - End-to-end data flow

### Component Documentation
- [BaseAgent Architecture](./docs/baseagent/ARCHITECTURE.md) - Core execution framework
- [Local Backend README](./src/local_backend/README.md) - Local execution engine setup
- [Cloud Backend README](./src/cloud_backend/README.md) - Cloud services setup

### Developer Guides
- [Development Guide](./docs/guides/DEVELOPMENT_GUIDE.md) - Developer quickstart
- [Testing Guide](./tests/README.md) - How to run tests

## 🎯 Use Cases

### Individual Users
- **Market Analysts**: Auto-scrape competitor pricing across multiple e-commerce sites
- **Supply Chain Analysts**: Extract material data from complex ERP systems (SAP, Oracle)
- **E-commerce Operators**: Collect product information across platforms
- **Finance Analysts**: Export and consolidate reports from multiple systems

**Value**: Save 10-15 hours weekly, 100x ROI on $20/month subscription

### Enterprises
- **Amplifying Expertise**: Top performer does it once, entire team can use it
- **Institutional Memory**: Expert judgment captured and shared, not lost when employees leave
- **Best Practices Spread**: System identifies efficient workflows and suggests them to others

**Value**: Transform tacit knowledge into organizational assets, continuous improvement

## 🧪 Testing

```bash
# Run all tests
pytest

# Run BaseApp tests
cd src/base_app
pytest tests/ -v

# Run specific module tests
pytest tests/test_browser_tool.py -v

# Run with coverage
pytest --cov=tools --cov-report=html
```

## 🛣️ Roadmap

### ✅ Phase 1: Architecture Refactoring (Completed)
- [x] Local Backend + Cloud Backend split architecture
- [x] BaseAgent framework with workflow engine
- [x] Browser tool integration with session reuse
- [x] Chrome Extension for recording
- [x] Intent Builder (Intent extraction, MetaFlow, Workflow generation)
- [x] Storage unification (~/.ami/)

### 🔄 Phase 2: MVP Development (Current - Q1 2025)
- [ ] Desktop App (Tauri) with workflow management UI
- [ ] Complete recording → generation → execution flow
- [ ] Production deployment (Cloud Backend)
- [ ] Beta testing with 50 users
- [ ] Performance optimization (>95% success rate)

### 🚀 Phase 3: Product Launch (Q2-Q3 2025)
- [ ] Individual subscription ($20/month)
- [ ] Freemium tier (100 executions/month)
- [ ] 1,000 paying users
- [ ] 5 enterprise pilots
- [ ] Content marketing & PLG strategy

### 🌟 Phase 4: Enterprise Scale (Q4 2025+)
- [ ] Enterprise subscription with team features
- [ ] Advanced Intent composition and sharing
- [ ] Cross-platform integration (Windows, Linux)
- [ ] Marketplace for community-created Intents

## 🤝 Contributing

We welcome contributions! Please see our development guidelines:

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Follow the code style in [CLAUDE.md](./CLAUDE.md)
4. Write tests for new features
5. Submit a Pull Request

**Important**: Always use English for code comments, docstrings, and log messages.

## 💬 Community & Support

- **Documentation**: [docs/README.md](./docs/README.md)
- **Issues**: [GitHub Issues](https://github.com/your-org/agentcrafter/issues)
- **Email**: shenyouren@gmail.com

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

## 🙏 Acknowledgments

Ami is built on the shoulders of giants:

- [browser-use](https://github.com/browser-use/browser-use) - AI browser automation
- [Anthropic Claude](https://www.anthropic.com/) - Powerful AI capabilities
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Playwright](https://playwright.dev/) - Cross-browser automation

---

## 🌟 Our Vision

We're not building "better RPA" or "cheaper AI agents."

We're creating a new category: **Evolvable Agents**

The difference:
- **No programming required** — learns by watching
- **Never becomes obsolete** — adapts to changes automatically
- **Gets smarter over time** — accumulates knowledge, doesn't reset
- **Economically viable** — 95% cheaper to run than generic AI agents
- **Actually reliable** — learned from real successes, not hallucinated guesses

**This is the first automation platform that inherits human expertise and evolves continuously.**

---

⭐ **If Ami helps you work smarter, give us a star!**
