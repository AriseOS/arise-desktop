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
  }
}

// Default metaflow key
export const DEFAULT_METAFLOW = 'allegro-coffee-collection'

// Get metaflow by key
export function getMetaflow(metaflowKey) {
  return METAFLOWS[metaflowKey] || METAFLOWS[DEFAULT_METAFLOW]
}

// Get all metaflow keys
export function getMetaflowKeys() {
  return Object.keys(METAFLOWS)
}
