# Browser Session Manager Redesign V3

## 背景

当前浏览器管理存在的问题：
- 需要手动开关浏览器，操作繁琐
- 忘记关闭浏览器会导致后续任务失败
- Daemon 层和 Agent 层有两套独立的会话管理机制

## 设计目标

**方向 B：持久化会话** - 浏览器作为 Ami 的内置组件，与 Daemon 生命周期绑定。

用户视角：
- 启动 Ami → 浏览器自动启动（有窗口）
- 执行任务 → 浏览器自动配合
- 用户关闭浏览器 → Ami 检测到后自动重启
- 关闭 Ami → 浏览器可以关闭也可以保留（配置）
- **用户不需要关心浏览器的开关**

---

## 架构设计

### 核心决策：统一到 HybridBrowserSession

**V2 架构问题**：
- `BrowserSessionManager`（Daemon 层）和 `HybridBrowserSession`（Agent 层）各自独立
- 两者使用相同的底层技术（BrowserLauncher + Playwright CDP）但启动了两个浏览器实例
- Tab Group 功能完全失效，因为 `BrowserToolkit` 从未调用 `BrowserSessionManager`

**V3 方案**：
- **删除** `BrowserSessionManager` 类
- **升级** `HybridBrowserSession` 为统一的浏览器管理器
- **保留** `ExtensionBridge` 用于 Tab Group 通信

### 新架构

```
┌──────────────────────────────────────────────────────────────────┐
│                            Daemon                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              HybridBrowserSession (升级版)                  │  │
│  │              统一的浏览器管理 + Tab 管理                     │  │
│  │                                                             │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │  │
│  │  │ Browser Process │  │  ExtensionBridge │  │ Tab Groups │  │  │
│  │  │                 │  │                  │  │            │  │  │
│  │  │ - auto start    │  │ - WebSocket to   │  │ task-001   │  │  │
│  │  │ - auto restart  │  │   Ami Extension  │  │ task-002   │  │  │
│  │  │ - health check  │  │ - group/ungroup  │  │ ...        │  │  │
│  │  │ - CDP control   │  │                  │  │            │  │  │
│  │  │ - lock file     │  │                  │  │            │  │  │
│  │  │ - reconnect     │  │                  │  │            │  │  │
│  │  └─────────────────┘  └─────────────────┘  └────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                ↑                                  │
│  ┌─────────────────────────────┼───────────────────────────────┐ │
│  │        Agent Layer          │                               │ │
│  │  ┌──────────────────────────┴────────────────────────────┐  │ │
│  │  │  BrowserToolkit                                       │  │ │
│  │  │  - 通过 session_id 获取 HybridBrowserSession 单例     │  │ │
│  │  │  - 调用 Tab Group API                                 │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                                 ↕ WebSocket
┌──────────────────────────────────────────────────────────────────┐
│                         Chrome Browser                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                      Ami Extension                          │  │
│  │  - chrome.tabs.group() / chrome.tabGroups.update()         │  │
│  │  - 接收 Daemon 指令，执行 Tab Group 操作                     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐  │
│  │ Tab Group: Blue  │ │ Tab Group: Red   │ │ Tab Group: Green │  │
│  │ "task-001"       │ │ "task-002"       │ │ "task-003"       │  │
│  │ ┌────┐ ┌────┐   │ │ ┌────┐          │ │ ┌────┐ ┌────┐   │  │
│  │ │Tab1│ │Tab2│   │ │ │Tab3│          │ │ │Tab4│ │Tab5│   │  │
│  │ └────┘ └────┘   │ │ └────┘          │ │ └────┘ └────┘   │  │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 关键变更

| 组件 | V2 状态 | V3 状态 |
|------|---------|---------|
| `BrowserSessionManager` | 独立类，未被使用 | **删除** |
| `HybridBrowserSession` | 只管 Page，无生命周期管理 | **升级**：增加自动启动/重启/重连/Tab Group |
| `ExtensionBridge` | 已实现 | **保留**，被 HybridBrowserSession 使用 |
| `BrowserToolkit` | 直接用 HybridBrowserSession | **保持**，无需改动 |

---

## HybridBrowserSession 升级设计

### 新增功能

```python
class HybridBrowserSession:
    """统一的浏览器会话管理器

    V3 升级：
    - 自动启动/重启浏览器
    - Health check 监控
    - Lock 文件管理
    - 既有浏览器重连
    - Tab Group 管理（通过 ExtensionBridge）
    """

    # === 类级别：Daemon 生命周期管理 ===

    _daemon_session: ClassVar[Optional["HybridBrowserSession"]] = None
    _extension_bridge: ClassVar[Optional[ExtensionBridge]] = None
    _health_check_task: ClassVar[Optional[asyncio.Task]] = None
    _auto_restart: ClassVar[bool] = True

    @classmethod
    async def start_daemon_session(cls, config: dict = None) -> "HybridBrowserSession":
        """Daemon 启动时调用，初始化全局浏览器会话

        1. 检查既有浏览器，有则重连
        2. 无则启动新浏览器
        3. 启动 ExtensionBridge
        4. 启动 health check
        """

    @classmethod
    async def stop_daemon_session(cls, force: bool = False) -> None:
        """Daemon 退出时调用

        Args:
            force: True=强制关闭浏览器，False=根据配置决定
        """

    @classmethod
    def get_daemon_session(cls) -> Optional["HybridBrowserSession"]:
        """获取 Daemon 级别的浏览器会话"""
        return cls._daemon_session

    # === 实例级别：Tab Group 管理 ===

    _tab_groups: Dict[str, TabGroup]  # task_id -> TabGroup
    _color_index: int = 0

    TAB_GROUP_COLORS = ["blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange", "grey"]

    async def create_tab_group(self, task_id: str, title: str = None) -> TabGroup:
        """为任务创建 Tab Group"""

    async def get_tab_group(self, task_id: str) -> Optional[TabGroup]:
        """获取任务的 Tab Group"""

    async def close_tab_group(self, task_id: str) -> bool:
        """关闭任务的 Tab Group"""

    # === 实例级别：增强的 Tab 创建 ===

    async def create_tab_in_group(self, task_id: str, url: str = None) -> Tuple[str, Page]:
        """在指定任务的 Tab Group 中创建新 Tab

        1. 获取/创建 TabGroup
        2. 创建 Page
        3. 通知 Extension 加入 Chrome Tab Group

        Returns:
            (tab_id, Page)
        """
```

### 生命周期流程

```
Daemon 启动
    ↓
HybridBrowserSession.start_daemon_session()
    ├─ 启动 ExtensionBridge WebSocket Server
    ├─ 检查 lock 文件，是否有既有浏览器
    │   ├─ 有：connect_over_cdp() 重连
    │   │   └─ 标记旧 Tab Groups 为 orphan
    │   └─ 无：BrowserLauncher 启动新浏览器
    ├─ 写入 lock 文件
    ├─ 等待 Extension 连接
    └─ 启动 health check loop
        ↓
任务执行
    ├─ BrowserToolkit._get_session()
    │   └─ 返回 HybridBrowserSession 单例
    ├─ create_tab_in_group(task_id, url)
    │   ├─ 创建/获取 TabGroup
    │   ├─ context.new_page()
    │   └─ ExtensionBridge.create_tab_group() 或 add_to_group()
    └─ 任务结束
        └─ close_tab_group(task_id)
            ├─ 关闭所有 Page
            └─ ExtensionBridge.close_group()
        ↓
用户关闭浏览器
    ↓
health check 检测到
    ├─ 清理状态
    ├─ 延迟 1s
    └─ 重新启动浏览器
        ↓
Daemon 退出
    ↓
HybridBrowserSession.stop_daemon_session()
    ├─ 停止 health check
    ├─ 根据配置：关闭浏览器 或 仅断开连接
    ├─ 停止 ExtensionBridge
    └─ 删除/保留 lock 文件
```

### Lock 文件管理

```python
# 文件位置：{user_data_dir}/ami_browser.lock
# 内容格式：
{
    "pid": 12345,
    "cdp_url": "ws://127.0.0.1:9222/devtools/browser/xxx",
    "started_at": "2024-01-15T10:30:00"
}
```

检测既有浏览器：
1. 读取 lock 文件
2. 检查 PID 是否存活 (`psutil.Process(pid).is_running()`)
3. 检查 CDP 是否响应 (`http://127.0.0.1:{port}/json/version`)
4. 都通过 → 重连；否则 → 清理 lock 文件，启动新浏览器

### Health Check

```python
async def _health_check_loop(cls):
    """每 5 秒检查一次浏览器状态"""
    while True:
        await asyncio.sleep(5)

        if not cls._daemon_session:
            continue

        # 1. 检查进程
        if not cls._check_process_alive():
            logger.warning("Browser process died, restarting...")
            await cls._handle_browser_closed()
            continue

        # 2. 检查 CDP
        if not await cls._check_cdp_alive():
            logger.warning("CDP connection lost, reconnecting...")
            await cls._handle_connection_lost()
            continue
```

---

## Tab Group 管理

### TabGroup 数据类

```python
@dataclass
class TabGroup:
    """一个任务的 Tab 集合"""

    task_id: str
    title: str  # 默认 "task-{task_id[:8]}"
    color: str  # Chrome Tab Group 颜色
    chrome_group_id: Optional[int] = None  # Chrome 内部 Group ID
    created_at: datetime = field(default_factory=datetime.now)

    # tab_id -> Page
    tabs: Dict[str, Page] = field(default_factory=dict)
    current_tab_id: Optional[str] = None
    _tab_counter: int = 0

    def add_tab(self, page: Page) -> str:
        """添加 Tab，返回 tab_id"""
        self._tab_counter += 1
        tab_id = f"{self.task_id}-tab-{self._tab_counter:03d}"
        self.tabs[tab_id] = page
        if self.current_tab_id is None:
            self.current_tab_id = tab_id
        return tab_id

    @property
    def current_tab(self) -> Optional[Page]:
        if self.current_tab_id and self.current_tab_id in self.tabs:
            return self.tabs[self.current_tab_id]
        return None
```

### 颜色分配

```python
TAB_GROUP_COLORS = ["blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange", "grey"]

def _allocate_color(self) -> str:
    """循环分配颜色"""
    color = self.TAB_GROUP_COLORS[self._color_index % len(self.TAB_GROUP_COLORS)]
    self._color_index += 1
    return color
```

### 与 Extension 的协作

```
create_tab_in_group(task_id, url)
    │
    ├─ 1. 获取/创建 TabGroup
    │
    ├─ 2. context.new_page()
    │      └─ Playwright 创建 Tab
    │
    ├─ 3. page.goto(url) if url
    │
    ├─ 4. 等待 0.2s（让 Chrome 注册 Tab）
    │
    ├─ 5. ExtensionBridge.get_all_tabs()
    │      └─ 精确匹配 URL 找到 chrome_tab_id
    │
    └─ 6. 如果 TabGroup.chrome_group_id 为空：
           ExtensionBridge.create_tab_group([chrome_tab_id], title, color)
           └─ 保存 chrome_group_id
       否则：
           ExtensionBridge.add_to_group([chrome_tab_id], chrome_group_id)
```

---

## 集成点

### 1. Daemon 启动

```python
# daemon.py lifespan
async def lifespan(app):
    global extension_bridge

    # 启动 ExtensionBridge
    extension_bridge = ExtensionBridge()
    await extension_bridge.start()

    # 启动浏览器会话（传入 extension_bridge）
    await HybridBrowserSession.start_daemon_session(
        config=config,
        extension_bridge=extension_bridge
    )

    yield

    # 关闭
    await HybridBrowserSession.stop_daemon_session()
    await extension_bridge.stop()
```

### 2. 任务结束清理

```python
# quick_task_service.py
async def _execute_task_ami(self, task_id: str, ...):
    try:
        # ... 任务执行
    finally:
        # 清理该任务的 Tab Group
        session = HybridBrowserSession.get_daemon_session()
        if session:
            await session.close_tab_group(task_id)
```

### 3. BrowserToolkit（已优化：缓存 session 引用）

```python
# browser_toolkit.py
async def _get_session(self) -> HybridBrowserSession:
    # 热路径：缓存命中 + is_connected() 检查 → 直接返回
    s = self._session
    if s is not None and s._browser is not None and s._browser.is_connected():
        return s

    # 冷路径：通过 classmethod 工厂获取 singleton
    s = await HybridBrowserSession.get_session(
        session_id=self._session_id,
        headless=self._headless,
        user_data_dir=self._user_data_dir,
    )
    self._session = s
    return s
```

**关键改进**：
- 热路径零开销：1 次属性读取 + 1 次 `is_connected()` 检查，无对象创建、无 lock
- `HybridBrowserSession.get_session()` classmethod 先查 registry（带 lock），命中则直接返回
- 浏览器断开时 `is_connected()=False` → 自动重新解析
- `_restart_browser()` 开头设置 `self._session = None` 清除缓存
- `_build_action_result()` 解析一次 session 后传给所有内部 helper，一次 browser action 只调用 1 次 `_get_session()`

---

## 实现计划

### Phase 1: 清理旧代码
- [x] 确认 BrowserSessionManager 未被业务代码使用
- [ ] 删除 `services/browser_session_manager.py`
- [ ] 从 `daemon.py` 移除 BrowserSessionManager 相关代码
- [ ] 从 `services/__init__.py` 移除导出

### Phase 2: 升级 HybridBrowserSession
- [ ] 添加类级别的 daemon session 管理
  - `start_daemon_session()` / `stop_daemon_session()`
  - `_daemon_session` 类变量
- [ ] 添加 health check
  - `_health_check_loop()`
  - `_handle_browser_closed()`
- [ ] 添加 lock 文件管理
  - `_write_lock_file()` / `_remove_lock_file()`
  - `_find_existing_browser()`
- [ ] 添加重连逻辑
  - `_connect_to_existing()`

### Phase 3: Tab Group 集成
- [ ] 添加 TabGroup 数据类
- [ ] 添加 `_tab_groups` 管理
- [ ] 添加 `create_tab_group()` / `close_tab_group()`
- [ ] 添加 `create_tab_in_group()` 方法
- [ ] 集成 ExtensionBridge
  - 创建 Tab 后通知 Extension
  - 关闭 Group 时通知 Extension

### Phase 4: Daemon 集成
- [ ] 修改 `daemon.py` lifespan
  - 调用 `HybridBrowserSession.start_daemon_session()`
- [ ] 修改 `quick_task_service.py`
  - 任务结束时调用 `close_tab_group()`

### Phase 5: 测试与验证
- [ ] 更新 `scripts/browser_interactive_test.py`
- [ ] 验证：Daemon 启动 → 浏览器自动启动
- [ ] 验证：用户关闭浏览器 → 自动重启
- [ ] 验证：任务执行 → Tab Group 可视化分组
- [ ] 验证：任务结束 → Tab Group 自动关闭
- [ ] 验证：Daemon 重启 → 重连既有浏览器

---

## 配置选项

```yaml
# ~/.ami/config.yaml
browser:
  auto_start: true              # Daemon 启动时自动启动浏览器
  headless: false               # 是否无头模式
  auto_restart: true            # 浏览器被关闭时自动重启
  restart_delay: 1.0            # 重启延迟秒数
  close_on_daemon_exit: true    # Daemon 退出时关闭浏览器
  health_check_interval: 5      # 健康检查间隔秒数
```

---

## 设计决策

### 1. 为什么删除 BrowserSessionManager 而不是合并

- `HybridBrowserSession` 已经有成熟的单例机制、Tab 管理、snapshot、executor
- `BrowserSessionManager` 几乎没被使用，删除比合并风险更低
- 升级 `HybridBrowserSession` 保持了与 `BrowserToolkit` 的兼容性

### 2. Extension 是必需组件

- CDP 不支持 Tab Groups，必须通过 Extension
- 不考虑降级：Extension 未连接时报错而非静默失败
- Extension 文件随 Ami 分发，通过 `--load-extension` 自动加载

### 3. 重连后旧 Tab Groups 处理

标记为 orphan：
- 颜色改为 grey
- 标题前缀加 "[Orphan] "
- 只处理 "task-" 前缀的 Groups（Ami 创建的）
- 用户可手动关闭

### 4. 多 Ami 实例

禁止：
- Lock 文件 + health check 检测
- 第二个实例启动时报错

### 5. Lazy 模式 vs Health Check 模式

**决策：采用 Lazy 模式**

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| Health Check 模式 | 每 5 秒检查浏览器状态，关闭则立即重启 | 浏览器始终可用 | 浪费资源，不尊重用户意愿 |
| **Lazy 模式** | 只在 Agent 需要时检查并重启 | 尊重用户意愿，节省资源 | 首次操作可能稍慢 |

原因：
- 用户关闭浏览器 = 用户不想要浏览器
- 强制重启会让用户困惑
- 等 Agent 需要时再启动更合理

---

## 用户操作场景处理

浏览器同时被 Agent 和用户操作，需要处理各种边界情况：

### 场景总览

| # | 场景 | 处理方式 | 状态 |
|---|------|----------|------|
| 1 | Daemon 启动，无浏览器 | 启动新浏览器 | ✅ |
| 2 | Daemon 启动，浏览器已存在 | 通过 lock file 重连 | ✅ |
| 3 | 用户关闭浏览器进程 | Lazy 模式：下次操作时重启 | ✅ |
| 4 | CDP 连接断开 | 下次操作时重连 | ✅ |
| 5 | 任务执行中浏览器被关 | `_ensure_valid_page()` 重启浏览器 | ✅ |
| 6 | 多任务并发 | `_pages` 隔离，各任务独立 | ✅ |
| 7 | 任务结束清理 | `close_tab_group()` 关闭任务的所有 tabs | ✅ |
| 8 | Daemon 重启复用 | 通过 lock file 检测并重连 | ✅ |
| 9 | 浏览器首次启动失败 | 最多重试 3 次，指数退避 | ✅ |
| 10 | 用户手动开的 tabs | 只有 daemon session 能看到 | ⚠️ |
| 11 | 用户关闭 tabs（进程还在） | 自动清理 `_pages`，需要时创建新 page | ✅ |

### 场景详解

#### 场景 3 & 5：用户关闭浏览器

```
用户关闭浏览器
    ↓
(Lazy 模式：什么都不发生)
    ↓
Agent 调用 browser_visit_page()
    ↓
_get_session_with_page()
    ↓
_ensure_valid_page() 检测到 browser.is_connected() = False
    ↓
_restart_browser()
    ├─ 清理旧状态 (_page, _pages, _context, _browser, _playwright)
    ├─ 调用 _ensure_browser_inner() 重新启动
    └─ 更新 lock file
    ↓
继续执行 visit
```

#### 场景 11：用户关闭 tabs（浏览器进程还在）

```
用户关闭 tab
    ↓
Playwright 触发 page.on("close") 事件
    ↓
handle_page_close() 回调
    ├─ 从 _pages 中移除该 tab
    └─ 清理 _console_logs
    ↓
Agent 调用 browser_visit_page()
    ↓
_ensure_valid_page()
    ├─ 检测到 session._page.is_closed() = True
    ├─ 遍历 _pages 寻找其他有效 page
    │   ├─ 找到 → 切换到该 page
    │   └─ 没找到 → 创建新 page
    └─ 最多重试 3 次（处理用户快速关闭的情况）
```

#### 重试机制

```python
async def _ensure_valid_page(self, session) -> bool:
    max_retries = 3

    for attempt in range(max_retries):
        # 1. 检查浏览器是否有效
        if not browser.is_connected():
            await self._restart_browser(session)

        # 2. 检查当前 page 是否有效
        if session._page and not session._page.is_closed():
            return True

        # 3. 尝试切换到其他有效 page
        for tab_id, page in session._pages.items():
            if not page.is_closed():
                session._page = page
                return True

        # 4. 创建新 page
        new_page = await session._context.new_page()

        # 5. 验证新 page 没有被立即关闭
        if new_page.is_closed():
            continue  # 重试

        return True

    return False
```

### 关键实现

#### 1. Page 关闭事件处理

```python
async def _register_new_page(self, tab_id: str, new_page: Page) -> None:
    self._pages[tab_id] = new_page

    def handle_page_close(page: Page):
        # 自动清理已关闭的 page
        self._pages.pop(tab_id, None)
        self._console_logs.pop(tab_id, None)
        logger.debug(f"Tab {tab_id} closed and removed from registry")

    new_page.on(event="close", f=handle_page_close)
```

#### 2. 浏览器重启（Lazy 模式）

```python
async def _restart_browser(self, session: HybridBrowserSession) -> None:
    """只在需要时重启浏览器"""
    logger.info("Restarting browser...")

    # 清理旧状态
    session._page = None
    session._pages = {}
    session._context = None
    session._browser = None
    session._playwright = None

    # 重新初始化
    await session._ensure_browser_inner()

    # 更新 lock file
    if session is HybridBrowserSession._daemon_session:
        await HybridBrowserSession._write_lock_file(session)

    logger.info("Browser restarted successfully")
```

#### 3. Singleton 正确返回

```python
# HybridBrowserSession.get_session() classmethod (推荐入口)
@classmethod
async def get_session(cls, session_id, *, headless=False, user_data_dir=None, stealth=True):
    loop_id = str(id(asyncio.get_running_loop()))
    session_key = (loop_id, session_id)

    # 快路径：registry 命中 → 直接返回 singleton
    async with cls._instances_lock:
        if session_key in cls._instances:
            return cls._instances[session_key]

    # 慢路径：创建实例 → ensure_browser → 从 registry 取回 canonical singleton
    instance = cls(session_id=session_id, headless=headless, ...)
    await instance.ensure_browser()
    async with cls._instances_lock:
        return cls._instances.get(session_key, instance)
```

**关键点**：`get_session()` 最后从 registry 取回 canonical singleton 而非返回 throwaway instance，
保证 page/tab 变更全局可见。BrowserToolkit 缓存此 singleton 引用。

### Agent 友好错误消息

当浏览器或页面被用户关闭后，我们会自动恢复，但需要通知 Agent 状态已改变。

#### 设计决策

**问题**：浏览器操作时（如 click）页面被关闭，应该怎么办？
- 选项 A：静默恢复，继续执行操作
- 选项 B：通知 Agent，让它重新导航

**选择 B 的原因**：
1. 页面状态已丢失（表单数据、登录状态等）
2. Agent 可能需要重新执行前置步骤
3. 静默恢复可能导致 Agent 在错误的页面上操作

#### 实现机制

```python
class BrowserPageClosedError(Exception):
    """当浏览器页面被关闭并恢复时抛出。

    携带友好的消息，应该返回给 Agent。
    """
    pass

async def _ensure_valid_page(self, session) -> Tuple[bool, Optional[str]]:
    """返回 (成功, 恢复消息)"""

    # 如果浏览器被关闭并重启
    if browser_was_restarted:
        return (True, "The browser page was closed unexpectedly. "
                "A new page has been created. "
                "Please use browser_visit_page to navigate to your target URL.")

    # 如果当前 tab 被关闭，切换到其他 tab
    if page_was_recovered:
        return (True, "Your previous browser tab was closed. "
                "Switched to another existing tab. "
                "Please check if this is the correct page or use "
                "browser_visit_page to navigate to your target URL.")

    # 正常情况
    return (True, None)

async def _get_session_with_page(self) -> HybridBrowserSession:
    session = await self._get_session()
    success, recovery_message = await self._ensure_valid_page(session)

    if recovery_message:
        raise BrowserPageClosedError(recovery_message)

    return session
```

#### 工具方法处理

所有浏览器工具都会捕获 `BrowserPageClosedError` 并返回友好消息：

```python
async def browser_click(self, ref=None, ...):
    try:
        session = await self._get_session_with_page()
        # ... 执行操作
    except BrowserPageClosedError as e:
        # 返回友好消息给 Agent
        return str(e)
```

#### Agent 收到的消息示例

**场景：用户关闭浏览器进程**
```
The browser page was closed unexpectedly. A new page has been created.
Please use browser_visit_page to navigate to your target URL.
```

**场景：用户关闭当前 tab（浏览器还在）**
```
Your previous browser tab was closed. Switched to another existing tab.
Please check if this is the correct page or use browser_visit_page to
navigate to your target URL.
```

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `services/browser_session_manager.py` | **删除** |
| `services/__init__.py` | 移除 BrowserSessionManager 导出 |
| `daemon.py` | 移除 BrowserSessionManager，改用 HybridBrowserSession |
| `base_agent/tools/eigent_browser/browser_session.py` | **升级**：添加 daemon 管理、Tab Group |
| `services/quick_task_service.py` | 添加 close_tab_group 调用 |
| `services/extension_bridge.py` | **保留**，无改动 |
| `extensions/ami-browser-helper/*` | **保留**，无改动 |
