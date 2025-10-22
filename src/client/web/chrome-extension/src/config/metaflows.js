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

// Default metaflow key
export const DEFAULT_METAFLOW = 'amazon-coffee-collection'

// Get metaflow by key
export function getMetaflow(metaflowKey) {
  return METAFLOWS[metaflowKey] || METAFLOWS[DEFAULT_METAFLOW]
}

// Get all metaflow keys
export function getMetaflowKeys() {
  return Object.keys(METAFLOWS)
}
