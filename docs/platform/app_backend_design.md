# App Backend 设计文档

**版本**: v3.0
**日期**: 2025-11-08
**状态**: Draft
**策略**: Desktop App Only (Tauri IPC + CDP Recording)

---

## 1. 架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop App (Tauri Process)                                │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Frontend (React/Vue)                                │    │
│  └────────────┬───────────────────────────────────────┘    │
│               │ invoke() - Tauri IPC                        │
│  ┌────────────┴───────────────────────────────────────┐    │
│  │ Rust Backend (Tauri Commands)                      │    │
│  │  #[tauri::command]                                  │    │
│  │  - start_recording()                                │    │
│  │  - stop_recording()                                 │    │
│  │  - execute_workflow()                               │    │
│  │  - get_workflow_status()                            │    │
│  └─────────────┬──────────────────────────────────────┘    │
└────────────────┼────────────────────────────────────────────┘
                 │ stdin/stdout (JSON-RPC)
┌────────────────┴────────────────────────────────────────────┐
│  App Backend (Python Daemon Process)                        │
│  ├── RPC Server (daemon.py)                                 │
│  │   └── Message Loop (read stdin → process → write stdout)│
│  ├── Global State (persistent across requests)              │
│  │   ├── BrowserSessionManager (global browser)            │
│  │   ├── Active Tasks (background workflow execution)      │
│  │   └── Recording Sessions                                │
│  ├── Services                                               │
│  │   ├── cdp_recorder.py                                   │
│  │   ├── storage_manager.py                                │
│  │   ├── cloud_client.py                                   │
│  │   └── workflow_executor.py                              │
│  └── CDP Binding                                            │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────────────────┐
│  Browser (Playwright + CDP - Global Session)                │
│  └── behavior_tracker.js (injected)                         │
└─────────────────────────────────────────────────────────────┘
```

**开发阶段设计（MVP）**：
- **常驻进程架构**：Python 进程随 Tauri 启动，退出时关闭
- **全局状态管理**：浏览器会话、异步任务在进程中持久化
- **JSON-RPC 通信**：通过 stdin/stdout 传递请求和响应
- **开发环境优先**：直接运行 `python daemon.py`，暂不考虑打包

---

## 2. 核心模块设计

### 2.1 CDPRecorder (cdp_recorder.py)

**职责**: 管理 CDP 浏览器生命周期，注入脚本，接收操作

**类设计**:

```python
from src.base_app.base_app.base_agent.tools.browser_use.user_behavior.monitor import SimpleUserBehaviorMonitor
from src.base_app.base_app.base_agent.tools.browser_session_manager import BrowserSessionManager

class CDPRecorder:
    """CDP 录制器 - 复用 monitor.py

    Browser Management:
    - Uses global browser session (shared across all tasks)
    - Browser stays open after recording stops
    - Browser only closes when App Backend shuts down
    """

    def __init__(self, config_service=None, browser_manager=None):
        self.config = config_service or ConfigService()
        self.browser_manager = browser_manager  # Global BrowserSessionManager
        self.browser_session = None
        self.monitor = None
        self.current_session_id = None
        self.operations = []  # 操作列表

    async def start_recording(self, url: str) -> Dict[str, Any]:
        """启动 CDP 浏览器并开始录制"""
        # 1. 创建 session_id
        self.current_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 2. 获取或创建全局浏览器会话（复用）
        if not self.browser_manager:
            self.browser_manager = BrowserSessionManager()

        self.browser_session = await self.browser_manager.get_or_create_session(
            session_name="global",  # 全局会话名称
            headless=False
        )

        # 3. 初始化 SimpleUserBehaviorMonitor（复用 monitor.py）
        self.operations = []
        self.monitor = SimpleUserBehaviorMonitor(operation_list=self.operations)

        # 4. 设置监控（CDP Binding + 脚本注入）
        await self.monitor.setup_monitoring(self.browser_session)

        # 5. 导航到起始 URL
        await self.browser_session.page.goto(url)

        return {
            "session_id": self.current_session_id,
            "status": "recording"
        }

    async def stop_recording(self) -> Dict[str, Any]:
        """停止录制，保存文件，但保持浏览器打开"""
        if not self.current_session_id:
            raise ValueError("No active recording session")

        # 1. 停止监控
        if self.monitor:
            self.monitor._is_monitoring = False

        # 2. 保存 operations.json
        storage = StorageManager(self.config)
        file_path = await storage.save_recording(
            session_id=self.current_session_id,
            operations=self.operations
        )

        # 3. 不关闭浏览器（保持打开，供后续任务复用）
        # Note: Browser session remains open in browser_manager

        result = {
            "session_id": self.current_session_id,
            "operations_count": len(self.operations),
            "local_file_path": file_path
        }

        # 4. 清理录制状态（但不清理浏览器）
        self.current_session_id = None
        self.operations = []
        self.monitor = None
        # self.browser_session 保留，不设为 None

        return result
```

**关键实现细节**:

1. **复用 SimpleUserBehaviorMonitor**:
   - 自动设置 CDP Binding
   - 自动注入 behavior_tracker.js
   - 自动处理 `window.reportUserBehavior()` 调用

2. **CDP Binding 工作原理**:
   ```python
   # monitor.py 内部实现
   await cdp_session.cdp_client.send.Runtime.addBinding(
       params={'name': 'reportUserBehavior'}
   )

   async def handle_runtime_binding(event, session_id=None):
       if event.get('name') == 'reportUserBehavior':
           payload = event.get('payload')
           operation = json.loads(payload)
           self.operation_list.append(operation)  # 自动追加到列表
   ```

---

### 2.2 StorageManager (storage_manager.py)

**职责**: 管理本地文件系统

**类设计**:

```python
class StorageManager:
    """本地存储管理器"""

    def __init__(self, config_service):
        self.base_path = Path(config_service.get("storage.base_path", "~/.ami")).expanduser()
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必要的目录存在"""
        (self.base_path / "recordings").mkdir(parents=True, exist_ok=True)
        (self.base_path / "users").mkdir(parents=True, exist_ok=True)
        (self.base_path / "logs").mkdir(parents=True, exist_ok=True)

    async def save_recording(self, session_id: str, operations: List[Dict]) -> str:
        """保存录制数据"""
        recording_dir = self.base_path / "recordings" / session_id
        recording_dir.mkdir(parents=True, exist_ok=True)

        file_path = recording_dir / "operations.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
                "operations": operations
            }, f, ensure_ascii=False, indent=2)

        return str(file_path)

    async def save_workflow(self, workflow_name: str, workflow_yaml: str, user_id: str = "default") -> str:
        """保存 workflow YAML"""
        workflow_dir = self.base_path / "users" / user_id / "workflows" / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        file_path = workflow_dir / "workflow.yaml"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        return str(file_path)

    async def load_workflow(self, workflow_name: str, user_id: str = "default") -> str:
        """加载 workflow YAML"""
        file_path = self.base_path / "users" / user_id / "workflows" / workflow_name / "workflow.yaml"

        if not file_path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_name}")

        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def list_workflows(self, user_id: str = "default") -> List[Dict[str, str]]:
        """列出所有 workflows"""
        workflows_dir = self.base_path / "users" / user_id / "workflows"

        if not workflows_dir.exists():
            return []

        workflows = []
        for workflow_dir in workflows_dir.iterdir():
            if workflow_dir.is_dir():
                yaml_path = workflow_dir / "workflow.yaml"
                if yaml_path.exists():
                    workflows.append({
                        "name": workflow_dir.name,
                        "created_at": datetime.fromtimestamp(yaml_path.stat().st_ctime).isoformat()
                    })

        return workflows
```

---

### 2.3 CloudClient (cloud_client.py)

**职责**: 封装 Cloud Backend API 调用

**设计说明**:
- Cloud Backend API 的调用方式灵活，可根据现有架构选择最方便的实现
- 可选方案：同步等待、异步轮询、WebSocket 推送等
- 以下是参考实现，具体实现时根据 Cloud Backend 的实际 API 设计调整

**类设计**:

```python
import httpx

class CloudClient:
    """Cloud Backend API 客户端"""

    def __init__(self, config_service):
        self.api_url = config_service.get("cloud.api_url", "https://api.ami.com")
        self.timeout = config_service.get("cloud.timeout", 120)
        self.session = httpx.AsyncClient(timeout=self.timeout)

    async def upload_recording(self, operations: List[Dict]) -> str:
        """Upload recording to Cloud Backend

        API Reference: architecture.md - Section 2.2 (Upload Phase)
        """
        url = f"{self.api_url}/api/recordings/upload"

        payload = {
            "operations": operations,
            "timestamp": datetime.now().isoformat()
        }

        response = await self.session.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        return data.get("recording_id")

    async def generate_metaflow(self, recording_id: str, title: str, description: str) -> str:
        """Generate MetaFlow via Cloud Backend

        Step 1 of workflow generation process:
        - Intent Extraction (LLM)
        - Intent Graph update
        - MetaFlow generation (LLM)

        Implementation Note:
        - This is a separate API endpoint
        - May be a long-running operation
        - Calling method is flexible (sync/async/polling)
        """
        url = f"{self.api_url}/api/recordings/{recording_id}/generate-metaflow"

        payload = {
            "recording_id": recording_id,
            "title": title,
            "description": description
        }

        response = await self.session.post(url, json=payload, timeout=120)
        response.raise_for_status()

        data = response.json()
        return data.get("metaflow_id")

    async def generate_workflow(self, metaflow_id: str) -> str:
        """Generate Workflow YAML from MetaFlow via Cloud Backend

        Step 2 of workflow generation process:
        - Workflow YAML generation (LLM)

        Implementation Note:
        - This is a separate API endpoint from MetaFlow generation
        - Takes metaflow_id as input
        - Returns workflow_name
        """
        url = f"{self.api_url}/api/metaflows/{metaflow_id}/generate-workflow"

        response = await self.session.post(url, json=payload, timeout=120)
        response.raise_for_status()

        data = response.json()
        return data.get("workflow_name")

    async def download_workflow(self, workflow_name: str) -> str:
        """Download Workflow YAML from Cloud Backend"""
        url = f"{self.api_url}/api/workflows/{workflow_name}"

        response = await self.session.get(url)
        response.raise_for_status()

        return response.text
```

---

### 2.4 WorkflowExecutor (workflow_executor.py)

**职责**: 执行 workflow，管理执行状态

**类设计**:

```python
from src.base_app.base_app.base_agent.core.base_agent import BaseAgent
from src.base_app.base_app.server.core.config_service import ConfigService as BaseAppConfigService

class WorkflowExecutor:
    """Workflow 执行器 - 复用 base_app/BaseAgent

    Browser Management:
    - Uses global browser session (shared with recorder)
    - Workflow name forced to "global" to reuse browser
    - Browser stays open after workflow execution
    """

    def __init__(self, config_service, storage_manager, browser_manager=None):
        self.config = config_service
        self.storage = storage_manager
        self.browser_manager = browser_manager  # Global BrowserSessionManager
        self.active_tasks = {}  # task_id -> TaskInfo

    async def execute(self, workflow_name: str, user_id: str = "default") -> Dict[str, Any]:
        """执行 Workflow（异步）"""
        # 1. 生成 task_id
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 2. 加载 workflow YAML
        workflow_yaml = await self.storage.load_workflow(workflow_name, user_id)
        workflow_dict = yaml.safe_load(workflow_yaml)

        # 3. 强制设置 workflow name 为 "global" 以复用浏览器
        workflow_dict["name"] = "global"

        # 4. 创建 BaseAgent 实例（复用 base_app）
        base_config = BaseAppConfigService()
        agent = BaseAgent(config_service=base_config, user_id=user_id)

        # 5. 确保使用全局浏览器管理器
        if self.browser_manager:
            # 将全局浏览器管理器注入到 agent
            agent.browser_manager = self.browser_manager

        # 6. 创建任务信息
        task_info = TaskInfo(
            task_id=task_id,
            workflow_name=workflow_name,
            status="running",
            agent=agent,
            start_time=datetime.now()
        )
        self.active_tasks[task_id] = task_info

        # 7. 异步执行（不阻塞）
        asyncio.create_task(self._execute_task(task_info, workflow_dict, user_id))

        return {"task_id": task_id, "status": "running"}

    async def _execute_task(self, task_info: TaskInfo, workflow_dict: Dict, user_id: str):
        """内部执行任务（异步）"""
        try:
            # 执行 workflow
            result = await task_info.agent.run_workflow(
                workflow=workflow_dict,
                context={"user_id": user_id}
            )

            # 更新状态
            task_info.status = "success"
            task_info.result = result
            task_info.end_time = datetime.now()

            # 保存结果
            await self.storage.save_execution_result(
                workflow_name=task_info.workflow_name,
                task_id=task_info.task_id,
                result={
                    "status": "success",
                    "final_output": result.final_result,
                    "duration": (task_info.end_time - task_info.start_time).total_seconds()
                },
                user_id=user_id
            )

        except Exception as e:
            task_info.status = "failed"
            task_info.error = str(e)
            task_info.end_time = datetime.now()

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态（同步）"""
        task_info = self.active_tasks.get(task_id)

        if not task_info:
            raise ValueError(f"Task not found: {task_id}")

        return {
            "task_id": task_id,
            "status": task_info.status,
            "progress": 100 if task_info.status == "success" else 50,
            "current_step": task_info.current_step or ""
        }

    def get_result(self, task_id: str) -> Dict[str, Any]:
        """获取任务结果（同步）"""
        task_info = self.active_tasks.get(task_id)

        if not task_info:
            raise ValueError(f"Task not found: {task_id}")

        if task_info.status != "success":
            raise ValueError(f"Task not completed: {task_info.status}")

        return {
            "status": "success",
            "final_output": task_info.result.final_result,
            "duration": (task_info.end_time - task_info.start_time).total_seconds()
        }


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    workflow_name: str
    status: str
    agent: Any
    start_time: datetime
    end_time: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    current_step: Optional[str] = None
```

---

## 3. Tauri 集成设计

### 3.1 Rust Tauri Commands (Daemon)

**文件**: `src/clients/desktop_app/src-tauri/src/main.rs`

```rust
use tauri::State;
use serde_json::{Value, json};
use std::sync::Mutex;

mod python_daemon;
use python_daemon::PythonDaemon;

// Global state for Python daemon
struct AppState {
    python_daemon: Mutex<PythonDaemon>,
}

#[tauri::command]
async fn start_recording(state: State<'_, AppState>, url: String) -> Result<Value, String> {
    let mut daemon = state.python_daemon.lock().unwrap();
    daemon.call_function("start_recording", json!({"url": url}))
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn stop_recording(state: State<'_, AppState>) -> Result<Value, String> {
    let mut daemon = state.python_daemon.lock().unwrap();
    daemon.call_function("stop_recording", json!({}))
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn execute_workflow(state: State<'_, AppState>, workflow_name: String) -> Result<Value, String> {
    let mut daemon = state.python_daemon.lock().unwrap();
    daemon.call_function("execute_workflow", json!({"workflow_name": workflow_name}))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_workflow_status(state: State<'_, AppState>, task_id: String) -> Result<Value, String> {
    let mut daemon = state.python_daemon.lock().unwrap();
    daemon.call_function("get_workflow_status", json!({"task_id": task_id}))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn list_workflows(state: State<'_, AppState>) -> Result<Value, String> {
    let mut daemon = state.python_daemon.lock().unwrap();
    daemon.call_function("list_workflows", json!({}))
        .map_err(|e| e.to_string())
}

fn main() {
    // Start Python daemon
    let mut daemon = PythonDaemon::new();
    daemon.start().expect("Failed to start Python daemon");

    tauri::Builder::default()
        .manage(AppState {
            python_daemon: Mutex::new(daemon),
        })
        .invoke_handler(tauri::generate_handler![
            start_recording,
            stop_recording,
            execute_workflow,
            get_workflow_status,
            list_workflows
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### 3.2 Python Daemon Bridge

**文件**: `src/clients/desktop_app/src-tauri/src/python_daemon.rs`

```rust
use std::process::{Command, Child, Stdio, ChildStdin, ChildStdout};
use std::io::{Write, BufRead, BufReader};
use serde_json::{Value, json};
use std::sync::Mutex;

pub struct PythonDaemon {
    process: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout: Option<BufReader<ChildStdout>>,
    request_id: Mutex<u64>,
}

impl PythonDaemon {
    pub fn new() -> Self {
        Self {
            process: None,
            stdin: None,
            stdout: None,
            request_id: Mutex::new(0),
        }
    }

    /// Start Python daemon process
    pub fn start(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        // Start Python daemon (development environment)
        let mut child = Command::new("python3")
            .arg("src/app_backend/daemon.py")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())  // Show errors in console
            .spawn()?;

        let stdin = child.stdin.take().unwrap();
        let stdout = BufReader::new(child.stdout.take().unwrap());

        self.process = Some(child);
        self.stdin = Some(stdin);
        self.stdout = Some(stdout);

        Ok(())
    }

    /// Call Python function via JSON-RPC
    pub fn call_function(&mut self, method: &str, params: Value) -> Result<Value, Box<dyn std::error::Error>> {
        // Generate request ID
        let id = {
            let mut counter = self.request_id.lock().unwrap();
            *counter += 1;
            *counter
        };

        // Build JSON-RPC request
        let request = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params
        });

        // Send request
        let stdin = self.stdin.as_mut().ok_or("Daemon not started")?;
        let request_str = serde_json::to_string(&request)?;
        writeln!(stdin, "{}", request_str)?;
        stdin.flush()?;

        // Read response
        let stdout = self.stdout.as_mut().ok_or("Daemon not started")?;
        let mut response_line = String::new();
        stdout.read_line(&mut response_line)?;

        // Parse JSON-RPC response
        let response: Value = serde_json::from_str(&response_line)?;

        // Check for error
        if let Some(error) = response.get("error") {
            return Err(format!("Python error: {}", error).into());
        }

        // Return result
        Ok(response.get("result").unwrap_or(&Value::Null).clone())
    }

    /// Stop daemon process
    pub fn stop(&mut self) {
        if let Some(mut process) = self.process.take() {
            let _ = process.kill();
        }
    }
}

impl Drop for PythonDaemon {
    fn drop(&mut self) {
        self.stop();
    }
}
```

### 3.3 Python Daemon 入口

**文件**: `src/app_backend/daemon.py`

```python
#!/usr/bin/env python3
"""
Daemon process for App Backend
Runs as a persistent process, communicates via JSON-RPC over stdin/stdout
"""
import sys
import json
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.app_backend.services.cdp_recorder import CDPRecorder
from src.app_backend.services.workflow_executor import WorkflowExecutor
from src.app_backend.services.storage_manager import StorageManager
from src.app_backend.core.config_service import ConfigService
from src.base_app.base_app.base_agent.tools.browser_session_manager import BrowserSessionManager

# Global instances (initialized once, persistent across requests)
config = ConfigService()
browser_manager = BrowserSessionManager()
recorder = CDPRecorder(config, browser_manager=browser_manager)
storage = StorageManager(config)
executor = WorkflowExecutor(config, storage, browser_manager=browser_manager)

# Global event loop for async operations
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def handle_request(method: str, params: dict) -> dict:
    """Handle JSON-RPC request"""
    try:
        if method == "start_recording":
            url = params.get("url", "")
            result = loop.run_until_complete(recorder.start_recording(url))

        elif method == "stop_recording":
            result = loop.run_until_complete(recorder.stop_recording())

        elif method == "execute_workflow":
            workflow_name = params.get("workflow_name", "")
            result = loop.run_until_complete(executor.execute(workflow_name))

        elif method == "get_workflow_status":
            task_id = params.get("task_id", "")
            result = executor.get_status(task_id)

        elif method == "get_workflow_result":
            task_id = params.get("task_id", "")
            result = executor.get_result(task_id)

        elif method == "list_workflows":
            result = {"workflows": storage.list_workflows()}

        else:
            return {"error": f"Unknown method: {method}"}

        return result

    except Exception as e:
        return {"error": str(e)}

def main():
    """Main daemon loop - read JSON-RPC requests from stdin"""
    sys.stderr.write("App Backend daemon started\n")
    sys.stderr.flush()

    for line in sys.stdin:
        try:
            # Parse JSON-RPC request
            request = json.loads(line.strip())
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # Handle request
            result = handle_request(method, params)

            # Build JSON-RPC response
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }

            # Send response to stdout
            print(json.dumps(response), flush=True)

        except Exception as e:
            # Return error response
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if "request" in locals() else None,
                "error": {"message": str(e)}
            }
            print(json.dumps(error_response), flush=True)

if __name__ == "__main__":
    main()
```

---

## 4. 目录结构

```
src/app_backend/                 # Python Backend (daemon process)
├── __init__.py
├── daemon.py                    # Daemon entry point (JSON-RPC server)
├── config/
│   └── app-backend.yaml
├── core/
│   └── config_service.py
├── services/
│   ├── cdp_recorder.py          # CDP recording (reuses monitor.py)
│   ├── storage_manager.py       # Local storage
│   ├── cloud_client.py          # Cloud API client (sync calls, no timeout)
│   └── workflow_executor.py     # Workflow executor (reuses base_app)
├── static/
│   └── recorder.js              # behavior_tracker.js (reused)
└── requirements.txt

src/clients/desktop_app/
├── src/                         # Frontend (React/Vue)
│   ├── App.jsx
│   ├── components/
│   │   ├── RecordingPanel.jsx
│   │   ├── WorkflowList.jsx
│   │   └── ExecutionMonitor.jsx
│   └── main.jsx
├── src-tauri/                   # Rust Backend
│   ├── src/
│   │   ├── main.rs              # Tauri Commands
│   │   └── python_daemon.rs     # Daemon process manager
│   ├── Cargo.toml               # Dependencies: tauri, serde_json
│   └── tauri.conf.json
└── package.json
```

---

## 5. 数据流设计

### 5.1 录制流程

```
1. Frontend: 用户点击"开始录制"
   ↓ invoke('start_recording', {url: "..."})
2. Rust Backend: 接收 Tauri Command
   ↓ daemon.call_function("start_recording", {"url": "..."})
3. JSON-RPC: 通过 stdin 发送请求到 Python daemon
   ↓ {"jsonrpc": "2.0", "id": 1, "method": "start_recording", "params": {"url": "..."}}
4. Python Daemon: 接收请求
   ↓ handle_request("start_recording", {"url": "..."})
   ↓ await recorder.start_recording(url)
5. CDPRecorder:
   ↓ 从全局 browser_manager 获取或创建浏览器 (session_name="global")
   ↓ 浏览器已存在则复用，首次启动则创建
   ↓ SimpleUserBehaviorMonitor.setup_monitoring()
   ↓ 注入 behavior_tracker.js
   ↓ 设置 CDP Binding
   ↓ goto(url)
6. 用户操作:
   ↓ behavior_tracker.js 捕获事件
   ↓ window.reportUserBehavior(JSON.stringify({...}))
   ↓ CDP Binding → handle_runtime_binding()
   ↓ operations.append(operation)
7. Frontend: 用户点击"停止录制"
   ↓ invoke('stop_recording')
8. Python Daemon: 停止监控，保存文件，保持浏览器打开
   ↓ 返回: {"session_id": "...", "operations_count": 42, "local_file_path": "..."}
   ↓ 浏览器继续运行在 daemon 进程中，等待下次任务
9. JSON-RPC 响应返回到 Rust → Frontend
```

### 5.2 执行流程

```
1. Frontend: 用户点击"执行"
   ↓ invoke('execute_workflow', {workflow_name})
2. Python: 加载 workflow，强制设置 name="global"
   ↓ 创建 BaseAgent，注入全局浏览器管理器
   ↓ BaseAgent 复用已打开的浏览器实例
   ↓ 异步执行
   ↓ 返回: {task_id, status: "running"}
3. Frontend: 轮询查询状态
   ↓ setInterval(() => {
       invoke('get_workflow_status', {task_id})
     }, 2000)
4. Python: 返回实时状态
   ↓ {status: "running", progress: 50}
5. 执行完成:
   ↓ Frontend 最后一次查询
   ↓ {status: "success"}
   ↓ invoke('get_workflow_result', {task_id})
   ↓ 显示结果
   ↓ 浏览器继续运行，等待下次任务
```

---

## 6. 配置

### 6.1 Rust Dependencies

**文件**: `src/clients/desktop_app/src-tauri/Cargo.toml`

```toml
[package]
name = "ami-desktop"
version = "0.1.0"
edition = "2021"

[dependencies]
tauri = { version = "1.5", features = ["shell-open"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

[build-dependencies]
tauri-build = { version = "1.5", features = [] }
```

### 6.2 Python Configuration

**文件**: `src/app_backend/config/app-backend.yaml`

```yaml
storage:
  base_path: ~/.ami

cloud:
  api_url: https://api.ami.com
  # Note: All Cloud Backend APIs are sync, no timeout limit

browser:
  headless: false
  timeout: 30

logging:
  level: INFO
  file: ~/.ami/logs/app-backend.log
```

---

## 7. 错误处理

### 7.1 Python 错误

```python
try:
    result = await recorder.start_recording(url)
except Exception as e:
    return {"error": str(e), "type": "RecordingError"}
```

### 7.2 Rust 错误

```rust
#[tauri::command]
async fn start_recording(url: String) -> Result<Value, String> {
    executor.call_python_function("start_recording", vec![url])
        .map_err(|e| format!("Python error: {}", e))
}
```

### 7.3 Frontend 错误

```javascript
try {
    const result = await invoke('start_recording', { url });
    // ...
} catch (error) {
    console.error('Recording failed:', error);
    alert(`录制失败: ${error}`);
}
```

---

## 8. 性能优化与开发便利性

### 8.1 常驻进程优势

- **全局状态持久化**:
  - 浏览器会话在进程中持久化，无需重复启动
  - 异步任务在后台运行，不阻塞请求
  - 一次启动，所有任务复用

- **性能提升**:
  - 无进程启动开销（仅首次启动 daemon）
  - JSON-RPC 通信延迟 < 10ms
  - 浏览器复用节省 5-10 秒/任务

- **开发便利**:
  - 可独立运行 `python daemon.py` 测试
  - 修改代码后重启 daemon 即可
  - 日志统一输出到 stderr

### 8.2 浏览器复用

- 全局 BrowserSessionManager 单例在 daemon 进程中
- 所有录制和执行任务共享同一个浏览器实例（session_name="global"）
- 浏览器随 daemon 启动创建，随 daemon 关闭销毁
- 避免重复启动浏览器，显著提升性能

### 8.3 Cloud Backend API 调用

- 所有 Cloud Backend API 假定为**同步接口**
- **无超时限制**：Rust 等待 Python 返回，Python 等待 Cloud API 返回
- MetaFlow 生成、Workflow 生成可能耗时 30-60 秒，但不影响架构
- Python daemon 进程不会因为长时间等待而被杀掉

---

## 9. 安全考虑

- **本地限制**: Python 可执行文件随 Tauri 打包，仅供本地调用
- **数据隔离**: 录制数据仅保存在 `~/.ami/`
- **无网络暴露**: 不启动任何网络服务
- **参数验证**: Rust 层验证所有传递给 Python 的参数

---

## 10. 开发与测试

### 10.1 Python Daemon 独立测试

```bash
# 启动 daemon（开发模式）
cd src/app_backend
python daemon.py

# 在另一个终端测试 JSON-RPC 调用
echo '{"jsonrpc":"2.0","id":1,"method":"list_workflows","params":{}}' | python daemon.py
echo '{"jsonrpc":"2.0","id":2,"method":"start_recording","params":{"url":"https://example.com"}}' | python daemon.py
```

### 10.2 完整流程测试

```bash
# 运行 Tauri 开发模式（自动启动 Python daemon）
cd src/clients/desktop_app
npm run tauri dev

# Tauri 启动时会执行 python3 src/app_backend/daemon.py
```

### 10.3 调试技巧

**Python 端调试**：
- daemon.py 的日志输出到 stderr，可在 Tauri console 看到
- 添加 `sys.stderr.write(f"Debug: {variable}\n")` 打印调试信息

**Rust 端调试**：
- 检查 JSON-RPC 请求/响应格式
- 使用 `eprintln!("Request: {:?}", request)` 打印请求

---

**文档版本**: v3.0 (Tauri IPC)
**最后更新**: 2025-11-08
**审核状态**: Draft
**实施状态**: Ready for Implementation
