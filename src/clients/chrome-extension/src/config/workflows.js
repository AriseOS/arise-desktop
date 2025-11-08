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
  },
  'cross-market-product-selection': {
    apiVersion: "agentcrafter.io/v1",
    kind: "Workflow",
    metadata: {
      name: "coffee-market-analysis-workflow",
      description: "Analyze coffee product opportunities by comparing Poland (Allegro) and US (Amazon) markets to identify profitable sourcing opportunities",
      version: "1.0.0",
      tags: ["market-analysis", "coffee", "allegro", "amazon", "comparison"]
    },
    inputs: {
      max_products: {
        type: "integer",
        description: "Maximum products to collect from each platform",
        required: false,
        default: 20
      }
    },
    outputs: {
      allegro_products: {
        type: "array",
        description: "Collected Allegro coffee product information"
      },
      amazon_products: {
        type: "array",
        description: "Collected Amazon coffee product information"
      },
      final_response: {
        type: "string",
        description: "Analysis completion summary"
      }
    },
    config: {
      max_execution_time: 3600,
      enable_parallel: false,
      enable_cache: true
    },
    steps: [
      {
        id: "init-vars",
        name: "Initialize variables",
        agent_type: "variable",
        description: "Initialize data collection variables for both platforms",
        agent_instruction: "Initialize product collection variables",
        inputs: {
          operation: "set",
          data: {
            all_allegro_urls: [],
            all_allegro_products: [],
            all_amazon_urls: [],
            all_amazon_products: []
          }
        },
        outputs: {
          all_allegro_urls: "all_allegro_urls",
          all_allegro_products: "all_allegro_products",
          all_amazon_urls: "all_amazon_urls",
          all_amazon_products: "all_amazon_products"
        },
        timeout: 10
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
        name: "[Allegro] Extract Product URLs",
        agent_type: "scraper_agent",
        branch: "allegro",
        description: "Navigate to Allegro coffee category and extract all product URLs",
        agent_instruction: "Visit Allegro coffee category page and extract all product URLs",
        inputs: {
          target_path: "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030",
          extraction_method: "script",
          dom_scope: "full",
          max_items: 10,
          data_requirements: {
            user_description: "Extract all coffee product URLs from the listing page",
            output_format: {
              url: "Product URL"
            },
            sample_data: [
              { url: "https://allegro.pl/oferta/kawa-ziarnista-1kg-brazylia-santos-swiezo-palona-100-arabica-tommy-cafe-12786896326" },
              { url: "https://allegro.pl/oferta/kawa-example-product-123456" }
            ]
          }
        },
        outputs: {
          extracted_data: "allegro_product_urls"
        },
        timeout: 60
      },
      {
        id: "save-allegro-urls",
        name: "[Allegro] Save URLs",
        agent_type: "variable",
        branch: "allegro",
        description: "Save extracted Allegro URLs to variable",
        agent_instruction: "Save Allegro product URLs",
        inputs: {
          operation: "set",
          data: {
            all_allegro_urls: "{{allegro_product_urls}}"
          }
        },
        outputs: {
          all_allegro_urls: "all_allegro_urls"
        },
        timeout: 10
      },
      {
        id: "collect-allegro-details",
        name: "[Allegro] Collect Details",
        agent_type: "foreach",
        branch: "allegro",
        description: "Iterate through Allegro products and collect detailed information",
        source: "{{all_allegro_urls}}",
        item_var: "current_allegro_product",
        index_var: "allegro_index",
        max_iterations: 20,
        loop_timeout: 1200,
        steps: [
          {
            id: "scrape-allegro-product",
            name: "Scrape Allegro product information",
            agent_type: "scraper_agent",
            description: "Extract product details including name, price, and purchase statistics",
            agent_instruction: "Visit Allegro product page and extract title, price, and purchase count",
            inputs: {
              target_path: "{{current_allegro_product.url}}",
              extraction_method: "llm",
              dom_scope: "partial",
              data_requirements: {
                user_description: "Extract coffee product details including name, price, and purchase statistics",
                output_format: {
                  title: "Product title",
                  price: "Product price",
                  purchases: "Number of recent purchases"
                },
                sample_data: {
                  title: "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe",
                  price: "69,50 zł",
                  purchases: "3 308 osób kupiło ostatnio"
                }
              }
            },
            outputs: {
              extracted_data: "allegro_product_info"
            },
            timeout: 60
          },
          {
            id: "append-allegro-product",
            name: "Add Allegro product to list",
            agent_type: "variable",
            description: "Append product info to collection",
            agent_instruction: "Add Allegro product to list",
            inputs: {
              operation: "append",
              source: "{{all_allegro_products}}",
              data: "{{allegro_product_info}}"
            },
            outputs: {
              result: "all_allegro_products"
            },
            timeout: 10
          },
          {
            id: "store-allegro-product",
            name: "Store Allegro product to database",
            agent_type: "storage_agent",
            description: "Persist Allegro product information",
            agent_instruction: "Store Allegro product to database",
            inputs: {
              operation: "store",
              collection: "allegro_products",
              data: "{{allegro_product_info}}"
            },
            outputs: {
              message: "allegro_store_message"
            },
            timeout: 15
          }
        ]
      },
      // Amazon workflow
      {
        id: "extract-amazon-urls",
        name: "[Amazon] Extract Product URLs",
        agent_type: "scraper_agent",
        branch: "amazon",
        description: "Navigate to Amazon coffee category and extract all product URLs",
        agent_instruction: "Visit Amazon coffee category page with customer rating filter and extract all product URLs",
        inputs: {
          target_path: "https://www.amazon.com/s?i=grocery&rh=n%3A23783759011%2Cp_72%3A4-&s=featured-rank",
          extraction_method: "script",
          dom_scope: "full",
          max_items: 10,
          data_requirements: {
            user_description: "Extract all coffee product URLs from the listing page",
            output_format: {
              url: "Product URL"
            },
            sample_data: [
              { url: "https://www.amazon.com/Lavazza-Dolcevita-Classico-Full-bodied-Intensity/dp/B00PQKRVFG" },
              { url: "https://www.amazon.com/coffee-product-example/dp/B00EXAMPLE" }
            ]
          }
        },
        outputs: {
          extracted_data: "amazon_product_urls"
        },
        timeout: 60
      },
      {
        id: "save-amazon-urls",
        name: "[Amazon] Save URLs",
        agent_type: "variable",
        branch: "amazon",
        description: "Save extracted Amazon URLs to variable",
        agent_instruction: "Save Amazon product URLs",
        inputs: {
          operation: "set",
          data: {
            all_amazon_urls: "{{amazon_product_urls}}"
          }
        },
        outputs: {
          all_amazon_urls: "all_amazon_urls"
        },
        timeout: 10
      },
      {
        id: "collect-amazon-details",
        name: "[Amazon] Collect Details",
        agent_type: "foreach",
        branch: "amazon",
        description: "Iterate through Amazon products and collect detailed information",
        source: "{{all_amazon_urls}}",
        item_var: "current_amazon_product",
        index_var: "amazon_index",
        max_iterations: 20,
        loop_timeout: 1200,
        steps: [
          {
            id: "scrape-amazon-product",
            name: "Scrape Amazon product information",
            agent_type: "scraper_agent",
            description: "Extract product details including name and customer ratings",
            agent_instruction: "Visit Amazon product page and extract product name and customer ratings",
            inputs: {
              target_path: "{{current_amazon_product.url}}",
              extraction_method: "llm",
              dom_scope: "partial",
              data_requirements: {
                user_description: "Extract coffee product information including product name and customer ratings",
                output_format: {
                  title: "Product title",
                  ratings: "Customer ratings count"
                },
                sample_data: {
                  title: "Lavazza House Blend Perfetto Ground Coffee 12oz Bag, Medium Roast, Full-bodied, Intensity 3/5, 100% Arabica, Ideal for Drip Brewers, (Pack of 1) - Package May Vary",
                  ratings: "8,168 ratings"
                }
              }
            },
            outputs: {
              extracted_data: "amazon_product_info"
            },
            timeout: 60
          },
          {
            id: "append-amazon-product",
            name: "Add Amazon product to list",
            agent_type: "variable",
            description: "Append product info to collection",
            agent_instruction: "Add Amazon product to list",
            inputs: {
              operation: "append",
              source: "{{all_amazon_products}}",
              data: "{{amazon_product_info}}"
            },
            outputs: {
              result: "all_amazon_products"
            },
            timeout: 10
          },
          {
            id: "store-amazon-product",
            name: "Store Amazon product to database",
            agent_type: "storage_agent",
            description: "Persist Amazon product information",
            agent_instruction: "Store Amazon product to database",
            inputs: {
              operation: "store",
              collection: "amazon_products",
              data: "{{amazon_product_info}}"
            },
            outputs: {
              message: "amazon_store_message"
            },
            timeout: 15
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
        name: "Prepare Final Output",
        agent_type: "variable",
        description: "Organize market analysis results",
        agent_instruction: "Prepare final output with collected data from both platforms",
        inputs: {
          operation: "set",
          data: {
            allegro_products: "{{all_allegro_products}}",
            amazon_products: "{{all_amazon_products}}",
            final_response: "Successfully collected {{allegro_index}} Allegro products and {{amazon_index}} Amazon products for market analysis"
          }
        },
        outputs: {
          allegro_products: "allegro_products",
          amazon_products: "amazon_products",
          final_response: "final_response"
        },
        timeout: 10
      }
    ]
  },
  'amazon-coffee-collection': {
    apiVersion: "agentcrafter.io/v1",
    kind: "Workflow",
    metadata: {
      name: "amazon-coffee-collection-workflow",
      description: "Collect coffee product information from Amazon including product name, price, and customer ratings",
      version: "1.0.0",
      tags: ["scraper", "amazon", "coffee", "collection"]
    },
    inputs: {
      max_products: {
        type: "integer",
        description: "Maximum number of products to collect",
        required: false,
        default: 20
      }
    },
    outputs: {
      all_product_details: {
        type: "array",
        description: "Collected product information including name, price, and ratings"
      },
      final_response: {
        type: "string",
        description: "Workflow completion message"
      }
    },
    config: {
      max_execution_time: 1800,
      enable_parallel: false,
      enable_cache: true
    },
    steps: [
      {
        id: "init-vars",
        name: "Initialize variables",
        agent_type: "variable",
        description: "Initialize data collection variables",
        agent_instruction: "Initialize product collection variables",
        inputs: {
          operation: "set",
          data: {
            all_product_urls: [],
            all_product_details: []
          }
        },
        outputs: {
          all_product_urls: "all_product_urls",
          all_product_details: "all_product_details"
        },
        timeout: 10
      },
      {
        id: "extract-product-urls",
        name: "Extract product URLs",
        agent_type: "scraper_agent",
        description: "Navigate to Amazon coffee category and extract all product URLs",
        agent_instruction: "Visit Amazon coffee products page with customer rating filter and extract all product URLs",
        inputs: {
          target_path: "https://www.amazon.com/s?i=grocery&rh=n%3A23783759011%2Cp_72%3A4-&s=featured-rank",
          extraction_method: "script",
          dom_scope: "full",
          max_items: 10,
          data_requirements: {
            user_description: "Extract all coffee product URLs from the listing page",
            output_format: {
              url: "Product detail page URL"
            },
            sample_data: [
              { url: "https://www.amazon.com/Lavazza-Coffee-Medium-Espresso-2-2-Pound/dp/B005OJ4X32/ref=sr_1_2?..." },
              { url: "https://www.amazon.com/Lavazza-Coffee-Medium-Espresso-2-2-Pound/dp/B000SDKDM4/ref=sr_1_1?..." }
            ]
          }
        },
        outputs: {
          extracted_data: "product_urls"
        },
        timeout: 60
      },
      {
        id: "save-urls",
        name: "Save product URLs",
        agent_type: "variable",
        description: "Save extracted URLs to variable",
        agent_instruction: "Save product URLs to collection variable",
        inputs: {
          operation: "set",
          data: {
            all_product_urls: "{{product_urls}}"
          }
        },
        outputs: {
          all_product_urls: "all_product_urls"
        },
        timeout: 10
      },
      {
        id: "collect-product-details",
        name: "Collect product details",
        agent_type: "foreach",
        description: "Iterate through all coffee products and extract name, price, and ratings for each",
        source: "{{all_product_urls}}",
        item_var: "current_product",
        index_var: "product_index",
        max_iterations: 20,
        loop_timeout: 1200,
        steps: [
          {
            id: "scrape-product-info",
            name: "Scrape product information",
            agent_type: "scraper_agent",
            description: "Extract product name, price, and customer ratings",
            agent_instruction: "Visit product detail page and extract product name, price, and customer ratings",
            inputs: {
              target_path: "{{current_product.url}}",
              extraction_method: "llm",
              dom_scope: "partial",
              data_requirements: {
                user_description: "Extract product name, price, and customer ratings from Amazon product page",
                output_format: {
                  product_name: "Product name",
                  product_price: "Product price",
                  product_ratings: "Customer ratings count"
                },
                sample_data: {
                  product_name: "Lavazza House Blend Perfetto Ground Coffee 12oz Bag, Medium Roast, Full-bodied, Intensity 3/5, 100% Arabica, Ideal for Drip Brewers, (Pack of 1) - Package May Vary",
                  product_price: "$12.99",
                  product_ratings: "8,168 ratings"
                }
              }
            },
            outputs: {
              extracted_data: "product_info"
            },
            timeout: 60
          },
          {
            id: "append-product",
            name: "Add product to collection",
            agent_type: "variable",
            description: "Append product info to collection list",
            agent_instruction: "Add product information to collection",
            inputs: {
              operation: "append",
              source: "{{all_product_details}}",
              data: "{{product_info}}"
            },
            outputs: {
              result: "all_product_details"
            },
            timeout: 10
          },
          {
            id: "store-product",
            name: "Store product to database",
            agent_type: "storage_agent",
            description: "Persist product information to database",
            agent_instruction: "Store product information to database",
            inputs: {
              operation: "store",
              collection: "amazon_coffee_products",
              data: "{{product_info}}"
            },
            outputs: {
              message: "store_message",
              rows_stored: "rows_stored"
            },
            timeout: 15
          }
        ]
      },
      {
        id: "prepare-output",
        name: "Prepare final output",
        agent_type: "variable",
        description: "Organize collection results and prepare final response",
        agent_instruction: "Prepare final output with collected product details",
        inputs: {
          operation: "set",
          data: {
            final_response: "Successfully collected {{product_index}} coffee products from Amazon with name, price, and ratings information"
          }
        },
        outputs: {
          final_response: "final_response"
        },
        timeout: 10
      }
    ]
  },
  'producthunt-weekly-leaderboard': {
    apiVersion: "agentcrafter.io/v1",
    kind: "Workflow",
    metadata: {
      name: "producthunt-weekly-leaderboard-scraper",
      description: "从 Product Hunt 每周排行榜（Weekly Leaderboard）中抓取热门产品的详细信息，包括产品名称、描述、评分、评论数、关注者数以及团队成员信息",
      version: "1.0.0",
      tags: ["producthunt", "scraper", "weekly-leaderboard"]
    },
    inputs: {
      max_products: {
        type: "integer",
        description: "Maximum number of products to scrape",
        required: false,
        default: 20
      }
    },
    outputs: {
      product_details: {
        type: "array",
        description: "Collected product information with team members"
      },
      final_response: {
        type: "string",
        description: "Completion message"
      }
    },
    config: {
      max_execution_time: 3600,
      enable_parallel: false,
      enable_cache: true
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
        id: "extract-weekly-products",
        name: "Extract weekly leaderboard products",
        agent_type: "scraper_agent",
        description: "Navigate to Product Hunt weekly leaderboard and extract all product URLs",
        agent_instruction: "Visit Product Hunt weekly leaderboard page and extract all product URLs from the list"
      },
      {
        id: "save-product-urls",
        name: "Save product URLs",
        agent_type: "variable",
        description: "Save extracted product URLs to variable",
        agent_instruction: "Save product URLs to collection variable"
      },
      {
        id: "collect-product-details",
        name: "Collect product details",
        agent_type: "foreach",
        description: "Iterate through products and collect detailed information including team members",
        source: "{{all_product_urls}}",
        item_var: "current_product",
        steps: [
          {
            id: "scrape-product-info",
            name: "Scrape product information",
            agent_type: "scraper_agent",
            description: "Extract product details from product page",
            agent_instruction: "Visit Product Hunt product page and extract product name, tagline, description, rating, reviews, and followers"
          },
          {
            id: "scrape-team-members",
            name: "Scrape team members",
            agent_type: "scraper_agent",
            description: "Extract team member information from team page",
            agent_instruction: "Navigate to Product Hunt product team page and extract all team member names and positions"
          },
          {
            id: "merge-product-data",
            name: "Merge product data with team info",
            agent_type: "variable",
            description: "Combine product information with team members",
            agent_instruction: "Merge product details with team member information"
          },
          {
            id: "append-product",
            name: "Add product to collection",
            agent_type: "variable",
            description: "Append complete product info to collection",
            agent_instruction: "Add product with team info to collection list"
          },
          {
            id: "store-product",
            name: "Store product to database",
            agent_type: "storage_agent",
            description: "Persist product information to database",
            agent_instruction: "Store complete product information including team members to database"
          }
        ]
      },
      {
        id: "prepare-output",
        name: "Prepare final output",
        agent_type: "variable",
        description: "Organize collection results",
        agent_instruction: "Prepare final output with collected product details"
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
