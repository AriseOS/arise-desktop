# 简化版用户行为监控设计方案

## 概述

本方案专注于监控用户的真实浏览器行为（点击、输入、导航等），并在后台实时打印这些行为。不涉及数据存储和复杂分析，保持最简单的实现。

## 设计原则

- **最小化实现** - 只监控和打印，无存储和分析
- **零侵入性** - 不修改Browser-Use库源码
- **实时打印** - 用户行为发生时立即在后台输出
- **装饰器模式** - 通过包装方式增强功能

## 简化架构

### 📁 目录结构

```
📦 base_app/base_app/base_agent/tools/browser_use/
├── 📂 user_behavior/
│   ├── 📄 __init__.py                   # 模块初始化
│   ├── 📄 monitor.py                    # 简化的监控器
│   └── 📄 behavior_tracker.js           # JavaScript监控脚本
├── 📄 enhanced_browser_use.py           # 简化的包装器
└── 📄 browser_use.py                    # 现有工具 (最小修改)
```

### 🔄 数据流程

```
用户在浏览器中操作
    ↓ (DOM原生事件)
JavaScript监控脚本捕获
    ↓ (CDP Runtime.addBinding)
Python监控器接收
    ↓ (控制台打印)
后台实时输出用户行为
```

### 📋 Browser-Use CDP API 使用方式

**正确的API调用模式**：
```python
# 1. 添加Runtime绑定
await cdp_session.cdp_client.send.Runtime.addBinding(
    params={'name': 'functionName'},
    session_id=cdp_session.session_id
)

# 2. 注册事件处理器 (注意：需要两个参数)
def event_handler(event, session_id=None):
    # 处理事件数据
    pass

cdp_session.cdp_client.register.Runtime.bindingCalled(event_handler)

# 3. 执行JavaScript
await cdp_session.cdp_client.send.Runtime.evaluate(
    params={
        'expression': 'JavaScript代码',
        'returnByValue': True
    },
    session_id=cdp_session.session_id
)
```

**关键要点**：
- 所有CDP调用都通过 `cdp_session.cdp_client.send.Domain.method()` 
- 事件注册通过 `cdp_session.cdp_client.register.Domain.event(handler)`
- 事件处理器必须接受两个参数：`(event, session_id=None)`
- 需要传递 `session_id` 参数给CDP调用

## 核心模块设计

### 1. 📄 `user_behavior/monitor.py` - 简化监控器

```python
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class SimpleUserBehaviorMonitor:
    """简化的用户行为监控器 - 只监控和打印"""
    
    def __init__(self):
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._is_monitoring = False
        
    async def setup_monitoring(self, browser_session) -> None:
        """设置用户行为监控"""
        if self._is_monitoring:
            return
            
        try:
            # 获取CDP会话
            cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
            
            # 1. 设置JavaScript到Python的绑定
            await cdp_session.cdp_client.send.Runtime.addBinding(
                params={'name': 'reportUserBehavior'},
                session_id=cdp_session.session_id
            )
            
            # 2. 注册绑定事件处理器
            await self._setup_binding_handler(cdp_session)
            
            # 3. 注入监控脚本
            script = self._get_monitoring_script()
            await browser_session._cdp_add_init_script(script)
            
            self._is_monitoring = True
            logger.info(f"🔍 User behavior monitoring started for {self.session_id}")
            print(f"\n🎯 用户行为监控已启动 - 会话ID: {self.session_id}")
            print("=" * 60)
            
        except Exception as e:
            logger.error(f"Failed to setup user behavior monitoring: {e}")
            raise
    
    async def _setup_binding_handler(self, cdp_session) -> None:
        """设置绑定事件处理器"""
        async def handle_runtime_binding(event):
            if event.get('name') == 'reportUserBehavior':
                payload = event.get('payload', '')
                await self._print_behavior_data(payload)
        
        # 注册Runtime.bindingCalled事件监听器
        cdp_session.cdp_client.register.Runtime.bindingCalled(handle_runtime_binding)
    
    async def _print_behavior_data(self, payload: str) -> None:
        """处理并打印用户行为数据"""
        try:
            data = json.loads(payload)
            
            # 格式化时间戳
            timestamp = datetime.fromtimestamp(data['timestamp'] / 1000)
            time_str = timestamp.strftime('%H:%M:%S.%f')[:-3]  # 精确到毫秒
            
            # 获取基本信息
            behavior_type = data['type'].upper()
            url = data['url']
            page_title = data.get('page_title', 'Unknown')
            
            # 打印基本行为信息
            print(f"[{time_str}] 🔥 {behavior_type}")
            print(f"  📍 页面: {page_title}")
            print(f"  🌐 URL: {url}")
            
            # 根据行为类型打印详细信息
            if data['type'] == 'click':
                self._print_click_details(data)
            elif data['type'] == 'input':
                self._print_input_details(data)
            elif data['type'] == 'navigate':
                self._print_navigate_details(data)
            elif data['type'] == 'form_submit':
                self._print_form_details(data)
            elif data['type'] == 'scroll':
                self._print_scroll_details(data)
            
            print("-" * 60)
            
        except Exception as e:
            logger.error(f"Failed to process behavior data: {e}")
            print(f"❌ 处理用户行为数据失败: {e}")
    
    def _print_click_details(self, data):
        """打印点击行为详情"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  🖱️  元素: {element.get('tagName', 'UNKNOWN')}")
        if element.get('id'):
            print(f"     ID: {element['id']}")
        if element.get('className'):
            print(f"     Class: {element['className']}")
        if element.get('textContent'):
            print(f"     文本: {element['textContent'][:50]}...")
        if element.get('href'):
            print(f"     链接: {element['href']}")
        
        # 打印点击位置
        if 'clientX' in user_data and 'clientY' in user_data:
            print(f"  📍 位置: ({user_data['clientX']}, {user_data['clientY']})")
        
        # 打印修饰键
        modifiers = []
        if user_data.get('ctrlKey'): modifiers.append('Ctrl')
        if user_data.get('shiftKey'): modifiers.append('Shift') 
        if user_data.get('altKey'): modifiers.append('Alt')
        if modifiers:
            print(f"  ⌨️  修饰键: {'+'.join(modifiers)}")
    
    def _print_input_details(self, data):
        """打印输入行为详情"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  ⌨️  输入框: {element.get('tagName', 'UNKNOWN')}")
        if element.get('id'):
            print(f"     ID: {element['id']}")
        if element.get('name'):
            print(f"     Name: {element['name']}")
        if element.get('type'):
            print(f"     Type: {element['type']}")
        
        value_length = user_data.get('valueLength', 0)
        print(f"  📝 内容长度: {value_length} 字符")
        
        input_type = user_data.get('inputType', '')
        if input_type:
            print(f"  🔤 输入类型: {input_type}")
    
    def _print_navigate_details(self, data):
        """打印导航行为详情"""
        user_data = data.get('data', {})
        from_url = user_data.get('fromUrl', '未知')
        to_url = user_data.get('toUrl', '未知')
        
        print(f"  🔗 从: {from_url}")
        print(f"  🎯 到: {to_url}")
    
    def _print_form_details(self, data):
        """打印表单提交详情"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  📋 表单: {element.get('tagName', 'FORM')}")
        if element.get('id'):
            print(f"     ID: {element['id']}")
        
        method = user_data.get('method', '').upper()
        action = user_data.get('action', '')
        element_count = user_data.get('elementCount', 0)
        
        print(f"  📤 方法: {method}")
        if action:
            print(f"  🎯 目标: {action}")
        print(f"  📊 字段数: {element_count}")
    
    def _print_scroll_details(self, data):
        """打印滚动行为详情"""
        user_data = data.get('data', {})
        direction = user_data.get('scrollDirection', '未知')
        delta = user_data.get('scrollDelta', 0)
        percentage = user_data.get('scrollPercentage', 0)
        
        print(f"  📜 方向: {direction}")
        print(f"  📏 距离: {delta}px")
        print(f"  📊 进度: {percentage}%")
    
    def _get_monitoring_script(self) -> str:
        """获取JavaScript监控脚本"""
        return '''
        (function() {
            if (window._simpleUserBehaviorMonitorInitialized) return;
            window._simpleUserBehaviorMonitorInitialized = true;
            
            console.log("🎯 Simple User Behavior Monitor initialized");
            
            // 用户行为收集器
            const collector = {
                getElementInfo: function(element) {
                    if (!element) return {};

                    // Only include non-empty meaningful fields
                    const info = {};

                    // Core positioning fields (always include if present)
                    if (element.tagName) info.tagName = element.tagName;
                    if (element.id) info.id = element.id;
                    if (element.className) info.className = element.className;

                    // Semantic information (only if non-empty)
                    const text = (element.textContent || '').trim();
                    if (text) info.textContent = text.slice(0, 100);

                    // Link-related (only if present)
                    if (element.href) info.href = element.href;
                    if (element.src) info.src = element.src;

                    // Form-related (only for input/select/textarea)
                    if (element.name) info.name = element.name;
                    if (element.type) info.type = element.type;
                    if (element.value) info.value = element.value.slice(0, 50);

                    return info;
                },
                
                report: function(type, element, additionalData) {
                    // Generate human-readable timestamp
                    const now = new Date();
                    const timestamp = now.toISOString().slice(0, 19).replace('T', ' '); // "2025-10-10 17:52:57"

                    const data = {
                        type: type,
                        timestamp: timestamp,
                        url: window.location.href,
                        page_title: document.title,
                        element: element ? this.getElementInfo(element) : {},
                        data: additionalData || {}
                    };
                    
                    // 通过CDP绑定发送到Python
                    if (window.reportUserBehavior) {
                        window.reportUserBehavior(JSON.stringify(data));
                    }
                }
            };
            
            // 监控用户点击
            document.addEventListener('click', function(e) {
                // For click: no additional data needed (element info is enough)
                collector.report('click', e.target, {});
            }, true);
            
            // 监控输入事件
            document.addEventListener('input', function(e) {
                collector.report('input', e.target, {
                    inputType: e.inputType,
                    valueLength: e.target.value ? e.target.value.length : 0
                });
            }, true);
            
            // 监控表单提交
            document.addEventListener('submit', function(e) {
                collector.report('form_submit', e.target, {
                    method: e.target.method || 'GET',
                    action: e.target.action || '',
                    elementCount: e.target.elements ? e.target.elements.length : 0
                });
            }, true);
            
            // 监控页面导航 (URL变化)
            let currentUrl = window.location.href;
            setInterval(function() {
                if (window.location.href !== currentUrl) {
                    collector.report('navigate', null, {
                        fromUrl: currentUrl,
                        toUrl: window.location.href
                    });
                    currentUrl = window.location.href;
                }
            }, 500);
            
            // 监控文本选择
            document.addEventListener('mouseup', function(e) {
                const selection = window.getSelection();
                const selectedText = selection ? selection.toString().trim() : '';

                if (selectedText) {
                    collector.report('select', e.target, {
                        selectedText: selectedText,
                        textLength: selectedText.length
                    });
                }
            }, true);

            // 监控复制操作
            document.addEventListener('copy', function(e) {
                const selection = window.getSelection();
                const copiedText = selection ? selection.toString().trim() : '';

                if (copiedText) {
                    collector.report('copy_action', e.target, {
                        copiedText: copiedText,
                        textLength: copiedText.length
                    });
                }
            }, true);

            // 监控滚动 (节流处理)
            let scrollTimeout;
            let lastScrollY = window.scrollY;
            window.addEventListener('scroll', function() {
                clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(function() {
                    const currentScrollY = window.scrollY;
                    const scrollDirection = currentScrollY > lastScrollY ? 'down' : 'up';
                    const scrollDelta = Math.abs(currentScrollY - lastScrollY);
                    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
                    const scrollPercentage = maxScroll > 0 ? Math.round((currentScrollY / maxScroll) * 100) : 0;

                    if (scrollDelta > 50) { // 只报告大于50px的滚动
                        collector.report('scroll', null, {
                            direction: scrollDirection,
                            distance: scrollDelta
                        });
                        lastScrollY = currentScrollY;
                    }
                }, 100); // 100ms节流
            });
            
        })();
        '''
    
    async def stop_monitoring(self) -> None:
        """停止监控"""
        self._is_monitoring = False
        print(f"\n🛑 用户行为监控已停止 - 会话ID: {self.session_id}")
        print("=" * 60)
        logger.info(f"User behavior monitoring stopped for {self.session_id}")
```

### 2. 📄 `enhanced_browser_use.py` - 简化包装器

```python
from typing import Optional, Any
from .browser_use import BrowserUseTool
from .user_behavior.monitor import SimpleUserBehaviorMonitor

class SimpleBrowserUseTool:
    """简化版Browser-Use工具 - 只监控和打印用户行为"""
    
    def __init__(self, enable_behavior_monitoring: bool = True, **browser_use_kwargs):
        # 初始化原始Browser-Use工具
        self.browser_tool = BrowserUseTool(**browser_use_kwargs)
        
        # 初始化用户行为监控
        self.behavior_monitoring_enabled = enable_behavior_monitoring
        self.behavior_monitor: Optional[SimpleUserBehaviorMonitor] = None
        
        if enable_behavior_monitoring:
            self.behavior_monitor = SimpleUserBehaviorMonitor()
    
    async def start_browser(self, **kwargs) -> Any:
        """启动浏览器并设置用户行为监控"""
        # 启动原始Browser-Use功能
        result = await self.browser_tool.start_browser(**kwargs)
        
        # 设置用户行为监控
        if self.behavior_monitoring_enabled and self.behavior_monitor:
            try:
                await self.behavior_monitor.setup_monitoring(
                    self.browser_tool.browser_session
                )
            except Exception as e:
                print(f"❌ 设置行为监控失败: {e}")
        
        return result
    
    async def stop_browser(self) -> Any:
        """停止浏览器和用户行为监控"""
        # 停止用户行为监控
        if self.behavior_monitor:
            await self.behavior_monitor.stop_monitoring()
        
        # 停止原始Browser-Use功能
        return await self.browser_tool.stop_browser()
    
    # 代理所有Browser-Use的原始方法
    def __getattr__(self, name):
        """代理到原始Browser-Use工具"""
        return getattr(self.browser_tool, name)
```

## 最小修改方案

### 修改现有文件（3个文件，总共不超过20行代码）

#### 1. 修改 `browser_use.py`
```python
# 在文件顶部添加
try:
    from .enhanced_browser_use import SimpleBrowserUseTool
    SIMPLE_MONITORING_AVAILABLE = True
except ImportError:
    SIMPLE_MONITORING_AVAILABLE = False

# 在BrowserUseTool类中添加
class BrowserUseTool:
    # 现有代码...
    
    @classmethod
    def create_with_monitoring(cls, **kwargs):
        """创建带用户行为监控的工具"""
        if not SIMPLE_MONITORING_AVAILABLE:
            raise ImportError("Simple monitoring features not available")
        return SimpleBrowserUseTool(enable_behavior_monitoring=True, **kwargs)
```

#### 2. 修改 `enhanced_browser_use.py` - 独立使用
```python
# 用户行为监控与特定Agent解耦，可以独立使用
from .enhanced_browser_use import SimpleBrowserUseTool

# 直接创建带监控的浏览器工具
browser_tool = SimpleBrowserUseTool(enable_behavior_monitoring=True)
```

## 使用方式

### 独立使用监控

```python
from base_app.base_app.base_agent.tools.browser_use.enhanced_browser_use import SimpleBrowserUseTool

# 创建启用行为监控的浏览器工具
browser_tool = SimpleBrowserUseTool(enable_behavior_monitoring=True)

# 执行浏览器任务（会自动设置监控）
result = await browser_tool.execute("execute", {
    "task": "Navigate to https://example.com and interact with the page"
})

# 现在用户在浏览器中的任何操作都会在后台打印出来
print("请在浏览器中进行操作，后台会实时显示用户行为...")

# 清理资源
await browser_tool.cleanup()
```

### 预期输出示例

```
🎯 用户行为监控已启动 - 会话ID: session_20240115_143022
============================================================

[2025-10-10 14:30:45] 🔥 CLICK
  📍 页面: 示例网站
  🌐 URL: https://example.com
  🖱️  元素: BUTTON
     ID: submit-btn
     Class: btn btn-primary
     文本: 提交表单
  📍 位置: (450, 200)
------------------------------------------------------------

[2025-10-10 14:30:46] 🔥 INPUT
  📍 页面: 示例网站
  🌐 URL: https://example.com
  ⌨️  输入框: INPUT
     ID: username
     Name: username
     Type: text
  📝 内容长度: 8 字符
  🔤 输入类型: insertText
------------------------------------------------------------

[2025-10-10 14:30:48] 🔥 NAVIGATE
  📍 页面: 新页面
  🌐 URL: https://example.com/new-page
  🔗 从: https://example.com
  🎯 到: https://example.com/new-page
------------------------------------------------------------
```

## 实现步骤

### 步骤1: 创建文件结构
```bash
mkdir -p base_app/base_app/base_agent/tools/browser_use/user_behavior
```

### 步骤2: 创建新文件
1. `user_behavior/__init__.py` (空文件)
2. `user_behavior/monitor.py` (上面的完整代码)
3. `enhanced_browser_use.py` (上面的完整代码)

### 步骤3: 最小修改现有文件
按照上面的方案修改3个现有文件

### 步骤4: 测试
```python
# 创建测试脚本：tests/unit/baseagent/tools/simple_browser_test.py
import asyncio
from base_app.base_app.base_agent.tools.browser_use.enhanced_browser_use import SimpleBrowserUseTool

async def test_behavior_monitoring():
    # 创建启用监控的浏览器工具
    browser_tool = SimpleBrowserUseTool(enable_behavior_monitoring=True)
    
    try:
        # 执行浏览器任务，会自动设置监控
        result = await browser_tool.execute("execute", {
            "task": "Navigate to https://httpbin.org/forms/post and wait for user interactions"
        })
        
        print("请在浏览器中点击、输入、提交表单等操作...")
        print("监控输出将在下方显示...")
        
        # 等待用户操作
        await asyncio.sleep(60)  
        
    finally:
        # 清理资源
        await browser_tool.cleanup()

if __name__ == "__main__":
    asyncio.run(test_behavior_monitoring())
```

这个简化方案专注于核心功能：**监控用户行为并实时打印**，去掉了所有存储和分析功能，实现更加轻量级和直接。