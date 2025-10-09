# AgentCrafter - 自然语言驱动的 Agent 构建平台

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

AgentCrafter 是一个创新的平台，允许非技术用户通过自然语言描述任务，系统自动为其构建可运行的智能 Agent。Agent 能够完成特定业务任务，如读取微信聊天记录、填写企业微信插件、辅助用户填写表单等。

## 🌟 核心特性

- **🗣️ 自然语言驱动**: 用户只需用自然语言描述需求，无需编程经验
- **🤖 双 Agent 架构**: 产品经理 Agent 收集需求，项目经理 Agent 生成代码
- **🔧 通用 Agent 框架**: 基于 Workflow + Tools + Memory + Trigger 的统一架构
- **🌐 丰富的工具支持**: 内置 browser_use、android_use 等强大工具
- **🚀 开箱即用**: Docker 容器化部署，一键启动
- **🔒 安全可靠**: 沙箱执行环境，权限控制

## 🏗️ 系统架构

```
┌─────────────────────────────────────────┐
│           用户交互层 (UI Layer)            │
├─────────────────────────────────────────┤
│        Agent 构建层 (Builder Layer)       │
│  ┌─────────────┐  ┌─────────────────────┐ │
│  │产品经理Agent │  │    项目经理Agent     │ │
│  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────┤
│       Agent 执行层 (Runtime Layer)        │
│  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Agent Core  │  │   工具调度器        │ │
│  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────┤
│        工具层 (Tool Layer)                │
│  browser_use | android_use | memory | ... │
└─────────────────────────────────────────┘
```

## 📦 快速开始

### 环境要求

- Python 3.9+
- Node.js 16+ (前端开发)

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/your-org/agentcrafter.git
cd agentcrafter
```

2. **配置环境变量**
```bash
# Set LLM API keys as system environment variables
export OPENAI_API_KEY=your_openai_key
export ANTHROPIC_API_KEY=your_anthropic_key
```

3. **Configure Web Backend** (optional)
```bash
# Copy and edit backend configuration
cp src/client/web/config/backend.yaml.example src/client/web/config/backend.yaml
# Edit backend.yaml to configure database, server settings, etc.
```

4. **本地开发部署**
```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright（用于浏览器自动化）
playwright install chromium --with-deps

# 启动服务
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 首次使用

1. 访问 http://localhost:8000
2. 在环境变量中设置你的 API Key（OpenAI/Claude）
3. 开始描述你的第一个 Agent 需求！

## 🎯 使用示例

### 示例 1: 路演信息自动填写 Agent

```python
# 用户自然语言输入
需求描述 = """
我需要一个助手帮我处理路演信息：
1. 从微信聊天记录中提取客户约定的路演时间
2. 自动打开企业微信插件，填写路演申请表单
3. 提交申请并通知我结果
"""

# 系统自动生成的 Agent
{
  "name": "路演助手",
  "workflow": [
    {
      "step": "读取聊天记录",
      "tool": "android_use",
      "action": "read_chat",
      "params": {"app": "微信", "contact": "{{客户名}}"}
    },
    {
      "step": "提取关键信息",
      "tool": "llm_extract", 
      "action": "extract_entities",
      "params": {"text": "{{聊天记录}}", "entities": ["时间", "项目", "客户"]}
    },
    {
      "step": "填写申请表单",
      "tool": "browser_use",
      "action": "fill_form",
      "params": {"url": "企业微信插件地址", "data": "{{提取的信息}}"}
    }
  ]
}
```

### 示例 2: 使用 Browser 工具

```python
from tools.browser_use import BrowserTool

# 创建浏览器工具
tool = BrowserTool()
await tool.initialize()

# 执行复杂任务
result = await tool.execute("execute_task", {
    "task": "访问京东，搜索iPhone 15，获取前5个商品的价格信息"
})

print(result.data)  # 返回提取的商品信息
```

## 🔧 工具系统

### Browser 工具 (browser_use)

基于 browser-use 库的智能浏览器自动化工具：

- **支持动作**:
  - `navigate`: 导航到指定URL
  - `click`: 点击页面元素
  - `fill_form`: 填写表单
  - `extract_data`: 提取页面数据
  - `screenshot`: 截取截图
  - `execute_task`: 执行复杂的自然语言任务

- **配置选项**:
```python
config = BrowserConfig(
    headless=True,           # 无头模式
    browser_type="chromium", # 浏览器类型
    llm_model="gpt-4o",     # LLM 模型
    timeout=300             # 超时时间
)
```

### Android 工具 (开发中)

用于控制 Android 设备，支持微信、企业微信等应用操作。

### Memory 工具 (开发中)

提供持久化内存管理，支持会话状态保存和恢复。

## 📖 文档

- [系统架构设计](./ARCHITECTURE.md) - 完整的架构设计和组件说明
- [项目需求文档](./PROJECT_REQUIREMENTS.md) - 原始需求和功能规划
- [开发指南](./docs/guides/DEVELOPMENT_GUIDE.md) - 开发者必读指南
- [API 参考文档](./docs/api/) - REST API 接口文档 (待完善)
- [工具开发指南](./docs/guides/) - 自定义工具开发 (待完善)
- [部署指南](./docs/deployment/) - 生产环境部署 (待完善)

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定模块测试
pytest tests/test_browser_tool.py -v

# 运行覆盖率测试
pytest --cov=tools --cov-report=html
```

## 📝 示例代码

查看 `examples/` 目录获取更多使用示例：

- [Browser 工具示例](./examples/browser_examples.py)
- [完整 Agent 示例](./examples/agent_examples.py)
- [工具开发示例](./examples/tool_development.py)

## 🤝 贡献指南

我们欢迎所有形式的贡献！请查看 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解详细信息。

### 开发流程

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

## 📄 许可证

本项目基于 MIT 许可证 - 查看 [LICENSE](./LICENSE) 文件了解详情。

## 🚀 路线图

### Stage 1: 核心框架（当前）
- [x] 项目架构设计
- [x] BaseAgent 基础框架
- [x] Browser 工具集成
- [x] 数据Schema定义
- [x] 目录结构规划
- [ ] 工具知识库系统
- [ ] 项目经理Agent
- [ ] Claude Code集成
- [ ] Android 工具开发

### Stage 2: 平台化
- [ ] Web 管理界面
- [ ] REST API接口
- [ ] 可视化Agent构建器
- [ ] Agent市场和模板库
- [ ] 多用户协作

### Stage 3: 企业级
- [ ] 企业级权限管理
- [ ] 高可用部署架构
- [ ] 性能监控和优化
- [ ] 第三方系统集成

## 📞 联系我们

- 项目主页: https://github.com/your-org/agentcrafter
- 问题反馈: https://github.com/your-org/agentcrafter/issues
- 邮箱: team@agentcrafter.com

## 🙏 致谢

感谢以下开源项目的支持：

- [browser-use](https://github.com/browser-use/browser-use) - AI 浏览器自动化
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架
- [Claude API](https://www.anthropic.com/) - 强大的 AI 助手

---

⭐ 如果这个项目对你有帮助，请给我们一个 Star！