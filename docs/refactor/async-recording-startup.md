# 异步录制启动优化方案

## 📋 目录

- [1. 问题分析](#1-问题分析)
- [2. 解决方案概述](#2-解决方案概述)
- [3. 详细设计](#3-详细设计)
- [4. 实施步骤](#4-实施步骤)
- [5. 风险评估](#5-风险评估)
- [6. 测试计划](#6-测试计划)

---

## 1. 问题分析

### 1.1 当前延迟来源

用户点击 "Start Recording" 按钮后，需要等待 **8-10 秒** 才能看到响应，延迟来源：

| 步骤 | 延迟 | 代码位置 | 类型 |
|------|------|---------|------|
| 浏览器启动 | 2 秒 | `daemon.py:874` | 硬编码 sleep |
| 页面加载 | 2 秒 | `cdp_recorder.py:115` | 硬编码 sleep |
| CDP Session | 0.5 秒 | `monitor.py:76` | 硬编码 sleep |
| 页面就绪检查 | 4 秒 | browser_use 内部 | 超时等待 |
| **总计** | **8.5+ 秒** | - | - |

### 1.2 根本原因

1. **同步等待模式**：API 必须等待所有初始化完成才能返回
2. **硬编码延迟**：用固定时间等待异步操作，而不是检查实际状态
3. **过度保守**：about:blank 空白页也用 4 秒超时检查

### 1.3 影响

- 用户体验差：点击按钮后长时间无响应，以为卡死
- 资源浪费：即使浏览器已就绪，也要等待固定时间
- 不可扩展：慢机器等不够，快机器浪费时间

---

## 2. 解决方案概述

### 2.1 核心思路

**将同步等待改为异步返回 + 状态轮询**

```
旧方案（同步）:
用户点击 → 后端初始化（8秒）→ 返回响应 → 前端显示

新方案（异步）:
用户点击 → 后端立即返回 → 前端轮询状态 → 显示进度 → 就绪通知
           ↓
        后台初始化（8秒）
```

### 2.2 改动范围

| 层级 | 文件 | 改动类型 | 难度 |
|------|------|---------|------|
| 后端状态管理 | `cdp_recorder.py` | 新增状态枚举和方法 | ⭐⭐ 中等 |
| 后端API | `daemon.py` | 修改启动逻辑，新增状态端点 | ⭐⭐ 中等 |
| 前端API | `api.js` | 新增状态查询方法 | ⭐ 简单 |
| 前端UI | `QuickStartPage.jsx` | 修改启动流程，新增轮询 | ⭐⭐ 中等 |

**总体评估：中等难度，预计 2-4 小时完成**

---

## 3. 详细设计

### 3.1 后端改造

#### 3.1.1 CDPRecorder 状态管理增强

**文件：** `src/clients/desktop_app/ami_daemon/services/cdp_recorder.py`

**新增状态枚举：**

```python
from enum import Enum

class RecordingStatus(Enum):
    """录制状态"""
    NOT_STARTED = "not_started"      # 未开始
    INITIALIZING = "initializing"    # 初始化中（浏览器启动、导航、监控设置）
    RECORDING = "recording"          # 正在录制
    ERROR = "error"                  # 初始化失败
    STOPPED = "stopped"              # 已停止
```

**新增字段：**

```python
class CDPRecorder:
    def __init__(self, ...):
        # 现有字段...

        # 新增：状态管理
        self._status: RecordingStatus = RecordingStatus.NOT_STARTED
        self._error_message: Optional[str] = None
        self._initialization_task: Optional[asyncio.Task] = None
```

**新增方法：**

```python
def get_status(self) -> Dict[str, Any]:
    """获取当前录制状态

    Returns:
        {
            "status": str,  # RecordingStatus 枚举值
            "session_id": Optional[str],
            "operations_count": int,
            "error": Optional[str]
        }
    """
    return {
        "status": self._status.value,
        "session_id": self.current_session_id,
        "operations_count": len(self.operations),
        "error": self._error_message
    }

async def start_recording_async(
    self,
    session_id: str,
    url: str,
    user_id: str,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """异步启动录制（立即返回，后台初始化）

    Args:
        session_id: 预先生成的会话ID
        url: 起始URL
        user_id: 用户ID
        metadata: 任务元数据

    Returns:
        {
            "session_id": str,
            "status": "initializing",
            "url": str
        }
    """
    # 1. 预先设置状态
    self.current_session_id = session_id
    self.current_user_id = user_id
    self.operations = []
    self.recording_start_time = datetime.now()
    self.task_metadata = metadata or {}
    self._status = RecordingStatus.INITIALIZING
    self._error_message = None

    # 2. 立即返回
    result = {
        "session_id": session_id,
        "status": self._status.value,
        "url": url
    }

    # 3. 后台任务：完成初始化
    self._initialization_task = asyncio.create_task(
        self._complete_initialization(url)
    )

    return result

async def _complete_initialization(self, url: str):
    """后台完成录制初始化

    完成后设置状态为 RECORDING 或 ERROR
    """
    try:
        # 1. 获取浏览器会话（假设已由 daemon.py 启动）
        browser_session_info = self.browser.global_session
        if not browser_session_info:
            raise RuntimeError("Global browser session not initialized")

        # 2. 初始化监控器
        from src.clients.desktop_app.ami_daemon.base_agent.tools.browser_use.user_behavior.monitor import (
            SimpleUserBehaviorMonitor
        )
        self.monitor = SimpleUserBehaviorMonitor(operation_list=self.operations)

        # 3. 导航到起始URL（优化：about:blank 不需要等待）
        await browser_session_info.session.navigate_to(url)

        if url == "about:blank":
            await asyncio.sleep(0.1)  # about:blank 几乎瞬间加载
        else:
            await asyncio.sleep(1.0)  # 真实网页给 1 秒缓冲

        # 4. 设置监控（CDP Binding + 脚本注入）
        await self.monitor.setup_monitoring(browser_session_info.session)

        # 5. 启用 DOM 捕获
        self.monitor.enable_dom_capture(True)
        logger.info("DOM capture enabled for recording")

        # 6. 标记为正在录制
        self._is_recording = True
        self._status = RecordingStatus.RECORDING
        logger.info(f"✅ Recording initialization complete: {self.current_session_id}")

    except Exception as e:
        logger.error(f"❌ Recording initialization failed: {e}")
        self._status = RecordingStatus.ERROR
        self._error_message = str(e)
        # 清理状态
        self.current_session_id = None
        self.current_user_id = None
        self.operations = []
        self.monitor = None
```

#### 3.1.2 Daemon API 改造

**文件：** `src/clients/desktop_app/ami_daemon/daemon.py`

**修改启动端点：**

```python
@app.post("/api/v1/recordings/start", response_model=StartRecordingResponse)
async def start_recording(request: StartRecordingRequest):
    """Start CDP recording session (Async - returns immediately)

    Returns immediately with status="initializing", frontend should poll
    GET /api/v1/recordings/{session_id}/status to check when ready.
    """
    try:
        # 1. 预先生成 session_id
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting recording: session_id={session_id}, url={request.url}")

        # 2. 启动浏览器（如果未运行）
        browser_status = browser_manager.get_status()
        if not browser_status["is_running"]:
            logger.info("Browser not running, starting browser for recording...")
            # 后台启动浏览器（不等待）
            asyncio.create_task(
                browser_manager.start_browser(headless=False)
            )

        # 3. 准备元数据
        metadata = request.task_metadata or {}
        metadata.update({
            "title": request.title,
            "description": request.description
        })

        # 4. 异步启动录制（立即返回）
        result = await cdp_recorder.start_recording_async(
            session_id=session_id,
            url=request.url,
            user_id=request.user_id,
            metadata=metadata
        )

        logger.info(f"Recording initialization started: {session_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**新增状态查询端点：**

```python
from pydantic import BaseModel

class RecordingStatusResponse(BaseModel):
    """录制状态响应"""
    status: str  # "not_started" | "initializing" | "recording" | "error" | "stopped"
    session_id: Optional[str] = None
    operations_count: int = 0
    error: Optional[str] = None

@app.get("/api/v1/recordings/{session_id}/status", response_model=RecordingStatusResponse)
async def get_recording_status(session_id: str):
    """Get recording status (for polling)

    Frontend should poll this endpoint every 300-500ms until status becomes "recording"
    """
    try:
        # 检查是否是当前会话
        if cdp_recorder.current_session_id != session_id:
            return RecordingStatusResponse(
                status="not_started",
                session_id=None,
                operations_count=0
            )

        # 获取当前状态
        status_info = cdp_recorder.get_status()
        return RecordingStatusResponse(**status_info)

    except Exception as e:
        logger.error(f"Failed to get recording status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**同时优化浏览器启动：**

```python
# 在 daemon.py 中添加浏览器启动状态查询
@app.get("/api/v1/browser/status")
async def get_browser_status():
    """Get browser status

    Returns:
        {
            "is_running": bool,
            "state": str,  # "not_started" | "starting" | "running" | "error"
            "pid": Optional[int]
        }
    """
    try:
        status = browser_manager.get_status()
        return {
            "is_running": status["is_running"],
            "state": status.get("state", "unknown"),
            "pid": status.get("pid")
        }
    except Exception as e:
        logger.error(f"Failed to get browser status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 3.2 前端改造

#### 3.2.1 API 客户端增强

**文件：** `src/clients/desktop_app/src/utils/api.js`

**新增方法：**

```javascript
/**
 * Get recording status (for polling)
 *
 * @param {string} sessionId - Recording session ID
 * @returns {Promise<object>} Status: {status, session_id, operations_count, error}
 */
async getRecordingStatus(sessionId) {
  return await this.callAppBackend(`/api/v1/recordings/${sessionId}/status`);
}

/**
 * Get browser status
 *
 * @returns {Promise<object>} Status: {is_running, state, pid}
 */
async getBrowserStatus() {
  return await this.callAppBackend('/api/v1/browser/status');
}

/**
 * Wait for recording to be ready (polling helper)
 *
 * @param {string} sessionId - Recording session ID
 * @param {number} timeoutMs - Max wait time in ms (default 30000)
 * @param {function} onProgress - Progress callback(status)
 * @returns {Promise<void>}
 * @throws {Error} If timeout or initialization fails
 */
async waitForRecordingReady(sessionId, timeoutMs = 30000, onProgress = null) {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    try {
      const status = await this.getRecordingStatus(sessionId);

      // 通知进度
      if (onProgress) {
        onProgress(status);
      }

      // 检查状态
      if (status.status === 'recording') {
        return; // 就绪
      }

      if (status.status === 'error') {
        throw new Error(status.error || 'Recording initialization failed');
      }

      // 继续轮询
      await new Promise(resolve => setTimeout(resolve, 300)); // 300ms 间隔

    } catch (error) {
      // 网络错误等，继续重试
      console.warn('[API] Polling error:', error);
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }

  throw new Error('Timeout waiting for recording to be ready');
}
```

#### 3.2.2 前端 UI 改造

**文件：** `src/clients/desktop_app/src/pages/QuickStartPage.jsx`

**新增状态变量：**

```javascript
const [initializationStatus, setInitializationStatus] = useState(null);
// null | "browser_starting" | "navigating" | "setting_up_monitor" | "ready"
```

**修改 handleStartRecording：**

```javascript
const handleStartRecording = async () => {
  try {
    showStatus("Starting recording...", "info");

    // 1. 调用启动 API（立即返回）
    const result = await api.callAppBackend('/api/v1/recordings/start', {
      method: "POST",
      body: JSON.stringify({
        url: "about:blank",
        user_id: userId,
        title: "Quick Start Recording",
        description: "Recording from Quick Start",
        task_metadata: {
          quick_start: true
        }
      })
    });

    setCurrentSessionId(result.session_id);

    // 2. 立即切换到 recording 界面（显示初始化进度）
    setStep('recording');

    // 3. 轮询等待就绪
    showStatus("Initializing recording...", "info");

    await api.waitForRecordingReady(
      result.session_id,
      30000, // 30 秒超时
      (status) => {
        // 显示进度
        setInitializationStatus(status.status);

        if (status.status === 'initializing') {
          showStatus("Setting up browser monitoring...", "info");
        }
      }
    );

    // 4. 就绪！
    setInitializationStatus('ready');
    showStatus("Recording started! Navigate to any website in the browser", "success");

  } catch (error) {
    console.error("Start recording error:", error);
    showStatus(`Failed to start recording: ${error.message}`, "error");
    setStep('input'); // 返回输入界面
  }
};
```

**优化 recording 界面显示：**

```javascript
const renderRecording = () => (
  <div className="recording-page-container">
    <div className="recording-top-section">
      <div className="recording-status-bar">
        <div className="recording-indicator">
          <span className="recording-dot"></span>
          <span>
            {initializationStatus === 'ready'
              ? 'Recording...'
              : 'Initializing...'}
          </span>
        </div>

        {/* 显示初始化进度 */}
        {initializationStatus !== 'ready' && (
          <div className="initialization-progress">
            <Icon icon="loader" className="spinning" />
            <span>Setting up monitoring...</span>
          </div>
        )}

        <div className="recording-stats">
          <span className="operations-badge">{operationsCount} operations</span>
          <span className="session-id">Session: {currentSessionId}</span>
        </div>
      </div>

      {/* ... 其余代码不变 ... */}
    </div>

    {/* ... 操作列表等 ... */}
  </div>
);
```

### 3.3 额外优化：移除硬编码等待

**在实施异步方案的同时，顺便移除硬编码 sleep：**

#### 3.3.1 优化 monitor.py

**文件：** `src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use/user_behavior/monitor.py`

```python
# 第 76 行
# await asyncio.sleep(0.5)  # ❌ 移除或缩短
await asyncio.sleep(0.05)  # ✅ 改为 50ms
```

#### 3.3.2 优化 about:blank 处理

在 `cdp_recorder.py` 的 `_complete_initialization` 中已经做了：

```python
if url == "about:blank":
    await asyncio.sleep(0.1)  # 100ms 足够
else:
    await asyncio.sleep(1.0)  # 真实网页 1 秒
```

---

## 4. 实施步骤

### 4.1 阶段 1：后端基础改造（1-1.5 小时）

**优先级：⭐⭐⭐⭐⭐**

```bash
# 1. 修改 CDPRecorder
vi src/clients/desktop_app/ami_daemon/services/cdp_recorder.py

# 添加：
# - RecordingStatus 枚举
# - get_status() 方法
# - start_recording_async() 方法
# - _complete_initialization() 方法

# 2. 修改 daemon.py
vi src/clients/desktop_app/ami_daemon/daemon.py

# 修改：
# - start_recording 端点改为异步模式
#
# 添加：
# - RecordingStatusResponse 模型
# - get_recording_status 端点
# - get_browser_status 端点（可选）
```

**验证点：**
```bash
# 启动后端
cd src/clients/desktop_app
python -m ami_daemon.daemon

# 测试状态端点
curl http://localhost:52030/api/v1/recordings/session_test/status
# 应返回：{"status": "not_started", "session_id": null, "operations_count": 0}
```

### 4.2 阶段 2：前端基础改造（1 小时）

**优先级：⭐⭐⭐⭐⭐**

```bash
# 1. 修改 api.js
vi src/clients/desktop_app/src/utils/api.js

# 添加：
# - getRecordingStatus() 方法
# - getBrowserStatus() 方法
# - waitForRecordingReady() 辅助方法

# 2. 修改 QuickStartPage.jsx
vi src/clients/desktop_app/src/pages/QuickStartPage.jsx

# 修改：
# - handleStartRecording 改为轮询模式
#
# 添加：
# - initializationStatus 状态变量
# - 初始化进度显示 UI
```

**验证点：**
```bash
# 启动前端
cd src/clients/desktop_app
npm run tauri dev

# 手动测试：
# 1. 点击 "Start Recording"
# 2. 观察是否立即切换到 recording 界面
# 3. 观察是否显示 "Initializing..." 状态
# 4. 观察是否在几秒后变为 "Recording..." 状态
```

### 4.3 阶段 3：额外优化（0.5 小时）

**优先级：⭐⭐⭐**

```bash
# 1. 移除硬编码 sleep
vi src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use/user_behavior/monitor.py
# 第 76 行：await asyncio.sleep(0.5) → await asyncio.sleep(0.05)

# 2. about:blank 已在 _complete_initialization 中优化，无需额外改动
```

### 4.4 阶段 4：测试与调优（1 小时）

**优先级：⭐⭐⭐⭐⭐**

```bash
# 1. 功能测试
# - 正常启动录制
# - 浏览器已运行情况下启动录制
# - 初始化失败情况（模拟浏览器启动失败）
# - 网络请求失败情况（断网测试）

# 2. 性能测试
# - 测量从点击到界面切换的延迟（应 < 500ms）
# - 测量从点击到实际开始录制的总时间（应 < 5 秒）
# - 对比改造前后的时间差

# 3. 稳定性测试
# - 快速连续点击"Start Recording"（防止竞态条件）
# - 初始化过程中关闭浏览器
# - 初始化过程中刷新前端页面
```

### 4.5 总时间估算

| 阶段 | 时间 | 备注 |
|------|------|------|
| 后端改造 | 1-1.5h | 核心逻辑 |
| 前端改造 | 1h | UI + 轮询 |
| 额外优化 | 0.5h | 移除 sleep |
| 测试调优 | 1h | 关键环节 |
| **总计** | **3.5-4h** | 一个工作日内完成 |

---

## 5. 风险评估

### 5.1 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 竞态条件（重复调用） | 中 | 中 | 添加会话锁，检查 `_initialization_task` |
| 浏览器启动失败 | 低 | 高 | 完善错误处理，设置超时重试 |
| 前端轮询失败 | 低 | 中 | 添加重试机制，显示错误提示 |
| 初始化超时 | 中 | 中 | 设置合理超时（30s），显示错误 |

### 5.2 兼容性风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 旧前端版本 | 低 | 后端保持向后兼容（老接口仍可用） |
| 并发录制 | 低 | 当前不支持多录制，保持单例模式 |

### 5.3 回滚计划

**如果出现严重问题，可以快速回滚：**

1. **后端回滚**：
   - 恢复 `daemon.py` 的 `start_recording` 端点到同步模式
   - 保留新增的 `get_recording_status` 端点（不影响旧逻辑）

2. **前端回滚**：
   - 恢复 `handleStartRecording` 到原始版本
   - 移除轮询相关代码

3. **Git 操作**：
   ```bash
   # 如需回滚
   git revert <commit-hash>
   # 或
   git reset --hard <commit-before-changes>
   ```

---

## 6. 测试计划

### 6.1 单元测试（可选）

```python
# tests/test_cdp_recorder.py

import pytest
import asyncio
from src.clients.desktop_app.ami_daemon.services.cdp_recorder import CDPRecorder, RecordingStatus

@pytest.mark.asyncio
async def test_start_recording_async():
    """测试异步启动录制"""
    recorder = CDPRecorder(mock_storage, mock_browser)

    # 调用异步启动
    result = await recorder.start_recording_async(
        session_id="test_session",
        url="about:blank",
        user_id="test_user"
    )

    # 验证立即返回
    assert result["session_id"] == "test_session"
    assert result["status"] == "initializing"

    # 验证状态
    status = recorder.get_status()
    assert status["status"] == "initializing"

    # 等待初始化完成
    await asyncio.sleep(2)

    # 验证最终状态
    status = recorder.get_status()
    assert status["status"] in ["recording", "error"]
```

### 6.2 集成测试

**测试用例：**

| 用例 | 前置条件 | 操作 | 期望结果 |
|------|---------|------|---------|
| TC1: 正常启动 | 浏览器未运行 | 点击 Start Recording | 立即显示 initializing，5秒内变为 recording |
| TC2: 浏览器已运行 | 浏览器已启动 | 点击 Start Recording | 立即显示 initializing，2秒内变为 recording |
| TC3: 初始化失败 | 浏览器启动失败 | 点击 Start Recording | 30秒内显示错误信息 |
| TC4: 网络中断 | 前端运行中 | 断网后点击 | 显示连接失败，提示重试 |
| TC5: 快速重复点击 | - | 连续点击 3 次 | 只创建一个录制会话，其余忽略 |

### 6.3 性能测试

**基准指标：**

| 指标 | 当前 | 目标 | 测量方法 |
|------|------|------|---------|
| 点击到界面切换 | N/A | < 500ms | 前端性能工具 |
| 点击到实际录制 | 8-10s | < 5s | 后端日志时间戳 |
| API 响应时间 | 8-10s | < 100ms | Network 面板 |
| 初始化成功率 | ~95% | > 99% | 100 次测试统计 |

**测试脚本示例：**

```javascript
// performance_test.js

async function testRecordingStartup() {
  const startTime = performance.now();

  // 1. 调用启动 API
  const response = await fetch('http://localhost:52030/api/v1/recordings/start', {
    method: 'POST',
    body: JSON.stringify({...})
  });

  const apiResponseTime = performance.now() - startTime;
  console.log('API 响应时间:', apiResponseTime, 'ms');

  // 2. 轮询直到就绪
  const pollStart = performance.now();
  const result = await response.json();

  while (true) {
    const status = await fetch(`http://localhost:52030/api/v1/recordings/${result.session_id}/status`);
    const statusData = await status.json();

    if (statusData.status === 'recording') {
      const totalTime = performance.now() - startTime;
      console.log('总初始化时间:', totalTime, 'ms');
      break;
    }

    if (statusData.status === 'error') {
      console.error('初始化失败:', statusData.error);
      break;
    }

    await new Promise(r => setTimeout(r, 300));
  }
}
```

---

## 7. 上线计划

### 7.1 发布策略

**建议采用分阶段发布：**

1. **Alpha 测试（内部）**：
   - 开发团队自测 1-2 天
   - 验证基本功能和稳定性

2. **Beta 测试（小范围）**：
   - 选择 5-10 个活跃用户
   - 收集反馈，优化体验

3. **正式发布**：
   - 全量发布给所有用户
   - 监控错误日志，及时处理问题

### 7.2 监控指标

**发布后需监控的指标：**

| 指标 | 监控方式 | 告警阈值 |
|------|---------|---------|
| 录制启动成功率 | 后端日志统计 | < 95% |
| 平均初始化时间 | 后端日志时间戳 | > 10s |
| API 错误率 | 后端异常日志 | > 5% |
| 前端崩溃率 | 前端错误上报 | > 1% |

### 7.3 文档更新

**需要更新的文档：**

- [ ] API 文档：新增 `GET /api/v1/recordings/{session_id}/status` 说明
- [ ] 用户手册：更新录制启动流程截图（如有）
- [ ] 故障排查指南：新增初始化失败的排查步骤

---

## 8. 总结

### 8.1 改造收益

| 方面 | 改造前 | 改造后 | 提升 |
|------|--------|--------|------|
| 用户感知延迟 | 8-10s | < 0.5s | **95% ↓** |
| 实际初始化时间 | 8-10s | 4-5s | **50% ↓** |
| 用户体验 | 差（长时间无响应） | 好（即时反馈+进度） | **显著提升** |
| 代码质量 | 硬编码延迟，不可靠 | 事件驱动，健壮 | **显著提升** |

### 8.2 关键要点

✅ **立即反馈**：点击按钮后 < 500ms 切换到录制界面
✅ **进度可见**：显示初始化状态，用户知道发生了什么
✅ **实际加速**：移除硬编码等待，减少 4-5 秒延迟
✅ **向后兼容**：不破坏现有功能，可快速回滚
✅ **可扩展**：为未来优化（如预启动浏览器）留下空间

### 8.3 下一步优化方向

1. **浏览器预启动**：在用户进入 QuickStart 页面时预先启动浏览器
2. **断点续录**：支持初始化失败后重试，不需要重新点击
3. **并发录制**：支持多个独立的录制会话
4. **智能超时**：根据机器性能动态调整超时时间

---

**文档版本：** v1.0
**创建日期：** 2026-01-13
**作者：** Claude
**状态：** ✅ 待实施
