# ScraperAgent Specification

**Agent Type**: `scraper_agent`

## Purpose
Data extraction from web pages. **scraper_agent ONLY extracts data from the current page** that the browser is on.

**IMPORTANT - Navigation Separation**:
- scraper_agent does NOT navigate to pages
- Use `browser_agent` to navigate first, then `scraper_agent` to extract
- scraper_agent always operates on the current page from the shared browser session

## Input Schema

The agent validates inputs using `INPUT_SCHEMA`. Access programmatically:
```python
from src.clients.desktop_app.ami_daemon.base_agent.agents import ScraperAgent
schema = ScraperAgent.get_input_schema()
```

### Required Fields
| Field | Type | Description |
|-------|------|-------------|
| `data_requirements` | dict\|str | Data extraction requirements with output_format |

### Optional Fields
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target_path` | str\|list | - | URL(s) to navigate (optional if already on page) |
| `interaction_steps` | list | - | Pre-extraction interactions (e.g., scroll) |
| `extraction_method` | str | "llm" | `llm` or `script` |
| `dom_scope` | str | "partial" | `partial` or `full` |
| `debug_mode` | bool | false | Enable debug logging |
| `max_items` | int | 0 | Max items to extract (0 = unlimited) |
| `timeout` | int | 30 | Timeout in seconds |

## Input Parameters (YAML)

### Required
```yaml
inputs:
  data_requirements:
    user_description: "What to extract"       # Natural language description
    output_format:                            # Expected output structure
      field_name: "field description"
    sample_data:                              # Example output (recommended)
      - field_name: "example value"
```

### Optional
```yaml
inputs:
  extraction_method: "llm"            # "llm" | "script" (default: "llm")
  dom_scope: "partial"                # "partial" | "full" (default: "partial")
  max_items: 20                       # Max items to extract
  timeout: 30                         # Timeout in seconds
```

## Output

**CRITICAL**: `extracted_data` is ALWAYS a **List[Dict]**, even for single item extraction.

```yaml
outputs:
  extracted_data: "variable_name"  # ALWAYS List[Dict], e.g. [{field: value}]
  message: "message_var"           # Status message (optional)
```

**Return Type Rules**:
- **List extraction** (multiple items): `[{url: "..."}, {url: "..."}, ...]`
- **Single item extraction** (detail page): `[{name: "...", price: "..."}]` (list with 1 element)

**How to Reference Extracted Data in Workflow**:
- **In foreach loop**: Use the list directly
  ```yaml
  source: "{{product_urls}}"  # Iterate over the list
  ```
- **Access single item fields**: Use `.0` index to get first element
  ```yaml
  name: "{{product_info.0.name}}"      # Access first item's name field
  price: "{{product_info.0.price}}"    # Access first item's price field
  ```

## Examples

### Extract URLs (List)
```yaml
# Step 1: Navigate to the page
- id: "navigate-to-products"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com/products"

# Step 2: Extract data from current page
- id: "scrape-urls"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      user_description: "Extract product URLs"
      output_format:
        url: "Product URL"
      sample_data:
        - url: "https://example.com/p/123"
  outputs:
    extracted_data: "product_urls"
```

### Extract Details (Single Item)
```yaml
# Step 1: Navigate to the product page
- id: "navigate-to-product"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{product.url}}"

# Step 2: Extract details from current page
- id: "scrape-detail"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      user_description: "Extract product information"
      output_format:
        name: "Product name"
        price: "Price with currency"
        rating: "Rating"
      sample_data:    # Single item: use dict (not list)
        name: "Example Product"
        price: "$99"
        rating: "4.5"
  outputs:
    extracted_data: "product_detail"  # Returns [{name: "...", price: "...", rating: "..."}]

# To use the extracted fields in next steps:
- id: "use-product-info"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      display_name: "{{product_detail.0.name}}"     # Access via .0 index
      display_price: "{{product_detail.0.price}}"
      display_rating: "{{product_detail.0.rating}}"
```

## Extraction Methods

- **llm**: Direct LLM extraction (flexible, slower, ONLY partial DOM)
- **script**: Auto-generated script (cached, faster, supports partial/full DOM)

## DOM Scope: When to Use "full" vs "partial"

### Use "full" - When extracting ALL matching patterns

**用户需求特征**:
- 需要提取**所有**的某类元素
- 关键词: "所有"、"全部"、"列表"、"每个"

**典型场景**:
- 提取列表页的**所有商品链接**
- 提取搜索结果的**所有结果**
- 提取分页导航的**所有页码**

**配置**: `dom_scope: "full"` + `extraction_method: "script"`

### Use "partial" - When extracting specific content

**用户需求特征**:
- 提取页面中的**特定内容**（不是全部）
- 关键词: "标题"、"价格"、"描述"、"详情"

**典型场景**:
- 提取单个商品的**标题、价格、描述**
- 提取文章的**正文内容**
- 提取页面的**特定信息**

**配置**: `dom_scope: "partial"`

### 简单判断

```
需求包含 "所有"、"列表" → full + script
其他情况 → partial
```
