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

Ami consists of three main layers:

```
┌─────────────────────────────────────────────────┐
│          Intent Builder Layer                    │
│  ┌──────────────────┐  ┌────────────────────┐   │
│  │ Intent Extraction │  │ MetaFlow Generator │   │
│  └──────────────────┘  └────────────────────┘   │
├─────────────────────────────────────────────────┤
│          BaseAgent Framework                     │
│  ┌──────────────────┐  ┌────────────────────┐   │
│  │ Workflow Engine  │  │ Memory System      │   │
│  │ StepAsAgent Arch │  │ (Variables/KV/LTM) │   │
│  └──────────────────┘  └────────────────────┘   │
├─────────────────────────────────────────────────┤
│          Tool Layer                              │
│  Browser Use | Android Use | Code Execution |... │
└─────────────────────────────────────────────────┘
```

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

4. **Start the service**

**Option A: BaseApp (Core Framework)**
```bash
cd src/base_app
baseapp start --port 8888 --host 0.0.0.0
```

**Option B: Web Platform (Full Stack)**
```bash
# Start backend
python client/web/start_backend.py

# In another terminal, start frontend
cd client/web && ./start_frontend.sh
```

### First Steps

1. Visit http://localhost:3000 (Web Platform) or http://localhost:8888 (BaseApp)
2. Perform a task once - Ami observes and learns
3. Ask Ami to execute similar tasks - it reuses and combines learned capabilities

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

### BaseAgent Framework

Located in `src/base_app/`, BaseAgent provides the standardized foundation:

- **Workflow Engine**: Executes YAML-based workflow definitions
- **Memory System**: Three-layer architecture (Variables, KV Storage, Long-term Memory)
- **Tool Integration**: Unified interface for browser, Android, and custom tools
- **Agent Types**: TextAgent, ToolAgent, CodeAgent for different step types

```python
from src.base_app.base_agent.core import BaseAgent

# Create agent with user-bound memory
agent = BaseAgent(config, user_id="user123")

# Load and execute workflow
workflow = agent._load_workflow('user-qa-workflow')
result = await agent.run_workflow(workflow, user_input)
```

### Intent Builder System

Located in `src/intent_builder/`, handles Intent-based workflow generation:

- **MetaFlow**: Intermediate representation between Intent Memory Graph and Workflow
- **Workflow Generator**: LLM-based workflow generation from MetaFlow
- **Prompt Builder**: Comprehensive prompt engineering for workflow generation
- **Validators**: YAML structure and field validation

### Web Platform

Located in `client/web/`, provides multi-user management:

- **Frontend**: React + TypeScript with Vite, Ant Design, Redux Toolkit
- **Backend**: FastAPI with SQLAlchemy, user/agent/session management
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Port Management**: Auto-allocation from pool (5001-5020) for agent instances

## 📖 Documentation

### Architecture & Design
- [CLAUDE.md](./CLAUDE.md) - Development guidance and project overview
- [BaseAgent Architecture](./docs/baseagent/ARCHITECTURE.md) - Core framework design
- [Contextual Dynamic Architecture](./docs/baseagent/contextual_dynamic_architecture.md) - Recommended approach
- [Platform Database](./docs/platform/database_architecture.md) - Database schema

### Developer Guides
- [Development Guide](./docs/guides/DEVELOPMENT_GUIDE.md) - Developer quickstart
- [Integration Testing Guide](./docs/guides/integration_testing_guide.md) - Testing strategies
- [AgentBuilder Architecture](./docs/agentbuilder/ARCHITECTURE.md) - AI-assisted agent generation

### Complete Documentation
See [docs/README.md](./docs/README.md) for the complete documentation index.

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

### ✅ Phase 1: Core Technology (Current)
- [x] BaseAgent framework with workflow engine
- [x] Memory system (Variables, KV, LTM)
- [x] Browser tool integration
- [x] Intent Builder v1 (Intent extraction, MetaFlow generation)
- [x] Web platform with multi-user support
- [ ] Complete Intent Memory Graph
- [ ] Production-ready demos

### 🔄 Phase 2: Product Launch (Next 6 Months)
- [ ] Individual subscription ($20/month)
- [ ] Freemium tier (100 executions/month)
- [ ] 1,000 paying users
- [ ] 5 enterprise pilots
- [ ] Content marketing & PLG strategy

### 🚀 Phase 3: Enterprise Scale (12+ Months)
- [ ] Enterprise subscription with team features
- [ ] Advanced Intent composition and sharing
- [ ] Cross-platform integration (Desktop, Mobile)
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
