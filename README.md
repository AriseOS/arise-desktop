# Ami - AI-Powered Workflow Automation

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Building AI agents that learn from your actions and automate complex workflows.**

Ami allows you to record browser operations, describe tasks in natural language, and let AI automatically generate executable workflows. No programming required—just demonstrate once, and let AI handle the repetition.

> **From manual operations to automated workflows in minutes.**

## 🌟 Core Features

Ami provides three powerful ways to create and manage workflows:

- **📹 Record Operations**: Capture browser actions in real-time and upload to cloud
- **🤖 Generate Workflows**: Describe tasks in natural language, AI generates executable workflows
- **📋 Manage & Execute**: View, execute, and monitor your workflows with detailed results

**Key Benefits**:
- ✅ No coding required - describe what you want in plain English
- 🚀 Fast iteration - from idea to working workflow in minutes
- 💰 Cost-effective - AI-powered generation with local execution
- 🔒 Privacy-focused - sensitive operations run locally on your machine

## 🏗️ System Architecture

Ami uses a **Desktop-First + Cloud-Enhanced** architecture:

```
┌─────────────────────────────────────────────────┐
│           Desktop App (Tauri + React)           │
│                                                 │
│   • Recording Interface                         │
│   • Workflow Generation UI                      │
│   • Workflow Management                         │
│   • Execution Monitoring                        │
│                                                 │
│         ↓ (manages lifecycle)                   │
│                                                 │
│    ┌──────────────────────────────────────┐    │
│    │   App Backend Daemon                 │    │
│    │   (Python FastAPI - Port 8765)       │    │
│    │                                      │    │
│    │   • Browser Recording (CDP)          │    │
│    │   • Workflow Execution               │    │
│    │   • Local Storage (~/.ami)           │    │
│    │   • Cloud API Proxy                  │    │
│    └──────────────┬───────────────────────┘    │
└───────────────────┼──────────────────────────────┘
                    │ HTTPS
                    ↓
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

### Key Design Principles

- **Desktop-First**: Single desktop app with embedded Python daemon - no browser extension needed
- **Automatic Lifecycle**: Daemon starts with app, stops when app closes - zero manual management
- **Local Execution**: Workflows run on your computer - fast, private, and secure
- **Cloud Intelligence**: AI-powered workflow generation happens in the cloud
- **Clean Separation**: Desktop handles UI/execution, Cloud handles AI/storage

### Three Core Workflows

**1. Recording Operations** - Capture Real Browser Actions
- Browser automation via Chrome DevTools Protocol (CDP)
- Real-time operation tracking (clicks, inputs, navigation)
- Upload recordings to cloud for AI analysis
- Local storage of all recorded sessions

**2. AI-Powered Generation** - From Description to Workflow
- Natural language task description
- LLM-based MetaFlow generation (intermediate representation)
- Automatic Workflow YAML generation
- Cloud storage with local download for execution

**3. Local Execution** - Run Workflows Privately
- BaseAgent framework with workflow engine
- Browser automation using Playwright
- Real-time progress monitoring
- Local result storage and management

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** (required by the desktop daemon and `browser-use>=0.1.0`)
- **Node.js 16+** (for desktop app frontend)
- **Rust** (for Tauri desktop app)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/your-org/ami.git
cd ami
```

2. **Configure API Keys (Required)**
```bash
# Set environment variables for LLM providers
export OPENAI_API_KEY=your_openai_key
export ANTHROPIC_API_KEY=your_anthropic_key

# Or add to your shell profile (~/.bashrc, ~/.zshrc)
echo 'export OPENAI_API_KEY=your_openai_key' >> ~/.bashrc
echo 'export ANTHROPIC_API_KEY=your_anthropic_key' >> ~/.bashrc
```

⚠️ **Important**: Make sure API keys are configured before starting services.

3. **Install dependencies (use Python 3.11 virtualenv)**
```bash
# Ensure Python 3.11 is active before creating the env
python3.11 --version
python3.11 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install desktop daemon dependencies (browser-use needs 3.11+)
pip install -r src/clients/desktop_app/ami_daemon/requirements.txt

# Install browser automation dependencies
playwright install chromium --with-deps
```

### Python Environment & Debugging

`browser-use>=0.1.0` only ships wheels for Python ≥3.11. Use one of the following flows to install and debug consistently:

| Option | Steps |
| --- | --- |
| **Homebrew** | `brew install python@3.11` → `python3.11 -m venv .venv` → `source .venv/bin/activate` → reinstall `requirements.txt` and `src/clients/desktop_app/ami_daemon/requirements.txt` |
| **pyenv** | `brew install pyenv` → `pyenv install 3.11.8` → `pyenv local 3.11.8` → recreate `.venv` with `python -m venv .venv` and reinstall requirements |

Verify with `python --version` (should report 3.11.x). When debugging the desktop daemon, always activate the 3.11 venv before running `npm run tauri dev` so the daemon loads the correct interpreter.

### Start the System

**Step 1: Start Cloud Backend**
```bash
./scripts/start_cloud_backend.sh
# Cloud Backend will start on port 9000
# Accessible at: http://localhost:9000
```

**Step 2: Start Desktop App**
```bash
./scripts/run_desktop_app.sh
# Desktop app will:
# - Automatically start App Backend daemon on port 8765
# - Launch the Tauri desktop application
# - Daemon will stop automatically when you close the app
```

### First Workflow

1. **Record Operations** 📹
   - Click "录制操作" in desktop app
   - Configure URL and description
   - Start recording, perform actions in browser
   - Stop and upload to cloud

2. **Generate Workflow** 🤖
   - Click "生成 Workflow"
   - Describe your task in natural language
   - AI generates MetaFlow and Workflow
   - Workflow saved automatically

3. **Execute Workflow** 📋
   - Click "我的 Workflow"
   - Select a workflow to view details
   - Click "运行" to execute
   - Monitor progress and view results

**API Documentation**:
- App Backend: http://127.0.0.1:8765/health
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

### 1️⃣ Desktop App (User Interface)

**Location**: `src/clients/desktop_app/`

Built with Tauri (Rust + React) for cross-platform desktop experience:
- Recording interface for capturing browser operations
- Workflow generation UI with AI assistance
- Workflow management and execution monitoring
- Automatically manages App Backend daemon lifecycle

### 2️⃣ App Backend (Execution Engine)

**Location**: `src/app_backend/`

Runs on your computer to execute workflows:
- **Workflow Executor**: Loads and executes YAML workflows using BaseAgent
- **Browser Manager**: Manages global browser session (reused across workflows)
- **Storage Manager**: Local file system management (`~/.ami/`)
- **Cloud Client**: Proxies requests to Cloud Backend (secure Token management)

```python
from src.app_backend.services.workflow_executor import WorkflowExecutor

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

The core execution engine used by App Backend:
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
- [App Backend README](./src/app_backend/README.md) - Local execution engine setup
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
- [x] App Backend + Cloud Backend split architecture
- [x] BaseAgent framework with workflow engine
- [x] Browser tool integration with session reuse
- [x] Desktop App (Tauri) with automatic daemon management
- [x] Intent Builder (Intent extraction, MetaFlow, Workflow generation)
- [x] Storage unification (~/.ami/)

### 🔄 Phase 2: MVP Development (Current - Q1 2025)
- [x] Three independent workflow modules (Record, Generate, Manage)
- [ ] Complete recording → generation → execution flow testing
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
- **Issues**: [GitHub Issues](https://github.com/your-org/ami/issues)
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
