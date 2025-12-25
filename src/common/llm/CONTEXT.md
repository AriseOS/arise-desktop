# src/common/llm/

LLM provider abstraction layer. Unified interface for different LLM backends.

## Providers

- `base_provider.py` - Abstract base class `BaseLLMProvider`
- `anthropic_provider.py` - Anthropic Claude API (single-turn)
- `openai_provider.py` - OpenAI GPT API (single-turn)
- `claude_agent_provider.py` - Claude Agent SDK (multi-turn with tools)

## Usage

```python
from src.common.llm import AnthropicProvider

provider = AnthropicProvider()
response = await provider.generate_response(system_prompt, user_prompt)
```

## Provider Types

**Single-turn (BaseLLMProvider):**
- `AnthropicProvider` - Claude models via API
- `OpenAIProvider` - GPT models via API

**Multi-turn Agent (ClaudeAgentProvider):**
- Uses Claude Agent SDK
- Supports tools: Read, Write, Edit, Bash, Glob
- Iterative execution with tool calls

## Environment Variables

```bash
ANTHROPIC_API_KEY=xxx
OPENAI_API_KEY=xxx
```
