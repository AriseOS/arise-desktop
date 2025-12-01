# Ami Chrome Extension - Build Guide

## Overview

This Chrome extension uses React and ReactFlow for workflow visualization. It requires building before use.

## Prerequisites

- Node.js (v16 or higher)
- npm or yarn

## Installation

```bash
# Install dependencies
npm install
```

## Development

```bash
# Build for development (with watch mode)
npm run watch

# Or one-time build
npm run build
```

## Load Extension in Chrome

1. Build the extension first using `npm run build`
2. Open Chrome and go to `chrome://extensions/`
3. Enable "Developer mode" in the top right
4. Click "Load unpacked"
5. Select the `dist` folder from this directory

## Project Structure

```
chrome-extension/
├── src/
│   ├── popup.jsx           # Entry point
│   ├── App.jsx             # Main app component
│   ├── popup.css           # Styles
│   ├── components/
│   │   └── CustomNode.jsx  # ReactFlow custom node
│   └── pages/
│       ├── LoginPage.jsx
│       ├── MainPage.jsx
│       ├── MyWorkflowsPage.jsx
│       ├── WorkflowDetailPage.jsx
│       └── AboutPage.jsx
├── public/
│   ├── manifest.json       # Extension manifest
│   ├── background.js       # Service worker
│   ├── content.js          # Content script
│   └── icons/              # Extension icons
├── popup-react.html        # HTML entry
├── vite.config.js          # Build configuration
└── package.json

```

## Key Features

- **ReactFlow Integration**: Full-featured workflow visualization
- **Compact Layout**: Optimized for 350x550px extension popup
- **Interactive Nodes**: Click nodes to view details
- **Responsive**: Smooth zoom and pan controls
- **Mini Map**: Overview navigation for large workflows

## Development Tips

- Use `npm run watch` during development for automatic rebuilds
- Reload the extension in Chrome after each build
- Check browser console for debugging
- ReactFlow requires proper container sizing - check CSS if layout breaks

## Troubleshooting

### Extension not loading
- Make sure you ran `npm run build` first
- Check that `dist` folder exists and contains `popup.html`
- Verify manifest.json is in the dist folder

### ReactFlow not rendering
- Check console for errors
- Ensure container has explicit height in CSS
- Verify workflow data has correct structure (steps and connections)

### Build errors
- Delete `node_modules` and `dist` folders
- Run `npm install` again
- Try `npm run build` with clean slate
