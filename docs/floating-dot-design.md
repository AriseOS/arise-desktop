# 浮动小圆点设计文档

> 本文档描述 Ami 桌面应用的核心交互入口——浮动小圆点的技术设计方案。

---

## 1. 产品需求

### 1.1 设计目标

根据产品愿景文档，小圆点是 Ami 的核心交互入口：

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

采用 Tauri 多窗口架构，实现三层窗口结构：

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

| 窗口 | Label | 尺寸 | 特性 | 用途 |
|-----|-------|------|------|------|
| **小圆点** | `dot` | 56×56 | alwaysOnTop, 无边框, 透明, 可拖拽, skipTaskbar | 常驻入口 |
| **快捷面板** | `panel` | 320×180 | alwaysOnTop, 无边框, 锚定在 dot 旁, 失焦隐藏 | 快捷交互 |
| **Dashboard** | `main` | 1400×900 | 标准窗口, 默认隐藏 | 完整功能 |

### 2.3 窗口间通信

```
┌─────────────┐     Tauri Events     ┌─────────────┐
│  dot 窗口   │ ←──────────────────→ │  main 窗口  │
└─────────────┘                      └─────────────┘
       │                                    │
       │      ┌─────────────┐               │
       └────→ │  panel 窗口  │ ←────────────┘
              └─────────────┘

通信机制：
- Tauri Events (emit/listen) - 窗口间事件
- Tauri Store Plugin - 共享持久化状态
- Rust Commands - 窗口控制
```

---

## 3. 实现细节

### 3.1 Tauri 配置

**文件**: `src-tauri/tauri.conf.json`

```json
{
  "app": {
    "windows": [
      {
        "label": "dot",
        "title": "",
        "url": "dot.html",
        "width": 56,
        "height": 56,
        "x": null,
        "y": null,
        "decorations": false,
        "transparent": true,
        "alwaysOnTop": true,
        "resizable": false,
        "skipTaskbar": true,
        "visible": true,
        "focus": false
      },
      {
        "label": "panel",
        "title": "",
        "url": "panel.html",
        "width": 320,
        "height": 180,
        "decorations": false,
        "transparent": true,
        "alwaysOnTop": true,
        "resizable": false,
        "skipTaskbar": true,
        "visible": false,
        "focus": true
      },
      {
        "label": "main",
        "title": "Ami",
        "url": "index.html",
        "width": 1400,
        "height": 900,
        "minWidth": 1000,
        "minHeight": 700,
        "center": true,
        "visible": false
      }
    ]
  }
}
```

**权限配置**: `src-tauri/capabilities/default.json`

```json
{
  "identifier": "default",
  "windows": ["dot", "panel", "main"],
  "permissions": [
    "core:default",
    "core:window:allow-show",
    "core:window:allow-hide",
    "core:window:allow-set-focus",
    "core:window:allow-set-position",
    "core:window:allow-outer-position",
    "core:window:allow-start-dragging",
    "store:default",
    "shell:default"
  ]
}
```

### 3.2 Rust 窗口管理

**文件**: `src-tauri/src/main.rs`

```rust
use tauri::{Manager, PhysicalPosition};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Default)]
struct DotPosition {
    x: i32,
    y: i32,
}

fn get_position_file() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_default()
        .join(".ami")
        .join("dot_position.json")
}

/// 显示/隐藏快捷面板，锚定在小圆点旁边
#[tauri::command]
fn toggle_panel(app: tauri::AppHandle, show: bool) -> Result<(), String> {
    let panel = app.get_webview_window("panel")
        .ok_or("Panel window not found")?;

    if show {
        // 获取小圆点位置，计算面板位置
        if let Some(dot) = app.get_webview_window("dot") {
            if let Ok(dot_pos) = dot.outer_position() {
                // 面板显示在小圆点左下方
                let panel_x = dot_pos.x - 264; // 320 - 56
                let panel_y = dot_pos.y + 64;  // 小圆点下方 8px 间距

                panel.set_position(PhysicalPosition::new(panel_x, panel_y))
                    .map_err(|e| e.to_string())?;
            }
        }
        panel.show().map_err(|e| e.to_string())?;
        panel.set_focus().map_err(|e| e.to_string())?;
    } else {
        panel.hide().map_err(|e| e.to_string())?;
    }

    Ok(())
}

/// 显示/隐藏 Dashboard
#[tauri::command]
fn toggle_dashboard(app: tauri::AppHandle, show: bool) -> Result<(), String> {
    let main = app.get_webview_window("main")
        .ok_or("Main window not found")?;

    if show {
        main.show().map_err(|e| e.to_string())?;
        main.set_focus().map_err(|e| e.to_string())?;
    } else {
        main.hide().map_err(|e| e.to_string())?;
    }

    Ok(())
}

/// 保存小圆点位置
#[tauri::command]
fn save_dot_position(x: i32, y: i32) -> Result<(), String> {
    let position = DotPosition { x, y };
    let path = get_position_file();

    // 确保目录存在
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let json = serde_json::to_string(&position).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| e.to_string())?;

    Ok(())
}

/// 加载小圆点位置
#[tauri::command]
fn load_dot_position() -> Result<DotPosition, String> {
    let path = get_position_file();

    if path.exists() {
        let json = fs::read_to_string(&path).map_err(|e| e.to_string())?;
        serde_json::from_str(&json).map_err(|e| e.to_string())
    } else {
        // 默认位置：屏幕右下角
        Ok(DotPosition { x: -100, y: -100 }) // 负值表示从右下角偏移
    }
}

/// 发送录制状态到所有窗口
#[tauri::command]
fn broadcast_recording_state(app: tauri::AppHandle, is_recording: bool) -> Result<(), String> {
    app.emit("recording-state-changed", is_recording)
        .map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            toggle_panel,
            toggle_dashboard,
            save_dot_position,
            load_dot_position,
            broadcast_recording_state,
            // ... 其他现有命令
        ])
        .setup(|app| {
            // 恢复小圆点位置
            if let Some(dot) = app.get_webview_window("dot") {
                if let Ok(pos) = load_dot_position() {
                    // 处理负值（相对于屏幕右下角）
                    // 实际实现需要获取屏幕尺寸
                    let _ = dot.set_position(PhysicalPosition::new(pos.x, pos.y));
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### 3.3 前端入口文件

需要创建独立的 HTML 入口文件：

**文件**: `src/dot.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Ami Dot</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      background: transparent;
      overflow: hidden;
      width: 56px;
      height: 56px;
    }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/dot-main.jsx"></script>
</body>
</html>
```

**文件**: `src/panel.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Ami Panel</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      background: transparent;
      overflow: hidden;
    }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/panel-main.jsx"></script>
</body>
</html>
```

### 3.4 小圆点组件

**文件**: `src/pages/DotWindow.jsx`

```jsx
import { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import './DotWindow.css';

function DotWindow() {
  const [isRecording, setIsRecording] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const isDragging = useRef(false);
  const dragStartTime = useRef(0);

  useEffect(() => {
    // 监听录制状态变化
    const unlisten = listen('recording-state-changed', (event) => {
      setIsRecording(event.payload);
    });

    return () => {
      unlisten.then(fn => fn());
    };
  }, []);

  const handleMouseDown = () => {
    isDragging.current = false;
    dragStartTime.current = Date.now();
  };

  const handleMouseUp = async (e) => {
    const dragDuration = Date.now() - dragStartTime.current;

    // 如果拖拽时间小于 200ms，视为点击
    if (dragDuration < 200 && !isDragging.current) {
      await invoke('toggle_panel', { show: true });
    } else {
      // 保存新位置
      const window = getCurrentWindow();
      const position = await window.outerPosition();
      await invoke('save_dot_position', {
        x: position.x,
        y: position.y
      });
    }
  };

  const handleDragStart = async () => {
    isDragging.current = true;
    const window = getCurrentWindow();
    await window.startDragging();
  };

  return (
    <div
      className="dot-container"
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseMove={(e) => {
        if (e.buttons === 1) {
          handleDragStart();
        }
      }}
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

.ami-logo {
  width: 24px;
  height: 24px;
}

/* 录制状态指示器 */
.recording-indicator {
  position: relative;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.recording-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: white;
}

.pulse-ring {
  position: absolute;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid white;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0% {
    transform: scale(1);
    opacity: 1;
  }
  100% {
    transform: scale(1.8);
    opacity: 0;
  }
}
```

### 3.5 快捷面板组件

**文件**: `src/pages/PanelWindow.jsx`

```jsx
import { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import './PanelWindow.css';

function PanelWindow() {
  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    // 窗口获得焦点时，聚焦输入框
    const unlistenFocus = listen('tauri://focus', () => {
      inputRef.current?.focus();
    });

    // 窗口失去焦点时，隐藏面板
    const unlistenBlur = listen('tauri://blur', async () => {
      // 延迟一下，避免点击 Dashboard 按钮时立即隐藏
      setTimeout(async () => {
        await invoke('toggle_panel', { show: false });
      }, 100);
    });

    // 监听录制状态
    const unlistenRecording = listen('recording-state-changed', (event) => {
      setIsRecording(event.payload);
    });

    // 初始聚焦
    inputRef.current?.focus();

    return () => {
      unlistenFocus.then(fn => fn());
      unlistenBlur.then(fn => fn());
      unlistenRecording.then(fn => fn());
    };
  }, []);

  const handleSubmit = async () => {
    if (isSubmitting) return;

    setIsSubmitting(true);

    try {
      if (input.trim()) {
        // 有输入：发送任务
        // TODO: 调用任务提交 API
        await invoke('toggle_panel', { show: false });
        await invoke('toggle_dashboard', { show: true });
        // 通过事件传递任务内容给 Dashboard
        // emit('submit-task', input.trim());
      } else {
        // 无输入：开始/停止录制
        if (isRecording) {
          // TODO: 停止录制
          await invoke('broadcast_recording_state', { isRecording: false });
        } else {
          // TODO: 开始录制
          await invoke('broadcast_recording_state', { isRecording: true });
        }
        await invoke('toggle_panel', { show: false });
      }
    } finally {
      setIsSubmitting(false);
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      invoke('toggle_panel', { show: false });
    }
  };

  const openDashboard = async () => {
    await invoke('toggle_panel', { show: false });
    await invoke('toggle_dashboard', { show: true });
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
            disabled={isSubmitting}
          />
          <button
            className="submit-button"
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {input.trim() ? '发送' : (isRecording ? '停止' : '录制')}
          </button>
        </div>

        <div className="panel-hint">
          {input.trim()
            ? '⏎ 发送任务给 Ami'
            : (isRecording
                ? '⏎ 停止录制'
                : '⏎ 开始录制，教 Ami 新技能'
              )
          }
        </div>

        <div className="panel-divider" />

        <button className="dashboard-button" onClick={openDashboard}>
          <span>打开 Dashboard</span>
          <span className="shortcut">⌘D</span>
        </button>
      </div>
    </div>
  );
}

export default PanelWindow;
```

**文件**: `src/pages/PanelWindow.css`

```css
.panel-container {
  width: 320px;
  height: 180px;
  padding: 8px;
}

.panel-content {
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 12px;
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.12),
    0 0 0 1px rgba(0, 0, 0, 0.05);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.input-wrapper {
  display: flex;
  gap: 8px;
}

.panel-input {
  flex: 1;
  height: 40px;
  padding: 0 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.panel-input:focus {
  border-color: #14b8a6;
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.1);
}

.panel-input::placeholder {
  color: #9ca3af;
}

.submit-button {
  height: 40px;
  padding: 0 16px;
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.1s;
}

.submit-button:hover {
  opacity: 0.9;
}

.submit-button:active {
  transform: scale(0.98);
}

.submit-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.panel-hint {
  font-size: 12px;
  color: #6b7280;
  text-align: center;
}

.panel-divider {
  height: 1px;
  background: #e5e7eb;
  margin: 4px 0;
}

.dashboard-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: 36px;
  padding: 0 12px;
  background: transparent;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 13px;
  color: #374151;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s;
}

.dashboard-button:hover {
  background: #f9fafb;
  border-color: #d1d5db;
}

.dashboard-button .shortcut {
  font-size: 11px;
  color: #9ca3af;
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .panel-content {
    background: rgba(30, 30, 30, 0.95);
  }

  .panel-input {
    background: #2d2d2d;
    border-color: #404040;
    color: #f3f4f6;
  }

  .panel-input:focus {
    border-color: #14b8a6;
    box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.2);
  }

  .panel-hint {
    color: #9ca3af;
  }

  .panel-divider {
    background: #404040;
  }

  .dashboard-button {
    border-color: #404040;
    color: #e5e7eb;
  }

  .dashboard-button:hover {
    background: #2d2d2d;
  }

  .dashboard-button .shortcut {
    background: #404040;
    color: #9ca3af;
  }
}
```

### 3.6 入口文件

**文件**: `src/dot-main.jsx`

```jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import DotWindow from './pages/DotWindow';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <DotWindow />
  </React.StrictMode>
);
```

**文件**: `src/panel-main.jsx`

```jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import PanelWindow from './pages/PanelWindow';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PanelWindow />
  </React.StrictMode>
);
```

### 3.7 Vite 配置更新

**文件**: `vite.config.js`

```javascript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        dot: 'src/dot.html',
        panel: 'src/panel.html',
      },
    },
  },
  // ... 其他配置
});
```

---

## 4. 系统托盘（可选增强）

作为小圆点的补充，可以添加系统托盘支持：

### 4.1 托盘功能

| 功能 | 描述 |
|-----|------|
| 左键点击 | 显示/隐藏小圆点 |
| 右键菜单 | 打开 Dashboard / 开始录制 / 退出 |
| 状态指示 | 录制中显示红点 |

### 4.2 托盘配置

**文件**: `src-tauri/Cargo.toml`

```toml
[dependencies]
tauri-plugin-system-tray = "2"
```

**托盘初始化** (main.rs):

```rust
use tauri::{
    menu::{Menu, MenuItem},
    tray::{TrayIconBuilder, TrayIconEvent},
};

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // 创建托盘菜单
            let menu = Menu::with_items(app, &[
                &MenuItem::with_id(app, "dashboard", "打开 Dashboard", true, None::<&str>)?,
                &MenuItem::with_id(app, "recording", "开始录制", true, None::<&str>)?,
                &MenuItem::Separator(app)?,
                &MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?,
            ])?;

            // 创建托盘图标
            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "dashboard" => {
                            if let Some(main) = app.get_webview_window("main") {
                                main.show().ok();
                                main.set_focus().ok();
                            }
                        }
                        "recording" => {
                            // TODO: 触发录制
                        }
                        "quit" => {
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { .. } = event {
                        // 点击托盘图标显示/隐藏小圆点
                        if let Some(dot) = tray.app_handle().get_webview_window("dot") {
                            if dot.is_visible().unwrap_or(false) {
                                dot.hide().ok();
                            } else {
                                dot.show().ok();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

---

## 5. 全局快捷键

### 5.1 快捷键定义

| 快捷键 | 功能 |
|-------|------|
| `⌘ + Shift + A` | 显示/隐藏快捷面板 |
| `⌘ + D` | 打开 Dashboard |
| `⌘ + R` | 开始/停止录制 |
| `Escape` | 隐藏面板 |

### 5.2 实现

**文件**: `src-tauri/Cargo.toml`

```toml
[dependencies]
tauri-plugin-global-shortcut = "2"
```

**注册快捷键** (main.rs):

```rust
use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut, ShortcutState};

fn main() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        if shortcut.matches(Modifiers::SUPER | Modifiers::SHIFT, Code::KeyA) {
                            // ⌘ + Shift + A: 切换面板
                            let _ = toggle_panel(app.clone(), true);
                        } else if shortcut.matches(Modifiers::SUPER, Code::KeyD) {
                            // ⌘ + D: 打开 Dashboard
                            let _ = toggle_dashboard(app.clone(), true);
                        }
                    }
                })
                .build(),
        )
        .setup(|app| {
            // 注册快捷键
            let shortcut_manager = app.global_shortcut();
            shortcut_manager.register(
                Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::KeyA)
            )?;
            shortcut_manager.register(
                Shortcut::new(Some(Modifiers::SUPER), Code::KeyD)
            )?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

---

## 6. 状态同步

### 6.1 共享状态

使用 Tauri Store Plugin 在窗口间共享状态：

```javascript
// 在任意窗口中
import { Store } from '@tauri-apps/plugin-store';

const store = new Store('.ami-state.json');

// 写入状态
await store.set('isRecording', true);
await store.save();

// 读取状态
const isRecording = await store.get('isRecording');

// 监听变化
await store.onKeyChange('isRecording', (value) => {
  console.log('Recording state changed:', value);
});
```

### 6.2 事件通信

```javascript
// 发送事件 (任意窗口)
import { emit } from '@tauri-apps/api/event';
await emit('task-submitted', { description: '帮我查询...' });

// 接收事件 (Dashboard)
import { listen } from '@tauri-apps/api/event';
await listen('task-submitted', (event) => {
  const { description } = event.payload;
  // 处理任务
});
```

---

## 7. 实现计划

### Phase 1: 基础窗口 (MVP)

| 任务 | 文件 | 优先级 |
|-----|------|-------|
| 配置多窗口 | `tauri.conf.json` | P0 |
| 创建 dot/panel HTML 入口 | `src/dot.html`, `src/panel.html` | P0 |
| 实现 DotWindow 组件 | `src/pages/DotWindow.jsx` | P0 |
| 实现 PanelWindow 组件 | `src/pages/PanelWindow.jsx` | P0 |
| Rust 窗口管理命令 | `src-tauri/src/main.rs` | P0 |
| 更新 Vite 配置 | `vite.config.js` | P0 |

### Phase 2: 交互完善

| 任务 | 文件 | 优先级 |
|-----|------|-------|
| 拖拽和位置保存 | `main.rs` + `DotWindow.jsx` | P1 |
| 录制状态同步 | Events + Store | P1 |
| 任务提交集成 | `PanelWindow.jsx` + API | P1 |
| 深色模式支持 | CSS | P1 |

### Phase 3: 增强功能

| 任务 | 文件 | 优先级 |
|-----|------|-------|
| 系统托盘 | `main.rs` | P2 |
| 全局快捷键 | `main.rs` + plugin | P2 |
| 多显示器支持 | `main.rs` | P2 |
| 动画效果增强 | CSS | P2 |

---

## 8. 待讨论

- [ ] 小圆点默认位置：右下角固定位置 vs 用户上次拖拽位置？
- [ ] 是否需要"隐藏小圆点"的选项（完全依赖托盘）？
- [ ] 多显示器场景下，小圆点是否需要跟随鼠标所在屏幕？
- [ ] 面板失焦隐藏的延迟时间（当前 100ms）是否合适？

---

## 附录：文件清单

新增/修改的文件列表：

```
src/clients/desktop_app/
├── src/
│   ├── dot.html                 # 新增：小圆点窗口入口
│   ├── panel.html               # 新增：快捷面板窗口入口
│   ├── dot-main.jsx             # 新增：小圆点 React 入口
│   ├── panel-main.jsx           # 新增：快捷面板 React 入口
│   └── pages/
│       ├── DotWindow.jsx        # 新增：小圆点组件
│       ├── DotWindow.css        # 新增：小圆点样式
│       ├── PanelWindow.jsx      # 新增：快捷面板组件
│       └── PanelWindow.css      # 新增：快捷面板样式
├── src-tauri/
│   ├── tauri.conf.json          # 修改：添加多窗口配置
│   ├── Cargo.toml               # 修改：添加插件依赖
│   ├── capabilities/
│   │   └── default.json         # 修改：添加窗口权限
│   └── src/
│       └── main.rs              # 修改：添加窗口管理命令
└── vite.config.js               # 修改：多入口构建配置
```
