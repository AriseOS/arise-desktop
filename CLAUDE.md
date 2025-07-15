# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

AgentCrafter is a natural language-driven Agent building platform consisting of three main layers:
1. **BaseAgent Framework** - Standardized foundation for all agents
2. **Agent Builder System** - AI-assisted agent generation using tools like Claude Code
3. **Web Platform** - Multi-user management interface and runtime environment

## Development Commands

### Python Backend Development

**BaseApp (Core Agent Framework)**
```bash
# Install BaseApp dependencies
cd base_app
pip install -r requirements.txt

# Run BaseApp CLI
baseapp start --port 8000 --host 0.0.0.0
baseapp status
baseapp chat interactive

# Run tests
pytest tests/ -v
pytest tests/test_browser_tool.py -v

# Install browser dependencies
python scripts/install_chromium.py
playwright install chromium --with-deps
```

**Main Platform**
```bash
# Install main platform dependencies
pip install -r requirements.txt

# Development server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests with coverage
pytest --cov=tools --cov-report=html
pytest tests/test_browser_tool.py -v
```

### Frontend Development

**Web Client**
```bash
cd client/web/frontend
npm install
npm run dev          # Development server (Vite)
npm run build        # Production build
npm run preview      # Preview production build
```

**Backend API Server**
```bash
cd client/web
python start_backend.py    # Starts backend on port 8000
# OR manually:
cd backend
python main.py
```

### Integrated Development

**Full Stack Development**
```bash
# Start backend
python client/web/start_backend.py

# In another terminal, start frontend
cd client/web && ./start_frontend.sh
```

### Code Quality

```bash
# Python linting and formatting
black . --line-length 88
isort . --profile black
flake8 .
mypy .

# Run pre-commit hooks
pre-commit install
pre-commit run --all-files
```

## Architecture Overview

### Core Framework Structure

**BaseAgent System** (`base_app/`)
- **Core Framework**: `base_app/base_agent/core/` - BaseAgent class, workflow engine, state management
- **Agent Types**: `base_app/base_agent/agents/` - TextAgent, ToolAgent, CodeAgent implementations
- **Tools Integration**: `base_app/base_agent/tools/` - Browser automation, Android tools, memory management
- **Providers**: `base_app/base_agent/providers/` - LLM provider abstraction (OpenAI, Anthropic)
- **Workflows**: `base_app/base_agent/workflows/` - YAML-based workflow definitions and loader

**Agent Builder System** (`agent_builder/`)
- **ProjectManagerAgent**: Intelligent development assistant that analyzes requirements and guides code generation
- **ToolKnowledgeBase**: Comprehensive database of tool capabilities for intelligent recommendations
- **Claude Integration**: Interface for calling Claude Code and other AI tools to generate agents

**Web Platform** (`client/web/`)
- **Frontend**: React + TypeScript with Vite, Ant Design, Redux Toolkit
- **Backend**: FastAPI with SQLAlchemy, user management, agent lifecycle management
- **Database**: SQLite (dev) / PostgreSQL (prod) with user, agent, and session management

### Key Design Patterns

**Agent-as-Step Architecture**
- Each workflow step is an intelligent agent (TextAgent/ToolAgent/CodeAgent)
- Unified input/output schemas with strong typing
- Conditional execution and variable passing between steps

**Dynamic Loading Architecture**
- BaseAgent can dynamically load workflows, tools, and memory configurations
- Configuration-driven behavior changes without code modification
- Context preservation across the requirements ’ design ’ implementation chain

**Multi-Database Architecture**
```
users table          ’ User authentication and profiles
agents table          ’ Agent instances with port assignments  
port_allocation table ’ Port pool management (5001-5020)
agent_sessions table  ’ Multi-session conversation support
```

## Important Configuration

### Environment Variables
```bash
# Required for LLM providers
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# Database (optional, defaults to SQLite)
DATABASE_URL=sqlite:///./agentcrafter_users.db

# BaseApp specific
BASEAPP_HOST=0.0.0.0
BASEAPP_PORT=8888
```

### Key Configuration Files
- `base_app/config/baseapp.yaml` - BaseApp runtime configuration
- `base_app/base_agent/workflows/builtin/user-qa-workflow.yaml` - Default workflow definition
- `client/web/backend/agentcrafter_users.db` - Main user database
- `.env` files for environment-specific settings

## Database Schema

**Core Tables:**
- **users**: User authentication (username, email, hashed_password, permissions)
- **agents**: Agent instances (agent_id, user_id, port, name, type, status, config)
- **port_allocation**: Port pool management for agent services
- **agent_sessions**: Multi-session conversation support
- **user_sessions**: JWT session management

**Key Relationships:**
- Users (1:N) ’ agents, user_sessions, agent_sessions
- Agents (1:1) ’ port_allocation  
- Agents (1:N) ’ agent_sessions

See `docs/database_architecture.md` for complete schema documentation.

## Agent Development Patterns

### Creating Custom Agents

**Standard BaseAgent Extension:**
```python
class CustomAgent(BaseAgent):
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        # Register required tools
        self.register_tool('browser', BrowserTool())
        
    async def execute(self, input_data: Any, **kwargs) -> AgentResult:
        # Implement custom logic using workflow engine
        workflow = self._load_workflow('custom-workflow')
        result = await self.run_workflow(workflow, input_data)
        return AgentResult(success=result.success, data=result.final_result)
```

**Dynamic Agent Loading:**
```python
# Load agent from configuration
agent_definition = {
    "workflow": {...},  # Workflow steps definition
    "steps": [...],     # Agent step configurations  
    "memory": {...}     # Memory configuration
}

dynamic_agent = DynamicBaseAgent()
await dynamic_agent.load_components(agent_definition)
```

### Tool Integration

**Standard Tool Interface:**
```python
class CustomTool(BaseTool):
    async def execute(self, action: str, params: Dict) -> ToolResult:
        # Implement tool functionality
        return ToolResult(success=True, data=result)
    
    def get_available_actions(self) -> List[str]:
        return ["action1", "action2"]
```

**Tool Registration:**
```python
agent.register_tool('custom_tool', CustomTool())
result = await agent.use_tool('custom_tool', 'action1', {'param': 'value'})
```

## Testing Strategy

**Unit Tests:**
- `tests/unit/` - Individual component testing
- Mock external dependencies (LLM APIs, browser automation)
- Focus on BaseAgent core functionality and tool interfaces

**Integration Tests:**
- `tests/integration/` - End-to-end workflow testing  
- Test tool combinations and agent orchestration
- Database integration testing

**Browser Tool Testing:**
- `tests/test_browser_tool.py` - Comprehensive browser automation tests
- Use headless mode for CI/CD compatibility
- Test against real websites with proper rate limiting

## Security Considerations

**Agent Isolation:**
- Each agent runs on isolated ports (5001-5020 pool)
- User-based access control for all agent operations
- Configuration validation to prevent code injection

**API Security:**
- JWT-based authentication for all endpoints
- User isolation in database queries (`WHERE user_id = ?`)
- Input validation using Pydantic models

## Deployment Architecture

**Development Environment:**
- SQLite database for simplicity
- Local port allocation (5001-5020)
- Hot reload for both frontend and backend

**Production Environment:**
- PostgreSQL for robust data management
- Container orchestration for agent isolation
- Load balancing for multiple agent instances

**Port Management:**
- BaseApp: Fixed port 8888
- Dynamic agents: Auto-allocated from pool 5001-5020
- Frontend dev server: Port 3000
- Backend API: Port 8000

## Recent Architecture Documents

Key architecture analysis documents in the repository:
- `baseapp_agentic_architecture_analysis.md` - Initial BaseAgent suitability analysis
- `baseagent_dynamic_loading_architecture.md` - Simplified dynamic loading design
- `baseagent_contextual_dynamic_architecture.md` - Context-preserving architecture (recommended)
- `docs/database_architecture.md` - Complete database schema documentation

The recommended approach is the contextual dynamic architecture which preserves the complete context chain from user requirements through design to implementation, enabling better AI-assisted development.