// Workflow definitions registry

export const WORKFLOWS = {
  'allegro-coffee-collection': {
    apiVersion: "agentcrafter.io/v1",
    kind: "Workflow",
    metadata: {
      name: "allegro-coffee-collection-workflow",
      description: "Collect coffee product information from Allegro including product name, price, and sales count",
      version: "1.0.0",
      tags: ["scraper", "allegro", "coffee", "price-collection"]
    },
    steps: [
      {
        id: "init-vars",
        name: "Initialize variables",
        agent_type: "variable",
        description: "Initialize data collection variables",
        agent_instruction: "Initialize product collection variables"
      },
      {
        id: "extract-product-urls",
        name: "Extract coffee product URLs",
        agent_type: "scraper_agent",
        description: "Navigate to coffee category and extract all product URLs from first page",
        agent_instruction: "Visit Allegro coffee category page and extract all product URLs"
      },
      {
        id: "save-urls",
        name: "Save product URLs",
        agent_type: "variable",
        description: "Save extracted URLs to variable",
        agent_instruction: "Save product URLs to collection variable"
      },
      {
        id: "collect-product-details",
        name: "Collect product details",
        agent_type: "foreach",
        description: "Iterate through all coffee products and extract detailed information",
        source: "{{all_product_urls}}",
        item_var: "current_product",
        steps: [
          {
            id: "scrape-product-info",
            name: "Scrape product information",
            agent_type: "scraper_agent",
            description: "Extract product name, price, and sales count",
            agent_instruction: "Visit product detail page and extract name, price, and sales count"
          },
          {
            id: "append-product",
            name: "Add product to collection",
            agent_type: "variable",
            description: "Append product information to collection list",
            agent_instruction: "Add product to collection list"
          },
          {
            id: "store-product",
            name: "Store product to database",
            agent_type: "storage_agent",
            description: "Persist product information to database",
            agent_instruction: "Store coffee product information to database"
          }
        ]
      },
      {
        id: "prepare-output",
        name: "Prepare final output",
        agent_type: "variable",
        description: "Organize collection results and prepare final response",
        agent_instruction: "Prepare final output with collection summary"
      }
    ]
  }
}

// Default workflow key
export const DEFAULT_WORKFLOW = 'allegro-coffee-collection'

// Get workflow by key
export function getWorkflow(workflowKey) {
  return WORKFLOWS[workflowKey] || WORKFLOWS[DEFAULT_WORKFLOW]
}

// Get all workflow keys
export function getWorkflowKeys() {
  return Object.keys(WORKFLOWS)
}
