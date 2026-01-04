// Workflow definitions registry (v2 format)

export const WORKFLOWS = {
  'allegro-coffee-collection': {
    apiVersion: "ami.io/v2",
    name: "allegro-coffee-collection-workflow",
    description: "Collect coffee product information from Allegro including product name, price, and sales count",
    version: "1.0.0",
    tags: ["scraper", "allegro", "coffee", "price-collection"],
    steps: [
      {
        id: "init-vars",
        intent_name: "Initialize variables",
        agent: "variable",
        intent_description: "Initialize data collection variables"
      },
      {
        id: "extract-product-urls",
        intent_name: "Extract coffee product URLs",
        agent: "scraper_agent",
        intent_description: "Navigate to coffee category and extract all product URLs from first page"
      },
      {
        id: "save-urls",
        intent_name: "Save product URLs",
        agent: "variable",
        intent_description: "Save extracted URLs to variable"
      },
      {
        id: "collect-product-details",
        intent_name: "Collect product details",
        intent_description: "Iterate through all coffee products and extract detailed information",
        foreach: "{{all_product_urls}}",
        as: "current_product",
        do: [
          {
            id: "scrape-product-info",
            intent_name: "Scrape product information",
            agent: "scraper_agent",
            intent_description: "Extract product name, price, and sales count"
          },
          {
            id: "append-product",
            intent_name: "Add product to collection",
            agent: "variable",
            intent_description: "Append product information to collection list"
          },
          {
            id: "store-product",
            intent_name: "Store product to database",
            agent: "storage_agent",
            intent_description: "Persist product information to database"
          }
        ]
      },
      {
        id: "prepare-output",
        intent_name: "Prepare final output",
        agent: "variable",
        intent_description: "Organize collection results and prepare final response"
      }
    ]
  },
  'cross-market-product-selection': {
    apiVersion: "ami.io/v2",
    name: "coffee-market-analysis-workflow",
    description: "Analyze coffee product opportunities by comparing Poland (Allegro) and US (Amazon) markets to identify profitable sourcing opportunities",
    version: "1.0.0",
    tags: ["market-analysis", "coffee", "allegro", "amazon", "comparison"],
    steps: [
      {
        id: "init-vars",
        intent_name: "Initialize variables",
        agent: "variable",
        intent_description: "Initialize data collection variables for both platforms"
      },
      {
        id: "branch-start",
        type: "branch_start",
        name: "Split to Market Branches",
        description: "Split workflow to collect data from Allegro and Amazon markets",
        branches: ["allegro", "amazon"]
      },
      // Allegro workflow
      {
        id: "extract-allegro-urls",
        intent_name: "[Allegro] Extract Product URLs",
        agent: "scraper_agent",
        branch: "allegro",
        intent_description: "Navigate to Allegro coffee category and extract all product URLs"
      },
      {
        id: "save-allegro-urls",
        intent_name: "[Allegro] Save URLs",
        agent: "variable",
        branch: "allegro",
        intent_description: "Save extracted Allegro URLs to variable"
      },
      {
        id: "collect-allegro-details",
        intent_name: "[Allegro] Collect Details",
        branch: "allegro",
        intent_description: "Iterate through Allegro products and collect detailed information",
        foreach: "{{all_allegro_urls}}",
        as: "current_allegro_product",
        do: [
          {
            id: "scrape-allegro-product",
            intent_name: "Scrape Allegro product information",
            agent: "scraper_agent",
            intent_description: "Extract product details including name, price, and purchase statistics"
          },
          {
            id: "append-allegro-product",
            intent_name: "Add Allegro product to list",
            agent: "variable",
            intent_description: "Append product info to collection"
          },
          {
            id: "store-allegro-product",
            intent_name: "Store Allegro product to database",
            agent: "storage_agent",
            intent_description: "Persist Allegro product information"
          }
        ]
      },
      // Amazon workflow
      {
        id: "extract-amazon-urls",
        intent_name: "[Amazon] Extract Product URLs",
        agent: "scraper_agent",
        branch: "amazon",
        intent_description: "Navigate to Amazon coffee category and extract all product URLs"
      },
      {
        id: "save-amazon-urls",
        intent_name: "[Amazon] Save URLs",
        agent: "variable",
        branch: "amazon",
        intent_description: "Save extracted Amazon URLs to variable"
      },
      {
        id: "collect-amazon-details",
        intent_name: "[Amazon] Collect Details",
        branch: "amazon",
        intent_description: "Iterate through Amazon products and collect detailed information",
        foreach: "{{all_amazon_urls}}",
        as: "current_amazon_product",
        do: [
          {
            id: "scrape-amazon-product",
            intent_name: "Scrape Amazon product information",
            agent: "scraper_agent",
            intent_description: "Extract product details including name and customer ratings"
          },
          {
            id: "append-amazon-product",
            intent_name: "Add Amazon product to list",
            agent: "variable",
            intent_description: "Append product info to collection"
          },
          {
            id: "store-amazon-product",
            intent_name: "Store Amazon product to database",
            agent: "storage_agent",
            intent_description: "Persist Amazon product information"
          }
        ]
      },
      {
        id: "branch-end",
        type: "branch_end",
        name: "Merge Branch Results",
        description: "Combine results from both Allegro and Amazon branches"
      },
      {
        id: "prepare-final-output",
        intent_name: "Prepare Final Output",
        agent: "variable",
        intent_description: "Organize market analysis results"
      }
    ]
  },
  'amazon-coffee-collection': {
    apiVersion: "ami.io/v2",
    name: "amazon-coffee-collection-workflow",
    description: "Collect coffee product information from Amazon including product name, price, and customer ratings",
    version: "1.0.0",
    tags: ["scraper", "amazon", "coffee", "collection"],
    steps: [
      {
        id: "init-vars",
        intent_name: "Initialize variables",
        agent: "variable",
        intent_description: "Initialize data collection variables"
      },
      {
        id: "extract-product-urls",
        intent_name: "Extract product URLs",
        agent: "scraper_agent",
        intent_description: "Navigate to Amazon coffee category and extract all product URLs"
      },
      {
        id: "save-urls",
        intent_name: "Save product URLs",
        agent: "variable",
        intent_description: "Save extracted URLs to variable"
      },
      {
        id: "collect-product-details",
        intent_name: "Collect product details",
        intent_description: "Iterate through all coffee products and extract name, price, and ratings for each",
        foreach: "{{all_product_urls}}",
        as: "current_product",
        do: [
          {
            id: "scrape-product-info",
            intent_name: "Scrape product information",
            agent: "scraper_agent",
            intent_description: "Extract product name, price, and customer ratings"
          },
          {
            id: "append-product",
            intent_name: "Add product to collection",
            agent: "variable",
            intent_description: "Append product info to collection list"
          },
          {
            id: "store-product",
            intent_name: "Store product to database",
            agent: "storage_agent",
            intent_description: "Persist product information to database"
          }
        ]
      },
      {
        id: "prepare-output",
        intent_name: "Prepare final output",
        agent: "variable",
        intent_description: "Organize collection results and prepare final response"
      }
    ]
  },
  'producthunt-weekly-leaderboard': {
    apiVersion: "ami.io/v2",
    name: "producthunt-weekly-leaderboard-scraper",
    description: "从 Product Hunt 每周排行榜（Weekly Leaderboard）中抓取热门产品的详细信息，包括产品名称、描述、评分、评论数、关注者数以及团队成员信息",
    version: "1.0.0",
    tags: ["producthunt", "scraper", "weekly-leaderboard"],
    steps: [
      {
        id: "init-vars",
        intent_name: "Initialize variables",
        agent: "variable",
        intent_description: "Initialize data collection variables"
      },
      {
        id: "extract-weekly-products",
        intent_name: "Extract weekly leaderboard products",
        agent: "scraper_agent",
        intent_description: "Navigate to Product Hunt weekly leaderboard and extract all product URLs"
      },
      {
        id: "save-product-urls",
        intent_name: "Save product URLs",
        agent: "variable",
        intent_description: "Save extracted product URLs to variable"
      },
      {
        id: "collect-product-details",
        intent_name: "Collect product details",
        intent_description: "Iterate through products and collect detailed information including team members",
        foreach: "{{all_product_urls}}",
        as: "current_product",
        do: [
          {
            id: "scrape-product-info",
            intent_name: "Scrape product information",
            agent: "scraper_agent",
            intent_description: "Extract product details from product page"
          },
          {
            id: "scrape-team-members",
            intent_name: "Scrape team members",
            agent: "scraper_agent",
            intent_description: "Extract team member information from team page"
          },
          {
            id: "merge-product-data",
            intent_name: "Merge product data with team info",
            agent: "variable",
            intent_description: "Combine product information with team members"
          },
          {
            id: "append-product",
            intent_name: "Add product to collection",
            agent: "variable",
            intent_description: "Append complete product info to collection"
          },
          {
            id: "store-product",
            intent_name: "Store product to database",
            agent: "storage_agent",
            intent_description: "Persist product information to database"
          }
        ]
      },
      {
        id: "prepare-output",
        intent_name: "Prepare final output",
        agent: "variable",
        intent_description: "Organize collection results"
      }
    ]
  }
}

// Get workflow by key
export function getWorkflow(workflowKey) {
  return WORKFLOWS[workflowKey]
}

// Get all workflow keys
export function getWorkflowKeys() {
  return Object.keys(WORKFLOWS)
}
