# Status Message System

## Overview

The extension now uses a beautiful floating status message system instead of native browser alerts for non-critical notifications.

## Features

- ✅ **Floating Design**: Messages appear at the top of the popup with smooth animation
- ✅ **Auto-dismiss**: Messages automatically disappear after 3 seconds
- ✅ **Type-based Styling**: Different colors for info, success, and error messages
- ✅ **Non-blocking**: Users can still interact with the UI while messages are shown
- ✅ **Smooth Animation**: Messages slide down from the top

## Usage

### In Page Components

All page components that need to show status messages should receive the `showStatus` prop:

```jsx
function MyPage({ showStatus }) {
  const handleAction = () => {
    showStatus('📹 录制功能开发中...', 'info')
  }

  return (
    <button onClick={handleAction}>Record</button>
  )
}
```

### Message Types

```jsx
// Info message (blue)
showStatus('💬 对话功能开发中...', 'info')

// Success message (green)
showStatus('✅ 操作成功', 'success')

// Error message (red)
showStatus('❌ 操作失败', 'error')
```

### When to Use Alert vs Status Message

**Use Status Message (`showStatus`) for:**
- Feature not implemented notifications
- Non-critical information
- Success confirmations
- Warnings that don't require immediate action

**Use Alert (`alert()`) for:**
- Critical errors that require immediate attention
- Session expiration (forces logout)
- Confirmation dialogs
- Situations that block user flow

## Examples

### Current Usage in MainPage

```jsx
const menuItems = [
  {
    section: 'Workflow',
    items: [
      {
        id: 'record',
        title: '录制',
        onClick: () => showStatus('📹 录制功能开发中...', 'info')
      },
      {
        id: 'chat',
        title: '对话',
        onClick: () => showStatus('💬 对话功能开发中...', 'info')
      },
    ]
  }
]
```

### Adding Status Messages to New Pages

1. Add `showStatus` to component props:
```jsx
function NewPage({ showStatus, onNavigate }) {
  // ...
}
```

2. Pass `showStatus` from App.jsx:
```jsx
{currentPage === 'new-page' && (
  <NewPage
    showStatus={showStatus}
    onNavigate={navigateTo}
  />
)}
```

3. Use in your component:
```jsx
const handleClick = () => {
  showStatus('功能开发中...', 'info')
}
```

## CSS Classes

### Status Message Container
```css
.status-message-container {
  position: fixed;
  top: 16px;
  left: 16px;
  right: 16px;
  z-index: 9999;
  pointer-events: none;
}
```

### Status Message Types
```css
.status-info {
  background: #bee3f8;
  color: #2c5282;
}

.status-success {
  background: #c6f6d5;
  color: #22543d;
}

.status-error {
  background: #fed7d7;
  color: #742a2a;
}
```

## Component Structure

```
StatusMessage.jsx
├── Receives: message, type, onClose
├── Auto-dismisses after 3 seconds
└── Renders floating notification

App.jsx
├── Manages global status state
├── Provides showStatus to all pages
└── Renders StatusMessage component
```

## Testing

1. Click "录制" button - should show blue message "📹 录制功能开发中..."
2. Click "对话" button - should show blue message "💬 对话功能开发中..."
3. Click "账户" button - should show blue message "👤 账户设置功能开发中..."
4. Messages should disappear after 3 seconds
5. Messages should have smooth slide-down animation

## Migration from Alert

Before:
```jsx
onClick: () => alert('功能开发中...')
```

After:
```jsx
onClick: () => showStatus('📹 功能开发中...', 'info')
```

Benefits:
- Better UX (non-blocking)
- Consistent with extension design
- Auto-dismiss (no manual close needed)
- Color-coded by importance
