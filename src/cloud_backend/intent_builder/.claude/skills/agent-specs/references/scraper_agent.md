# ScraperAgent

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

## Basic Usage

```yaml
- id: "extract-products"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    dom_scope: "full"
    data_requirements:
      user_description: "Extract product names and prices"
      output_format:
        name: "Product name"
        price: "Price"
  outputs:
    extracted_data: "products"  # Always returns List[Dict]
```

## Using XPath from Recordings

When the user recorded extracting data, the recording captured which elements they selected. Pass this as `xpath_hints` to help find the same elements:

```yaml
inputs:
  data_requirements:
    user_description: "Extract product URLs"
    output_format:
      url: "Product URL"
    xpath_hints:
      url: "//*[@id='product-list']/div/a"  # From user's recording
```

The xpath shows exactly which elements the user was looking at. This makes extraction more reliable, especially on complex pages.

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
  dom_scope: "full"
  extraction_method: "script"
  ```

- **partial** (default): Extracting specific content (title, description, details)
  ```yaml
  dom_scope: "partial"
  ```

## Complete Example

```yaml
# Navigate first
- id: "go-to-page"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://shop.com/products"

# Then extract
- id: "get-products"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    dom_scope: "full"
    data_requirements:
      user_description: "Extract all product URLs from the list"
      output_format:
        url: "Product detail URL"
        name: "Product name"
      xpath_hints:
        url: "//*[@class='product-card']/a"
        name: "//*[@class='product-card']/h3"
  outputs:
    extracted_data: "product_list"
```
