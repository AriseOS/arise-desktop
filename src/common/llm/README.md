# Common LLM Service

Shared LLM provider implementations for all AgentCrafter modules.

## Usage

```python
from common.llm import AnthropicProvider, OpenAIProvider

# Use Anthropic Claude
provider = AnthropicProvider()
response = await provider.generate_response(
    system_prompt="You are a helpful assistant",
    user_prompt="What is 2+2?"
)

# Use OpenAI GPT-4
provider = OpenAIProvider(model_name="gpt-4-turbo-preview")
response = await provider.generate_response(
    system_prompt="You are a helpful assistant",
    user_prompt="What is 2+2?"
)
```

## Providers

- `AnthropicProvider`: Claude models (default: claude-sonnet-4-5-20250929)
- `OpenAIProvider`: GPT models (default: gpt-4-turbo-preview)

## Configuration

Set API keys via environment variables:
```bash
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
```

Or pass directly to constructor:
```python
provider = AnthropicProvider(api_key="your-key")
```
