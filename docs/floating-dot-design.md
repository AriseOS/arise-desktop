# 浮动小圆点设计文档

> Ami 桌面应用的核心交互入口——浮动小圆点的技术设计方案（Electron 架构）。

---

## 1. 产品需求

### 1.1 设计目标

| 特性 | 描述 |
|-----|------|
| **形态** | 浮动小圆点，常驻桌面 |
| **交互** | 点击呼出对话输入框；输入=对话，不输入=录制 |
| **感觉** | 像系统的一部分，不是一个 App |
| **扩展** | 需要时展开成完整 Dashboard |

### 1.2 用户心智

- **日常**：小圆点常驻，随时呼唤 → 贾维斯感
- **深入**：打开 Dashboard 管理和浏览 → 实用性

### 1.3 交互流程

```
点击小圆点
    ↓
弹出输入框
    ├─ 用户输入文字 → 发起对话/任务
    └─ 用户不输入，按 Enter → 开始录屏
```

---

## 2. 技术方案

### 2.1 架构概览

基于 Electron 多窗口架构，实现三层窗口结构：

```
┌─────────────────────────────────────────────────────────────┐
│                          桌面                               │
│                                                             │
│                                         ┌───┐               │
│                                         │ ● │ ← 浮动小圆点   │
│                                         └───┘               │
│                                            │                │
│                                            ↓ 点击            │
│                                   ┌─────────────────┐       │
│                                   │ 快捷输入面板     │       │
│                                   │ [输入任务...]   │       │
│                                   │ 或点击开始录制   │       │
│                                   └─────────────────┘       │
│                                            │                │
│                                            ↓ 展开 Dashboard  │
│                           ┌───────────────────────────────┐ │
│                           │         Dashboard              │ │
│                           │  ┌────┐ ┌────────┐ ┌────────┐ │ │
│                           │  │对话│ │Memory │ │Public │ │ │
│                           │  └────┘ └────────┘ └────────┘ │ │
│                           └───────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

系统托盘：作为备用入口和状态指示器
```

### 2.2 窗口定义

| 窗口 | 变量名 | 尺寸 | 特性 | 用途 |
|-----|--------|------|------|------|
| **小圆点** | `dotWindow` | 56×56 | alwaysOnTop, 无边框, 透明, 可拖拽, skipTaskbar | 常驻入口 |
| **快捷面板** | `panelWindow` | 320×180 | alwaysOnTop, 无边框, 锚定在 dot 旁, 失焦隐藏 | 快捷交互 |
| **Dashboard** | `mainWindow` | 1400×900 | 标准窗口, 默认隐藏（即现有主窗口） | 完整功能 |

### 2.3 与现有架构的关系

当前 ami-desktop 是单个 `mainWindow`（BrowserWindow）。浮动小圆点在此基础上新增两个窗口：

```
现有：
  mainWindow (BrowserWindow) → React App + WebContentsView Pool

新增：
  dotWindow (BrowserWindow, frameless) → dot.html (极简 React)
  panelWindow (BrowserWindow, frameless) → panel.html (快捷输入)
```

WebContentsView Pool、TypeScript Daemon、IPC 体系保持不变。新窗口仅负责 UI 入口，不参与浏览器自动化。

### 2.4 窗口间通信

```
┌─────────────┐      IPC (Main Process)     ┌─────────────┐
│  dotWindow  │ ←─────────────────────────→ │ mainWindow  │
└─────────────┘                             └─────────────┘
       │                                           │
       │      ┌─────────────┐                      │
       └────→ │ panelWindow │ ←───────────────────┘
              └─────────────┘

通信机制：
- Electron IPC (ipcMain/ipcRenderer) — 窗口控制
- electron-store — 共享持久化状态（已有）
- BrowserWindow 方法 — show/hide/setPosition/setBounds
```

---

## 3. 实现细节

### 3.1 主进程窗口创建

**文件**: `electron/main.cjs` — 在现有 `app.whenReady()` 中新增

```javascript
// ==================== Dot Window (浮动小圆点) ====================

function createDotWindow() {
  const dotWindow = new BrowserWindow({
    width: 56,
    height: 56,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    hasShadow: false,
    focusable: false,          // 不抢焦点
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 恢复上次位置
  const savedPos = store.get('dotPosition');
  if (savedPos) {
    dotWindow.setPosition(savedPos.x, savedPos.y);
  }

  // 开发模式加载 Vite dev server，生产模式加载打包文件
  if (process.env.VITE_DEV_SERVER_URL) {
    dotWindow.loadURL(`${process.env.VITE_DEV_SERVER_URL}/dot.html`);
  } else {
    dotWindow.loadFile(path.join(__dirname, '../dist/dot.html'));
  }

  return dotWindow;
}

// ==================== Panel Window (快捷面板) ====================

function createPanelWindow() {
  const panelWindow = new BrowserWindow({
    width: 320,
    height: 180,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    show: false,              // 默认隐藏
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 失焦自动隐藏
  panelWindow.on('blur', () => {
    panelWindow.hide();
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    panelWindow.loadURL(`${process.env.VITE_DEV_SERVER_URL}/panel.html`);
  } else {
    panelWindow.loadFile(path.join(__dirname, '../dist/panel.html'));
  }

  return panelWindow;
}
```

### 3.2 IPC Handlers

在 `main.cjs` 中注册新的 IPC 通道：

```javascript
// ==================== Dot/Panel IPC ====================

ipcMain.handle('toggle-panel', (_event, show) => {
  if (show) {
    // 锚定在小圆点旁边
    const dotBounds = dotWindow.getBounds();
    const panelX = dotBounds.x - 264;  // 320 - 56
    const panelY = dotBounds.y + 64;   // 圆点下方 8px
    panelWindow.setPosition(panelX, panelY);
    panelWindow.show();
    panelWindow.focus();
  } else {
    panelWindow.hide();
  }
});

ipcMain.handle('toggle-dashboard', (_event, show) => {
  if (show) {
    mainWindow.show();
    mainWindow.focus();
  } else {
    mainWindow.hide();
  }
});

ipcMain.handle('save-dot-position', (_event, x, y) => {
  store.set('dotPosition', { x, y });
});

ipcMain.handle('broadcast-recording-state', (_event, isRecording) => {
  // 广播给所有窗口
  dotWindow.webContents.send('recording-state-changed', isRecording);
  panelWindow.webContents.send('recording-state-changed', isRecording);
  mainWindow.webContents.send('recording-state-changed', isRecording);
});
```

### 3.3 Preload 扩展

**文件**: `electron/preload.cjs` — 新增方法

```javascript
// Dot/Panel controls
togglePanel: (show) => ipcRenderer.invoke('toggle-panel', show),
toggleDashboard: (show) => ipcRenderer.invoke('toggle-dashboard', show),
saveDotPosition: (x, y) => ipcRenderer.invoke('save-dot-position', x, y),
broadcastRecordingState: (isRecording) =>
  ipcRenderer.invoke('broadcast-recording-state', isRecording),

// Events (Main → Renderer)
onRecordingStateChanged: (callback) => {
  const listener = (_event, isRecording) => callback(isRecording);
  ipcRenderer.on('recording-state-changed', listener);
  return () => ipcRenderer.removeListener('recording-state-changed', listener);
},
```

### 3.4 前端入口文件

**文件**: `dot.html`（与 `index.html` 同级）

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { background: transparent; overflow: hidden; width: 56px; height: 56px; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/dot-main.jsx"></script>
</body>
</html>
```

**文件**: `panel.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { background: transparent; overflow: hidden; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/panel-main.jsx"></script>
</body>
</html>
```

### 3.5 小圆点组件

**文件**: `src/pages/DotWindow.jsx`

```jsx
import { useState, useEffect, useRef } from 'react';
import './DotWindow.css';

function DotWindow() {
  const [isRecording, setIsRecording] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const isDragging = useRef(false);
  const dragStartTime = useRef(0);

  useEffect(() => {
    const unlisten = window.electronAPI.onRecordingStateChanged((recording) => {
      setIsRecording(recording);
    });
    return () => unlisten();
  }, []);

  const handleMouseDown = (e) => {
    isDragging.current = false;
    dragStartTime.current = Date.now();
  };

  const handleMouseUp = async () => {
    const duration = Date.now() - dragStartTime.current;
    if (duration < 200 && !isDragging.current) {
      // 短按 = 点击 → 弹出面板
      await window.electronAPI.togglePanel(true);
    }
    // 拖拽结束 → 位置由 Electron 的 will-move 事件自动保存
  };

  return (
    <div
      className="dot-container"
      style={{ WebkitAppRegion: 'drag' }}  // 允许拖拽窗口
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className={`dot ${isRecording ? 'recording' : ''} ${isHovered ? 'hovered' : ''}`}>
        {isRecording ? (
          <div className="recording-indicator">
            <div className="pulse-ring" />
            <div className="recording-dot" />
          </div>
        ) : (
          <svg className="ami-logo" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="white" strokeWidth="2"/>
            <circle cx="12" cy="12" r="4" fill="white"/>
          </svg>
        )}
      </div>
    </div>
  );
}

export default DotWindow;
```

**文件**: `src/pages/DotWindow.css`

```css
.dot-container {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
}

.dot {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
  box-shadow: 0 4px 12px rgba(20, 184, 166, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.dot.hovered {
  transform: scale(1.08);
  box-shadow: 0 6px 16px rgba(20, 184, 166, 0.5);
}

.dot.recording {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
}

.ami-logo { width: 24px; height: 24px; }

.recording-indicator {
  position: relative;
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
}
.recording-dot {
  width: 12px; height: 12px;
  border-radius: 50%; background: white;
}
.pulse-ring {
  position: absolute;
  width: 24px; height: 24px;
  border-radius: 50%; border: 2px solid white;
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1.8); opacity: 0; }
}
```

### 3.6 快捷面板组件

**文件**: `src/pages/PanelWindow.jsx`

```jsx
import { useState, useEffect, useRef } from 'react';
import './PanelWindow.css';

function PanelWindow() {
  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    // 窗口显示时聚焦输入框
    inputRef.current?.focus();

    const unlisten = window.electronAPI.onRecordingStateChanged((recording) => {
      setIsRecording(recording);
    });
    return () => unlisten();
  }, []);

  const handleSubmit = async () => {
    if (input.trim()) {
      // 有输入：发送任务，打开 Dashboard
      await window.electronAPI.togglePanel(false);
      await window.electronAPI.toggleDashboard(true);
      // TODO: 通过 IPC 传递任务内容给 mainWindow
    } else {
      // 无输入：开始/停止录制
      await window.electronAPI.broadcastRecordingState(!isRecording);
      await window.electronAPI.togglePanel(false);
    }
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      window.electronAPI.togglePanel(false);
    }
  };

  return (
    <div className="panel-container">
      <div className="panel-content">
        <div className="input-wrapper">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入任务..."
            className="panel-input"
          />
          <button className="submit-button" onClick={handleSubmit}>
            {input.trim() ? '发送' : (isRecording ? '停止' : '录制')}
          </button>
        </div>
        <div className="panel-hint">
          {input.trim()
            ? '⏎ 发送任务给 Ami'
            : (isRecording ? '⏎ 停止录制' : '⏎ 开始录制，教 Ami 新技能')}
        </div>
        <div className="panel-divider" />
        <button className="dashboard-button" onClick={async () => {
          await window.electronAPI.togglePanel(false);
          await window.electronAPI.toggleDashboard(true);
        }}>
          <span>打开 Dashboard</span>
          <span className="shortcut">⌘D</span>
        </button>
      </div>
    </div>
  );
}

export default PanelWindow;
```

### 3.7 Vite 多入口配置

**文件**: `vite.config.js` — 新增 rollup 多入口

```javascript
build: {
  rollupOptions: {
    input: {
      main: 'index.html',
      dot: 'dot.html',
      panel: 'panel.html',
    },
  },
},
```

### 3.8 拖拽与位置记忆

Electron 的 frameless window 通过 CSS `-webkit-app-region: drag` 实现拖拽。位置保存通过 `will-move` 事件：

```javascript
// main.cjs — dotWindow 创建后
dotWindow.on('will-move', (_event, newBounds) => {
  store.set('dotPosition', { x: newBounds.x, y: newBounds.y });
});
```

---

## 4. 全局快捷键

### 4.1 快捷键定义

| 快捷键 | 功能 |
|-------|------|
| `⌘ + Shift + A` | 显示/隐藏快捷面板 |
| `⌘ + D` | 打开 Dashboard |
| `Escape` | 隐藏面板 |

### 4.2 实现

```javascript
// main.cjs — 在 app.whenReady() 中注册
const { globalShortcut } = require('electron');

globalShortcut.register('CommandOrControl+Shift+A', () => {
  if (panelWindow.isVisible()) {
    panelWindow.hide();
  } else {
    const dotBounds = dotWindow.getBounds();
    panelWindow.setPosition(dotBounds.x - 264, dotBounds.y + 64);
    panelWindow.show();
    panelWindow.focus();
  }
});

globalShortcut.register('CommandOrControl+D', () => {
  mainWindow.show();
  mainWindow.focus();
});

// app.will-quit 中反注册
app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
```

---

## 5. 系统托盘（可选增强）

| 功能 | 描述 |
|-----|------|
| 左键点击 | 显示/隐藏小圆点 |
| 右键菜单 | 打开 Dashboard / 开始录制 / 退出 |
| 状态指示 | 录制中显示红点图标 |

```javascript
const { Tray, Menu, nativeImage } = require('electron');

const tray = new Tray(nativeImage.createFromPath(trayIconPath));
tray.setContextMenu(Menu.buildFromTemplate([
  { label: '打开 Dashboard', click: () => { mainWindow.show(); mainWindow.focus(); } },
  { label: '开始录制', click: () => { /* broadcast recording state */ } },
  { type: 'separator' },
  { label: '退出', click: () => app.quit() },
]));
```

---

## 6. 实现计划

### Phase 1: 基础窗口 (MVP)

| 任务 | 文件 | 优先级 |
|-----|------|-------|
| 创建 dotWindow / panelWindow | `electron/main.cjs` | P0 |
| 新增 dot.html / panel.html 入口 | 项目根目录 | P0 |
| 实现 DotWindow 组件 | `src/pages/DotWindow.jsx` | P0 |
| 实现 PanelWindow 组件 | `src/pages/PanelWindow.jsx` | P0 |
| IPC 通道注册 | `electron/main.cjs`, `electron/preload.cjs` | P0 |
| Vite 多入口配置 | `vite.config.js` | P0 |

### Phase 2: 交互完善

| 任务 | 优先级 |
|-----|-------|
| 拖拽 + 位置记忆 (electron-store) | P1 |
| 录制状态同步（广播给三个窗口） | P1 |
| 任务提交集成（面板 → Dashboard） | P1 |
| 深色模式支持 (CSS media query) | P1 |

### Phase 3: 增强功能

| 任务 | 优先级 |
|-----|-------|
| 全局快捷键 (globalShortcut) | P2 |
| 系统托盘 | P2 |
| 多显示器支持（screen API） | P2 |
| 动画效果增强 | P2 |

---

## 7. 待讨论

- [ ] 小圆点默认位置：右下角固定位置 vs 屏幕中央？
- [ ] 是否需要"隐藏小圆点"选项（完全依赖托盘）？
- [ ] 多显示器场景下，小圆点是否跟随鼠标所在屏幕？
- [ ] 面板失焦隐藏的行为是否需要可配置的延迟？
- [ ] mainWindow 启动时是否默认隐藏（仅显示小圆点）？
