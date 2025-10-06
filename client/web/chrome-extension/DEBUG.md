# Debugging Guide

## How to Debug the Extension

### 1. Check Browser Console

1. Click the extension icon to open popup
2. Right-click anywhere in the popup
3. Select "Inspect" or "检查"
4. Go to Console tab

### 2. Common Debug Messages

When clicking a workflow, you should see:
```
Loading workflow detail: <workflow-id>
Workflow data received: { ... }
Steps: [...]
Connections: [...]
transformWorkflowData called with: { ... }
Generated nodes: [...]
Generated edges: [...]
```

### 3. Check for Errors

Look for any red error messages in console:

**Common Issues:**

1. **Network Error**
   - Message: `Load workflow error: ...`
   - Fix: Ensure backend is running on http://localhost:8000

2. **No workflow data**
   - Message: `No workflow data or steps found`
   - Fix: Check backend API response structure

3. **ReactFlow Not Rendering**
   - Check if `workflow-canvas` div has height
   - Open Elements tab and inspect `.workflow-canvas`
   - Should have computed height > 0

### 4. Verify API Response

Open Network tab in DevTools:
1. Click on workflow
2. Find request to `/api/agents/{id}/workflow`
3. Check Response tab - should show:
```json
{
  "agent_id": "sample-workflow",
  "steps": [...],
  "connections": [...],
  "metadata": {...}
}
```

### 5. ReactFlow Container Check

In Console, run:
```javascript
document.querySelector('.workflow-canvas').offsetHeight
```

Should return a number > 0. If returns 0, there's a CSS issue.

### 6. Manual Test Sample Workflow

In Console, run:
```javascript
// Should navigate to workflow detail
// Replace with actual workflow ID
```

### 7. Reload Extension

After making changes:
1. Run `npm run build`
2. Go to `chrome://extensions/`
3. Click reload icon on AgentCrafter extension
4. Close and reopen the popup

## Troubleshooting Steps

### Issue: Blank Page After Clicking Workflow

1. **Check Console**: Any errors?
2. **Check Network**: API call successful?
3. **Check Elements**: Does `.workflow-canvas` have height?
4. **Check Data**: Does workflowData have `steps` array?

### Issue: API Returns 404

- Backend might not be running
- Wrong workflow ID
- User not authenticated (token expired)

### Issue: ReactFlow Shows But Empty

- Check `nodes` array has items
- Check `edges` array has connections
- Verify node positions are valid
- Check if nodes are rendered (inspect Elements)

### Issue: Nodes Not Clickable

- Check `CustomNode` component is loaded
- Verify `nodeTypes` is passed to ReactFlow
- Check console for React errors

## Quick Fix Checklist

- [ ] Backend running on port 8000
- [ ] Extension built with `npm run build`
- [ ] Extension reloaded in Chrome
- [ ] Logged in with valid credentials
- [ ] API returns workflow data
- [ ] Console shows debug messages
- [ ] No red errors in console
- [ ] `.workflow-canvas` has height > 0

## Still Not Working?

1. Delete `dist` folder
2. Run `npm run build` again
3. Reload extension completely
4. Try sample workflow first (always available with `default=true`)
5. Check if issue is with specific workflow or all workflows
