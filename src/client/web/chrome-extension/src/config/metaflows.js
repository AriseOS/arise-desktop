// Metaflow definitions registry

export const METAFLOWS = {
  'allegro-coffee-collection': {
    version: '1.0',
    task_description: 'Collect coffee product information from Allegro including product name, price, and sales count',
    nodes: [
      {
        id: 'node_1',
        intent_id: 'intent_6c3e972a',
        intent_name: 'NavigateToAllegro',
        intent_description: 'Navigate to Allegro homepage to begin coffee product price collection',
        operations: [
          { type: 'test', timestamp: '2025-09-13 10:32:54', url: 'about:blank' },
          { type: 'navigate', timestamp: '2025-09-13 10:32:57', url: 'https://allegro.pl/' }
        ]
      },
      {
        id: 'node_2',
        intent_id: 'intent_69544a61',
        intent_name: 'NavigateToCoffeeCategory',
        intent_description: 'Navigate to the coffee category page to view coffee products',
        operations: [
          { type: 'click', timestamp: '2025-09-13 10:32:58', url: 'https://allegro.pl/' },
          { type: 'click', timestamp: '2025-09-13 10:33:00', url: 'https://allegro.pl/' },
          { type: 'navigate', timestamp: '2025-09-13 10:33:02', url: 'https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030' }
        ]
      },
      {
        id: 'node_3',
        intent_id: 'implicit_extract_list',
        intent_name: 'ExtractProductList',
        intent_description: 'Extract coffee product list from first page (inferred node)',
        operations: [
          { type: 'extract', element: { xpath: '<PLACEHOLDER>', tagName: 'A' }, target: 'product_urls', value: [] }
        ]
      },
      {
        id: 'node_4',
        type: 'loop',
        description: 'Iterate through all coffee products on first page, extract detailed information',
        source: '{{product_urls}}',
        item_var: 'current_product',
        children: [
          {
            id: 'node_4_1',
            intent_id: 'intent_7fe0c6bf',
            intent_name: 'NavigateToProductDetail',
            intent_description: 'Navigate to a specific coffee product detail page to view its information',
            operations: [
              { type: 'click', timestamp: '2025-09-13 10:33:04' },
              { type: 'navigate', timestamp: '2025-09-13 10:33:05' }
            ]
          },
          {
            id: 'node_4_2',
            intent_id: 'intent_b7f99df2',
            intent_name: 'ExtractProductDetails',
            intent_description: 'Extract coffee product details including name, price, and purchase statistics',
            operations: [
              { type: 'click', timestamp: '2025-09-13 10:33:08' },
              { type: 'select', timestamp: '2025-09-13 10:33:08' },
              { type: 'copy_action', timestamp: '2025-09-13 10:33:08' }
            ]
          }
        ]
      }
    ]
  },
  'cross-market-product-selection': {
    version: '1.0',
    task_description: 'Analyze coffee product opportunities by comparing Poland (Allegro) and US (Amazon) markets to identify profitable sourcing opportunities',
    nodes: [
      {
        id: 'branch_start',
        type: 'branch_start',
        intent_name: 'Split Data Collection',
        intent_description: 'Split workflow to collect data from Allegro and Amazon markets',
        operations: [],
        branches: ['allegro_branch', 'amazon_branch']
      },
      {
        id: 'node_1',
        intent_id: 'allegro_intent_6c3e972a',
        intent_name: '[Allegro] Navigate to Allegro',
        intent_description: '[Allegro Branch] Navigate to Allegro homepage to begin coffee product price collection',
        branch: 'allegro_branch',
        operations: [
          { type: 'test', timestamp: '2025-09-13 10:32:54', url: 'about:blank', data: { message: 'binding verification' } },
          { type: 'navigate', timestamp: '2025-09-13 10:32:57', url: 'https://allegro.pl/' }
        ]
      },
      {
        id: 'node_2',
        intent_id: 'allegro_intent_69544a61',
        intent_name: '[Allegro] Navigate to Coffee Category',
        intent_description: '[Allegro Branch] Navigate to the coffee category page to view coffee products',
        branch: 'allegro_branch',
        operations: [
          { type: 'click', timestamp: '2025-09-13 10:32:58', url: 'https://allegro.pl/' },
          { type: 'click', timestamp: '2025-09-13 10:33:00', url: 'https://allegro.pl/' },
          { type: 'navigate', timestamp: '2025-09-13 10:33:02', url: 'https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030' }
        ]
      },
      {
        id: 'node_3',
        intent_id: 'implicit_extract_allegro_list',
        intent_name: '[Allegro] Extract Product List',
        intent_description: '[Allegro Branch] Extract Allegro coffee product list (inferred node)',
        branch: 'allegro_branch',
        operations: [
          { type: 'extract', element: { xpath: '<PLACEHOLDER>', tagName: 'A' }, target: 'allegro_product_urls', value: [] }
        ],
        outputs: {
          allegro_product_urls: 'allegro_product_urls'
        }
      },
      {
        id: 'node_4',
        type: 'loop',
        branch: 'allegro_branch',
        description: '[Allegro Branch] Iterate through Allegro product list, extract detailed info for each product',
        source: '{{allegro_product_urls}}',
        item_var: 'current_allegro_product',
        children: [
          {
            id: 'node_4_1',
            intent_id: 'allegro_intent_7fe0c6bf',
            intent_name: '[Allegro] Navigate to Product Detail',
            intent_description: '[Allegro Branch] Navigate to a specific coffee product detail page',
            operations: [
              { type: 'click', timestamp: '2025-09-13 10:33:04' },
              { type: 'navigate', timestamp: '2025-09-13 10:33:05' }
            ],
            inputs: {
              product_url: '{{current_allegro_product.url}}'
            }
          },
          {
            id: 'node_4_2',
            intent_id: 'allegro_intent_b7f99df2',
            intent_name: '[Allegro] Extract Product Details',
            intent_description: '[Allegro Branch] Extract coffee product details including name, price, and purchase statistics',
            operations: [
              { type: 'click', timestamp: '2025-09-13 10:33:08' },
              { type: 'select', timestamp: '2025-09-13 10:33:08' },
              { type: 'copy_action', timestamp: '2025-09-13 10:33:08' },
              { type: 'click', timestamp: '2025-09-13 10:33:11' },
              { type: 'select', timestamp: '2025-09-13 10:33:11' },
              { type: 'copy_action', timestamp: '2025-09-13 10:33:11' },
              { type: 'click', timestamp: '2025-09-13 10:33:15' },
              { type: 'select', timestamp: '2025-09-13 10:33:15' },
              { type: 'copy_action', timestamp: '2025-09-13 10:33:15' }
            ],
            outputs: {
              allegro_product_info: 'allegro_product_info'
            }
          }
        ]
      },
      {
        id: 'node_5',
        intent_id: 'amazon_intent_bc50bc29',
        intent_name: '[Amazon] Navigate to Amazon Coffee',
        intent_description: "[Amazon Branch] Navigate to Amazon's coffee products category page with customer rating filter",
        branch: 'amazon_branch',
        operations: [
          { type: 'test', timestamp: '2025-10-15 17:15:07', url: 'about:blank', data: { message: 'binding verification' } },
          { type: 'navigate', timestamp: '2025-10-15 17:15:13', url: 'https://www.amazon.com/s?i=grocery&rh=n%3A23783759011%2Cp_72%3A4-&s=featured-rank' }
        ]
      },
      {
        id: 'node_6',
        intent_id: 'implicit_extract_amazon_list',
        intent_name: '[Amazon] Extract Product List',
        intent_description: '[Amazon Branch] Extract Amazon coffee product list (inferred node)',
        branch: 'amazon_branch',
        operations: [
          { type: 'extract', element: { xpath: '<PLACEHOLDER>', tagName: 'A' }, target: 'amazon_product_urls', value: [] }
        ],
        outputs: {
          amazon_product_urls: 'amazon_product_urls'
        }
      },
      {
        id: 'node_7',
        type: 'loop',
        branch: 'amazon_branch',
        description: '[Amazon Branch] Iterate through Amazon product list, extract detailed info for each product',
        source: '{{amazon_product_urls}}',
        item_var: 'current_amazon_product',
        children: [
          {
            id: 'node_7_1',
            intent_id: 'amazon_intent_f3331686',
            intent_name: '[Amazon] Navigate to Product Detail',
            intent_description: '[Amazon Branch] Navigate to Lavazza coffee product detail page',
            operations: [
              { type: 'click', timestamp: '2025-10-15 09:15:22' },
              { type: 'navigate', timestamp: '2025-10-15 17:15:22' }
            ],
            inputs: {
              product_url: '{{current_amazon_product.url}}'
            }
          },
          {
            id: 'node_7_2',
            intent_id: 'amazon_intent_8dedc8d0',
            intent_name: '[Amazon] Extract Product Info',
            intent_description: '[Amazon Branch] Extract Lavazza coffee product information including product name and customer ratings',
            operations: [
              { type: 'click', timestamp: '2025-10-15 09:15:29' },
              { type: 'select', timestamp: '2025-10-15 09:15:29' },
              { type: 'scroll', timestamp: '2025-10-15 09:15:31' },
              { type: 'click', timestamp: '2025-10-15 09:15:34' },
              { type: 'select', timestamp: '2025-10-15 09:15:40' }
            ],
            outputs: {
              amazon_product_info: 'amazon_product_info'
            }
          }
        ]
      },
      {
        id: 'branch_end',
        type: 'branch_end',
        intent_name: 'Merge Branch Results',
        intent_description: 'Combine results from both Allegro and Amazon branches',
        operations: []
      },
      {
        id: 'node_merge',
        intent_id: 'merge_and_analyze',
        intent_name: '[Merge] Cross-Market Analysis',
        intent_description: 'Merge data from both markets and perform cross-market analysis to identify profitable sourcing opportunities',
        operations: [
          { type: 'process', description: 'Combine Allegro and Amazon product data' },
          { type: 'process', description: 'Compare prices, ratings, and market trends' },
          { type: 'process', description: 'Generate cross-market analysis report with insights and recommendations' }
        ],
        inputs: {
          allegro_data: '{{allegro_product_info}}',
          amazon_data: '{{amazon_product_info}}'
        },
        outputs: {
          analysis_report: 'analysis_report',
          sourcing_recommendations: 'sourcing_recommendations'
        }
      }
    ]
  },
  'amazon-coffee-collection': {
    version: '1.0',
    task_description: 'Collect coffee product information from Amazon including product name, price, and customer ratings',
    nodes: [
      {
        id: 'node_1',
        intent_id: 'intent_bc50bc29',
        intent_name: 'NavigateToAmazonCoffee',
        intent_description: "Navigate to Amazon's coffee products category page with customer rating filter",
        operations: [
          {
            type: 'test',
            timestamp: '2025-10-15 17:15:07',
            url: 'about:blank',
            page_title: 'Starting agent 5367...',
            data: { message: 'binding verification' }
          },
          {
            type: 'navigate',
            timestamp: '2025-10-15 17:15:13',
            url: 'https://www.amazon.com/s?i=grocery&rh=n%3A23783759011%2Cp_72%3A4-&s=featured-rank',
            page_title: 'Navigated Page'
          }
        ]
      },
      {
        id: 'node_2',
        intent_id: 'implicit_extract_list',
        intent_name: 'ExtractProductList',
        intent_description: 'Extract coffee product list (inferred node)',
        operations: [
          {
            type: 'extract',
            element: { xpath: '<PLACEHOLDER>', tagName: 'A' },
            target: 'product_urls',
            value: []
          }
        ],
        outputs: {
          product_urls: 'product_urls'
        }
      },
      {
        id: 'node_3',
        type: 'loop',
        description: 'Iterate through all coffee products, extract name, price and ratings for each',
        source: '{{product_urls}}',
        item_var: 'current_product',
        children: [
          {
            id: 'node_3_1',
            intent_id: 'intent_f3331686',
            intent_name: 'NavigateToProductDetail',
            intent_description: 'Navigate to Lavazza coffee product detail page',
            operations: [
              {
                type: 'click',
                timestamp: '2025-10-15 09:15:22',
                url: 'https://www.amazon.com/s?i=grocery&rh=n%3A23783759011%2Cp_72%3A4-&s=featured-rank',
                page_title: 'Amazon.com',
                element: {
                  xpath: '//*[@id="0b44d025-afdb-40ce-889b-fedbb3136b83"]/div/div/span/div/div/div[3]/div[1]/a/h2',
                  tagName: 'H2',
                  className: 'a-size-base-plus a-spacing-none a-color-base a-text-normal'
                }
              },
              {
                type: 'navigate',
                timestamp: '2025-10-15 17:15:22',
                page_title: 'Navigated Page'
              }
            ],
            inputs: {
              product_url: '{{current_product.url}}'
            }
          },
          {
            id: 'node_3_2',
            intent_id: 'intent_8dedc8d0',
            intent_name: 'ExtractProductInfo',
            intent_description: 'Extract Lavazza coffee product information including product name and customer ratings',
            operations: [
              {
                type: 'click',
                timestamp: '2025-10-15 09:15:29',
                element: {
                  xpath: '//*[@id="productTitle"]',
                  tagName: 'SPAN',
                  className: 'a-size-large product-title-word-break',
                  id: 'productTitle'
                }
              },
              {
                type: 'select',
                timestamp: '2025-10-15 09:15:29',
                element: {
                  xpath: '//*[@id="productTitle"]',
                  tagName: 'SPAN',
                  id: 'productTitle'
                },
                data: {
                  selectedText: 'Lavazza House Blend Perfetto Ground Coffee 12oz Bag, Medium Roast, Full-bodied, Intensity 3/5, 100% Arabica, Ideal for Drip Brewers, (Pack of 1) - Package May Vary',
                  textLength: 163
                }
              },
              {
                type: 'scroll',
                timestamp: '2025-10-15 09:15:31',
                data: {
                  direction: 'down',
                  distance: 68
                }
              },
              {
                type: 'click',
                timestamp: '2025-10-15 09:15:34',
                element: {
                  xpath: '//*[@id="flavor_name_5"]/span/input',
                  tagName: 'INPUT',
                  className: 'a-button-input',
                  type: 'submit'
                }
              },
              {
                type: 'select',
                timestamp: '2025-10-15 09:15:40',
                element: {
                  xpath: '//*[@id="acrCustomerReviewText"]',
                  tagName: 'SPAN',
                  className: 'a-size-base',
                  id: 'acrCustomerReviewText',
                  textContent: '8,168 ratings'
                },
                data: {
                  selectedText: '8,168 ratings',
                  textLength: 13
                }
              }
            ],
            outputs: {
              product_name: 'product_name',
              product_price: 'product_price',
              product_ratings: 'product_ratings'
            }
          }
        ]
      }
    ]
  }
}

// Get metaflow by key
export function getMetaflow(metaflowKey) {
  return METAFLOWS[metaflowKey]
}

// Get all metaflow keys
export function getMetaflowKeys() {
  return Object.keys(METAFLOWS)
}
