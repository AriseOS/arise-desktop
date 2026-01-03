# ScraperAgent Specification

**Agent Type**: `scraper_agent`

## What It Does

Extracts data from the current web page. It reads what's on screen and pulls out structured information.

**Key point**: scraper_agent doesn't navigate. It works on whatever page the browser is currently showing. Use `browser_agent` to get to the page first.

## Required Parameters

**ALWAYS specify these two parameters:**

```yaml
inputs:
  extraction_method: "script"   # REQUIRED: Always use "script"
  dom_scope: "full"             # REQUIRED: "full" for lists, "partial" for single items
```

## Basic Usage (v2 Format)

```yaml
- id: extract-products
  agent: scraper_agent
  inputs:
    extraction_method: "script"
    dom_scope: "full"
    data_requirements:
      user_description: "Extract product names and prices"
      output_format:
        name: "Product name"
        price: "Price"
  outputs:
    extracted_data: products  # Always returns List[Dict]
```

## Input Parameters

### Required
```yaml
inputs:
  data_requirements:
    user_description: "What to extract"    # Natural language description
    output_format:                          # Field definitions
      field_name: "Field description"
```

### Optional
```yaml
inputs:
  extraction_method: llm      # llm (default) | script
  dom_scope: partial          # partial (default) | full
  data_requirements:
    user_description: "..."
    output_format: {...}
    sample_data:              # Example data to guide extraction
      - field_name: "example value"
    xpath_hints:              # XPath hints from recordings
      field_name: "//xpath/expression"
```

## Output Format

**Always returns a list**, even for single items:

```yaml
# Multiple items
[{name: "Product A", price: "$10"}, {name: "Product B", price: "$20"}]

# Single item
[{title: "Article Title", author: "John"}]
```

To access fields from a single-item result:
```yaml
"{{result.0.title}}"   # First item's title field
```

## Note: Page URL

The current page's URL is not in the DOM - it's browser metadata. In foreach loops, the URL is already available in the item variable (e.g., `{{product.url}}`) from the list extraction step.

## When to Use "full" vs "partial" DOM

- **full**: Extracting a list of items (all products, all links, etc.)
  ```yaml
  dom_scope: full
  extraction_method: script
  ```

- **partial** (default): Extracting specific content (title, description, details)
  ```yaml
  dom_scope: partial
  ```

## Using XPath from Recordings

When the user recorded extracting data, pass xpath as hints:

```yaml
inputs:
  data_requirements:
    user_description: "Extract product URLs"
    output_format:
      url: "Product URL"
    xpath_hints:
      url: "//*[@id='product-list']/div/a"
```

## Complete Examples (v2 Format)

### Extract from Current Page
```yaml
- id: get-products
  agent: scraper_agent
  inputs:
    extraction_method: script
    dom_scope: full
    data_requirements:
      user_description: "Extract all product URLs from the list"
      output_format:
        url: "Product detail URL"
        name: "Product name"
      xpath_hints:
        url: "//*[@class='product-card']/a"
        name: "//*[@class='product-card']/h3"
  outputs:
    extracted_data: product_list
```

### Navigate then Extract (Cooperation Pattern)
```yaml
steps:
  # Navigate first
  - id: go-to-page
    agent: browser_agent
    inputs:
      target_url: "https://shop.com/products"

  # Then extract
  - id: get-products
    agent: scraper_agent
    inputs:
      extraction_method: script
      dom_scope: full
      data_requirements:
        user_description: "Extract all product URLs"
        output_format:
          url: "Product URL"
    outputs:
      extracted_data: product_list
```

### Extract Detail Page Info
```yaml
- id: get-detail
  agent: scraper_agent
  inputs:
    extraction_method: llm
    dom_scope: partial
    data_requirements:
      user_description: "Extract product details"
      output_format:
        name: "Product name"
        price: "Price"
        description: "Description"
        rating: "Rating"
      sample_data:
        - name: "Example Product"
          price: "$99.00"
          description: "A great product"
          rating: "4.5"
  outputs:
    extracted_data: product_detail
```

## How It Works

1. **Get DOM**: Fetch page content (partial or full)
2. **Check Cache**: Reuse cached extraction script if exists
3. **Generate Script**: LLM creates Python extraction script
4. **Execute**: Run script to extract data
5. **Validate**: Verify extracted data matches format
6. **Cache**: Store script for future reuse
