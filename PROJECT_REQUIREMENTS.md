# 项目名称：自然语言驱动的 Agent 构建与运行平台

## 一、项目简介

本项目旨在构建一个平台，允许非技术用户通过自然语言描述任务，系统自动为其构建可运行的智能 Agent。Agent 能够完成特定业务任务，如读取微信聊天记录、填写企业微信插件、辅助用户填写表单等。

平台核心由以下几部分组成：

- 通用 Agent 架构（基于 Workflow + Tools + Memory）
- 大模型辅助的 Agent 构建流程（产品经理 Agent + 项目经理 Agent）
- Agent 测试与验证机制
- Agent 执行环境（支持安卓、浏览器插件等）

**注意：本系统使用 Claude API / Claude Code 作为"开发助手"，但最终生成的 Agent 是在自定义平台中运行的，不依赖 Claude 执行。**

---

## 二、项目阶段划分

### ✅ 当前阶段：Agent 构建部分（Stage 1）

1. 用户通过自然语言输入描述
2. Claude 扮演 "产品经理 Agent" 角色，引导用户明确需求 → 生成开发提示词
3. Claude 扮演 "项目经理 Agent" 角色，基于提示词输出 Agent 代码（workflow + tools + memory）
4. 自动执行 Agent 代码，验证其是否满足用户需求

### 🚧 后续阶段：Agent 使用部分（Stage 2）

- 提供用户调用 Agent 的接口（网页、APP、API）
- 支持状态管理、参数输入、权限控制等

---

## 三、Demo 需求说明

### 🅰️ A需求：路演信息自动填写 Agent

**功能：**
- 从微信聊天记录中提取客户约定的路演时间
- 自动打开企业微信插件，填写表单

**工具需求：**
- `android_use`：用于控制安卓系统中的微信、企业微信
- `browser_use`：用于打开企业微信插件网页（如果表单在网页中）

**流程：**
1. 启动微信 → 搜索客户 → 读取最近聊天记录
2. 提取时间、客户名、项目名等关键词
3. 打开企业微信插件页面 → 填写表单 → 提交

---

### 🅱️ B需求：表单辅助 Agent

**功能：**
- 用户上传表单结构（schema）
- Agent 回答用户关于字段含义的问题
- 用户填写字段后，Agent 自动提交表单数据

**工具需求：**
- `memory`：记录表单结构、字段含义
- `http_tool`（可选）：将表单数据提交到后端系统

**流程：**
1. 加载表单结构 → 解析字段
2. 接收用户提问 → 提供字段解释
3. 接收用户输入 → 提交到系统

---

## 四、系统架构说明

### ✅ Agent 架构组成

| 模块 | 描述 |
|------|------|
| **Workflow** | 串联任务步骤，定义执行流程 |
| **Tools** | 外部能力封装（如 android_use、browser_use） |
| **Memory** | 管理上下文状态（变量、历史记录） |
| **Trigger** | 触发方式：用户输入、定时、监听 |

---

### ✅ 支持的工具系统

| 工具 | 描述 |
|------|------|
| `android_use` | 启动安卓模拟器，控制微信和企业微信（支持 A11Tree） |
| `browser_use` | 控制浏览器进行网页操作（打开、点击、填表） |
| `e2b` | 浏览器可视化操作插件（用于未来增强） |

---

## 五、核心组件职责说明

### 🧠 产品经理 Agent（Claude）

**目标：引导用户明确需求，并输出结构化任务描述 + Claude Prompt**

- 分析用户自然语言输入
- 提问用户补充关键信息（如触发方式、工具需求、输出目标）
- 最终输出结构化 Agent 需求描述（JSON） + Claude Prompt 给项目经理 Agent

---

### 👷 项目经理 Agent（Claude）

**目标：根据 Prompt 自动生成 Agent 代码 + 测试 + 文档**

- 读取结构化需求（JSON）
- 输出一个完整的 Agent 定义（Python + Workflow + Tools）
- 自动生成测试代码，验证功能是否正确
- 输出说明文档（可选）

---

### 🧪 测试系统

**目标：验证 Agent 是否能按预期工作**

- 加载 Agent 代码并运行
- 模拟用户输入、聊天内容、工具调用
- 校验结果是否符合预期
- 输出运行日志，便于调试

---

## 六、Agent 工作流定义格式（DSL）

平台支持使用 JSON / YAML / Python 定义 Agent 的工作流程。格式示例如下：

```json
{
  "name": "路演助手",
  "trigger": "用户输入",
  "inputs": ["客户名", "时间", "项目"],
  "workflow": [
    {
      "step": "读取聊天记录",
      "tool": "android_use",
      "action": "read_chat",
      "params": {"target": "微信", "contact": "{{客户名}}"}
    },
    {
      "step": "提取时间",
      "tool": "llm_extract",
      "action": "extract_entities",
      "params": {"text": "{{聊天记录}}", "entities": ["时间", "项目"]}
    },
    {
      "step": "填写插件",
      "tool": "browser_use",
      "action": "fill_form",
      "params": {"url": "https://work.weixin.qq.com/plugin/..."}
    }
  ],
  "memory": true
}
```