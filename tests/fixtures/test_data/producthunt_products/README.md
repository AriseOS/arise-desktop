# Product Hunt Weekly Leaderboard Scraper Test Data

## Overview

This test scenario demonstrates scraping detailed product information from Product Hunt's weekly leaderboard, including:
- Product name, rating, and review count
- Product description
- Team members information

## Test Scenario

**Target Website**: https://www.producthunt.com/leaderboard/weekly/

**Sample Product**: v0 by Vercel (https://www.producthunt.com/products/v0)

**Data to Extract**:
1. Product name: "v0 by Vercel"
2. Rating: "5.0"
3. Reviews count: "161 reviews"
4. Followers: "1.5K followers"
5. Product description: "Your collaborative AI assistant to design, iterate, and scale full-stack applications for the web."
6. Team members:
   - Richárd Kunkli - Mobile @ Vercel
   - Gary Tokman - Mobile @ Vercel
   - Evil Rabbit - Founding Designer at Vercel
   - Fernando Rojo - Head of Mobile at Vercel

## Operation Flow

The user operations follow this workflow:

1. **Navigate to Product Hunt homepage**
   - URL: https://www.producthunt.com/

2. **Navigate to Weekly Leaderboard**
   - Click "Launches" in navigation
   - Click "Weekly" tab
   - Scroll to view all products

3. **Click on a product** (v0 by Vercel)
   - Open product in new tab
   - Navigate to product detail page

4. **Extract product information**
   - Select product name (H1 element)
   - Extract rating, reviews count, and followers
   - Select product description

5. **Navigate to Team page**
   - Click "Team" tab
   - Scroll to view all team members
   - Extract team members information with roles

## Directory Structure

```
producthunt_products/
├── fixtures/
│   └── user_operations.json    # Recorded user operations
├── expected/
│   └── intents.json            # (Generated) Expected intents
└── output/
    ├── intent_graph.json       # (Generated) Intent Memory Graph
    ├── metaflow.yaml           # (Generated) MetaFlow
    └── workflow.yaml           # (Generated) Final executable workflow
```

## How to Run Test

```bash
# Set environment variable (if testing different scenarios)
export TEST_NAME=producthunt_products

# Run the end-to-end test
pytest tests/integration/intent_builder/test_end_to_end.py -v -s

# Or run directly with Python
TEST_NAME=producthunt_products python tests/integration/intent_builder/test_end_to_end.py
```

## Expected Intents

The Intent Extractor should identify intents like:

1. **Navigate to Product Hunt** - Navigate to the homepage
2. **Navigate to Weekly Leaderboard** - Navigate through Launches menu to weekly view
3. **Scroll Product List** - Scroll to load all products in the leaderboard
4. **Open Product Detail** - Click on a product to view details (opens in new tab)
5. **Extract Product Metadata** - Extract name, rating, reviews count, followers
6. **Extract Product Description** - Select product description text
7. **Navigate to Team Section** - Click Team tab
8. **Scroll Team List** - Scroll to view all team members
9. **Extract Team Information** - Select team members data with roles

## Notes

- This version focuses on scraping from the weekly leaderboard
- The workflow demonstrates:
  - Multi-step navigation (homepage → leaderboard → product detail)
  - New tab handling for product details
  - Scrolling to load content
  - Structured data extraction (rating, reviews, team members)
- To scrape multiple products, you would need to add:
  - Loop back to product list
  - Click next product
  - Repeat extraction steps

## Data Quality Improvements Needed

If you want to enhance this test data:

1. **Add LinkedIn link extraction** - Explicitly select href attributes for team members
2. **Add multiple products** - Record operations for 2-3 products to demonstrate looping
3. **Add data export** - Include operation to save extracted data to CSV/JSON
4. **Add more granular team member extraction** - Extract each member individually rather than selecting the whole section

## Related Test Cases

- `coffee_allegro/` - E-commerce product scraping from Allegro.pl
- `coffee_amazon/` - E-commerce product scraping from Amazon.com
