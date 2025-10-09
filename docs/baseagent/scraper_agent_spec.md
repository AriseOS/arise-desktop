# ScraperAgent Specification

**Agent Type**: `scraper_agent`

## Purpose
Web scraping with browser automation. Extracts structured data from web pages.

## Input Parameters

### Required
```yaml
inputs:
  target_path: "https://example.com"          # Target URL to scrape
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
  extraction_method: "llm"        # "llm" | "script" (default: "llm")
  dom_scope: "partial"            # "partial" | "full" (default: "partial")
  session_id: "session-id"        # Browser session to reuse
  use_shared_session: true        # Use shared session from workflow
  options:
    max_items: 20                 # Max items to extract
    timeout: 30                   # Timeout in seconds
```

## Output
```yaml
outputs:
  extracted_data: "variable_name"  # Extracted data matching output_format
  message: "message_var"           # Status message (optional)
```

## Examples

### Extract URLs (List)
```yaml
- id: "scrape-urls"
  agent_type: "scraper_agent"
  agent_instruction: "Extract all product URLs"
  inputs:
    target_path: "https://example.com/products"
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

### Extract Details (Single)
```yaml
- id: "scrape-detail"
  agent_type: "scraper_agent"
  agent_instruction: "Extract product details"
  inputs:
    target_path: "{{product.url}}"
    extraction_method: "llm"
    data_requirements:
      user_description: "Extract product information"
      output_format:
        name: "Product name"
        price: "Price with currency"
        rating: "Rating"
      sample_data:
        - name: "Example"
          price: "$99"
          rating: "4.5"
  outputs:
    extracted_data: "product_detail"
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
