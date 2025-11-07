# Kickstarter Projects Test Data

## Overview
This test dataset captures a complete workflow for collecting information about the latest technology projects on Kickstarter.

## Task Description
**Goal**: Collect information about the latest technology projects on Kickstarter, including:
- Project title
- Funding amount (pledged vs goal)
- Number of backers
- Project timeline (days remaining)
- Creator information (name, description, social links, location)

## Workflow Steps

### 1. Navigation to Discovery Page
- Navigate to Kickstarter homepage
- Enter discovery/advanced search mode
- Remove default search term

### 2. Apply Filters
- **Category**: Technology (category_id=16)
- **Sort**: Newest projects
- **Filter**: Projects We Love (staff picks)

### 3. Load More Projects
- Scroll down to view initial projects
- Click "Load more" button → Navigate to page 2
- Scroll down → Auto-load page 3

### 4. Select and View Project Details
- Click on a project (Xlaserlab E3 UV Laser Engraver)
- Open project in new tab

### 5. Extract Project Information
- Extract title: "Xlaserlab E3: The One for All Ultrafast UV Laser Engraver"
- Extract funding: "S$ 896,458 pledged of S$ 129,836 goal"
- Extract backers: "125 backers"
- Extract timeline: "56 days to go"

### 6. Extract Creator Information
- Navigate to Creator tab
- Extract creator name: "XLaserlab / LINA WANG"
- Extract creator description: "XPhotonics is bringing advanced laser technology..."
- Extract social links:
  - Instagram: /xinghanlaser1, /xphotonics
  - YouTube: youtube.com/@xphotonics_laser
  - Website: xlaserlab.com/pages/kickstarter
- Extract location: "Chicago, IL"

## Key URLs
- **Homepage**: https://www.kickstarter.com/
- **Final Discovery URL**: https://www.kickstarter.com/discover/advanced?category_id=16&woe_id=0&staff_picks=1&sort=newest&seed=2936830&page=3
- **Sample Project**: https://www.kickstarter.com/projects/xlaserlab/xlaserlab-uv-engraver
- **Creator Page**: https://www.kickstarter.com/projects/xlaserlab/xlaserlab-uv-engraver/creator

## Test Scenarios

### Scenario 1: Basic Navigation
Test that the workflow can navigate through filters and load multiple pages successfully.

### Scenario 2: Data Extraction
Test that the workflow can extract all required fields from project and creator pages.

### Scenario 3: Intent Classification
Test that IntentExtractor correctly identifies:
- Navigation intents (with click operations for filters)
- Scroll intents (for loading more content)
- Extraction intents (for project and creator data)

## Expected Workflow Structure

### Browser Agent Steps
- Navigate to homepage
- Navigate to discovery page (with filter parameters in URL)
- Navigate to project detail page
- Navigate to creator tab

### Scraper Agent Steps
- Extract project list (optional - for collecting multiple projects)
- Extract project details (title, funding, backers, timeline)
- Extract creator information (name, description, social links, location)

## Notes
- The workflow includes multiple navigation steps through URL changes (filters trigger navigation)
- Scroll operations are for loading more content (lazy loading, page 2-3)
- Select operations indicate data extraction (user selecting text to copy)
- The workflow demonstrates complex multi-page data collection with filters
