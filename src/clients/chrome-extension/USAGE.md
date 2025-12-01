# Ami Chrome Extension - Usage Guide

## Quick Start

### 1. Build the Extension

```bash
cd /Users/liuyihua/Code/Ami/client/web/chrome-extension
npm install
npm run build
```

### 2. Load in Chrome

1. Open Chrome browser
2. Navigate to `chrome://extensions/`
3. Enable **Developer mode** (toggle in top right)
4. Click **Load unpacked**
5. Select the `dist` folder: `/Users/liuyihua/Code/Ami/client/web/chrome-extension/dist`

### 3. Start Using

1. Click the Ami extension icon in your Chrome toolbar
2. Login with your credentials
3. Navigate to "我的" (My Workflows) to see your workflows
4. Click on any workflow to view its visualization using ReactFlow

## Features

### Workflow Visualization

- **ReactFlow Canvas**: Interactive, zoomable workflow diagram
- **Custom Nodes**: Color-coded by type (start=green, end=red, others=blue)
- **Node Details**: Click any node to see detailed information
- **Mini Map**: Quick navigation for large workflows
- **Controls**: Zoom in/out, fit view, and interactive mode toggle

### Navigation

- **Main Page**: Access recording, chat, my workflows, account, and about
- **My Workflows**: List all your workflows (or see sample workflow if none exist)
- **Workflow Detail**: Full ReactFlow visualization with step-by-step flow
- **About**: Information about Ami platform

### Sample Workflow

If you don't have any workflows yet, the extension will show a sample "Browser Session Test Workflow" with:
- 6 steps demonstrating browser automation
- Sequential connections showing workflow flow
- Example of scraper agents and text processing

## Development Mode

For development with auto-rebuild:

```bash
npm run watch
```

This will watch for file changes and rebuild automatically. You'll need to reload the extension in Chrome after each build.

## Troubleshooting

### Extension Icon Not Showing
- Check that manifest.json is in the dist folder
- Verify icons folder is copied to dist

### Popup Not Opening
- Check browser console for errors (F12)
- Ensure popup-react.html exists in dist
- Verify popup.js is properly built

### ReactFlow Not Rendering
- Workflow data must have `steps` and `connections` arrays
- Check network requests to ensure API returns correct data
- Console should show workflow data when loading detail page

### Backend Connection Failed
- Ensure backend is running on http://localhost:8000
- Check that user is logged in with valid token
- Verify CORS is enabled on backend

## API Endpoints Used

- `POST /api/login` - User authentication
- `GET /api/agents?default=true` - List workflows (with sample if empty)
- `GET /api/agents/{agent_id}/workflow` - Get workflow details

## File Structure After Build

```
dist/
├── manifest.json          # Extension configuration
├── popup-react.html       # Extension popup HTML
├── popup.js              # Bundled React app (305KB)
├── background.js         # Service worker
├── content.js            # Content script
├── icons/                # Extension icons
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── assets/
    └── popup.css         # Bundled styles
```

## Next Steps

1. **Create Workflows**: Use the recording or chat features (coming soon)
2. **Execute Workflows**: Run automation tasks (coming soon)
3. **Manage Workflows**: Edit, delete, or duplicate workflows (coming soon)

## Support

For issues or questions, please refer to the main Ami documentation.
