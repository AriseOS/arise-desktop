# Workflow Integration Tests

This directory contains tools and scripts for testing AgentCrafter workflows.

## run_workflow.py

A comprehensive workflow test runner that can load and execute any workflow YAML file.

### Usage

```bash
# Basic usage
python run_workflow.py <workflow_name> [options]

# List available workflows
python run_workflow.py --list

# Run built-in workflow
python run_workflow.py user-qa-workflow --input user_input="Hello, how are you?"

# Run user workflow with specific parameters
python run_workflow.py paginated-scraper-workflow \
    --url "https://example.com" \
    --max-pages 2 \
    --products-per-page 10

# Run with custom config
python run_workflow.py my-workflow \
    --config /path/to/config.yaml \
    --verbose

# Pass complex JSON input
python run_workflow.py my-workflow \
    --json '{"key1": "value1", "nested": {"key2": "value2"}}'

# Save results to file
python run_workflow.py my-workflow --input key=value --save
```

### Command Line Options

#### Positional Arguments
- `workflow`: Name of built-in/user workflow or path to YAML file

#### Input Options
- `--input, -i`: Input data as key=value pairs (can be used multiple times)
- `--json, -j`: Input data as JSON string

#### Workflow-specific Options
- `--url`: Target URL for scraper workflows
- `--max-pages`: Maximum pages to scrape
- `--products-per-page`: Products per page for pagination

#### Configuration Options
- `--config, -c`: Path to config file
- `--llm-provider`: LLM provider (openai, anthropic, etc.)
- `--llm-model`: LLM model name

#### Output Options
- `--save, -s`: Save result to JSON file
- `--verbose, -v`: Enable verbose logging

#### Special Commands
- `--list`: List available workflows and exit

### Examples

1. **Test the paginated scraper workflow:**
```bash
python run_workflow.py paginated-scraper-workflow \
    --url "https://example.com/products" \
    --max-pages 3 \
    --verbose
```

2. **Run a simple Q&A workflow:**
```bash
python run_workflow.py user-qa-workflow \
    --input user_input="What is the weather today?" \
    --llm-provider openai \
    --llm-model gpt-4
```

3. **Test with complex input and save results:**
```bash
python run_workflow.py my-custom-workflow \
    --json '{"target": "https://site.com", "config": {"depth": 2}}' \
    --save \
    --verbose
```

### Workflow File Locations

- **Built-in workflows**: `base_app/base_app/base_agent/workflows/builtin/`
- **User workflows**: `base_app/base_app/base_agent/workflows/user/`

### Output

The runner provides:
- Real-time execution logs
- Step-by-step progress tracking
- Final workflow results
- Error details if workflow fails
- Optional JSON file with complete execution details

### Requirements

Make sure to set up environment variables for LLM providers:
```bash
export OPENAI_API_KEY=your-key-here
export ANTHROPIC_API_KEY=your-key-here
```

Or provide them in the config file specified with `--config`.