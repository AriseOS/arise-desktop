# Workflow Generation Tests

这些测试脚本验证完整的工作流生成流程：从用户操作录制到最终可执行的 workflow YAML。

## 📋 测试流程

```
User Operations (录制)
    ↓
[Test 1] Upload to Cloud Backend
    ↓
Recording ID
    ↓
[Test 2] Generate MetaFlow (with user description)
    ↓
MetaFlow ID
    ↓
[Test 3] Generate Workflow YAML
    ↓
Workflow YAML (可执行)
```

## 🧪 测试脚本

### Test 1: 录制用户操作

**文件:** `1_test_recording.py`

**功能:**
- 启动浏览器到指定 URL
- 录制用户的点击、输入等操作
- 保存到本地 `~/ami/users/default_user/recordings/`

**运行:**
```bash
python tests/app_backend/1_test_recording.py
```

**输出:**
- Session ID
- 录制文件路径

---

### Test 2: 上传用户操作录制

**文件:** `2_test_upload_recording.py`

**功能:**
- 从本地存储加载最新的录制文件
- 上传到 Cloud Backend
- 获取 `recording_id`

**运行:**
```bash
python tests/app_backend/2_test_upload_recording.py
```

**输出:**
- Recording ID (用于下一步)
- 保存状态到 `.test_state.json`

---

### Test 3: 生成 MetaFlow

**文件:** `3_test_generate_metaflow.py`

**功能:**
- 使用 recording_id 和用户的自然语言描述
- 调用 Cloud Backend LLM 生成 MetaFlow
- 获取 `metaflow_id`

**运行:**
```bash
# 使用默认描述
python tests/app_backend/3_test_generate_metaflow.py

# 使用自定义描述
python tests/app_backend/3_test_generate_metaflow.py "我想在 Google 搜索咖啡机，然后点击第一个结果"
```

**输出:**
- MetaFlow ID (用于下一步)
- MetaFlow 结构预览
- 更新状态到 `.test_state.json`

---

### Test 4: 生成 Workflow YAML

**文件:** `4_test_generate_workflow.py`

**功能:**
- 使用 metaflow_id
- 调用 Cloud Backend LLM 生成 workflow YAML
- 下载并保存到本地 `~/ami/users/default_user/workflows/`

**运行:**
```bash
python tests/app_backend/4_test_generate_workflow.py
```

**输出:**
- Workflow 名称
- Workflow 文件路径
- Workflow 结构预览
- 更新状态到 `.test_state.json`

---

## 🚀 运行测试

按顺序单独运行每个测试：

```bash
# 1. 录制用户操作
python tests/app_backend/1_test_recording.py

# 2. 上传到 Cloud Backend
python tests/app_backend/2_test_upload_recording.py

# 3. 生成 MetaFlow (可自定义描述)
python tests/app_backend/3_test_generate_metaflow.py "我的任务描述"

# 4. 生成 Workflow YAML
python tests/app_backend/4_test_generate_workflow.py
```

## 📦 前置条件

### 1. 启动 Cloud Backend

```bash
./scripts/start_cloud_backend.sh
```

Cloud Backend 应该运行在 `http://localhost:9000`

### 2. 配置 LLM API Key

```bash
# 使用 Anthropic (Claude)
export ANTHROPIC_API_KEY=your_anthropic_key

# 或使用 OpenAI (GPT)
export OPENAI_API_KEY=your_openai_key
```

### 3. 创建录制数据

先运行录制测试创建数据：

```bash
# 启动 App Backend daemon
./scripts/start_http_daemon.sh

# 在另一个终端，运行录制测试
python tests/app_backend/1_test_recording.py
```

这会在 `~/ami/users/default_user/recordings/` 创建录制文件。

## 📊 测试数据流

### 输入数据 (operations.json)

```json
{
  "session_id": "session_20251108_160557",
  "timestamp": "2025-11-08T16:05:57",
  "operations_count": 15,
  "task_metadata": {
    "title": "Search Coffee",
    "description": "Find coffee machines",
    "user_intent": "我想在 Google 搜索咖啡机"
  },
  "operations": [
    {
      "type": "click",
      "url": "https://www.google.com",
      "element": { "tag": "INPUT", "name": "q" },
      "timestamp": "2025-11-08 16:06:10"
    },
    ...
  ]
}
```

### 中间数据 (MetaFlow)

```json
{
  "metaflow_id": "metaflow_xxx",
  "nodes": [
    {
      "id": "node_1",
      "type": "navigate",
      "action": "navigate_to_url",
      "params": { "url": "https://www.google.com" }
    },
    {
      "id": "node_2",
      "type": "input",
      "action": "input_text",
      "params": { "selector": "input[name='q']", "text": "咖啡机" }
    },
    ...
  ],
  "edges": [
    { "from": "node_1", "to": "node_2" }
  ]
}
```

### 输出数据 (workflow.yaml)

```yaml
name: search_coffee_workflow
description: Search for coffee machines on Google

steps:
  - name: navigate_to_google
    agent_type: browser_agent
    action: navigate_to_url
    params:
      url: "https://www.google.com"

  - name: search_coffee
    agent_type: browser_agent
    action: input_text
    params:
      selector: "input[name='q']"
      text: "咖啡机"

  - name: click_search_button
    agent_type: browser_agent
    action: click_element
    params:
      selector: "button[type='submit']"
```

## 🔍 调试

### 查看测试状态

```bash
cat tests/app_backend/.test_state.json
```

### 查看 Cloud Backend 日志

Cloud Backend 控制台会显示 LLM 请求和响应。

### 查看生成的 Workflow

```bash
ls ~/ami/users/default_user/workflows/
cat ~/ami/users/default_user/workflows/*/workflow.yaml
```

## ⚠️ 注意事项

1. **LLM 调用耗时**: Test 2 和 Test 3 会调用 LLM，每次可能需要 30-60 秒
2. **API Key**: 确保设置了有效的 LLM API key
3. **录制数据质量**: 录制的操作越清晰，生成的 workflow 质量越高
4. **网络连接**: 需要稳定的网络连接到 LLM API

## 📈 后续步骤

测试通过后，可以：

1. **执行生成的 Workflow**:
   ```bash
   curl -X POST http://localhost:8765/api/workflow/execute \
     -H 'Content-Type: application/json' \
     -d '{"workflow_name": "workflow_xxx", "user_id": "default_user"}'
   ```

2. **集成到 Tauri Desktop App**:
   - 在 UI 中显示录制状态
   - 提供用户描述输入框
   - 展示生成的 workflow
   - 执行并监控 workflow

3. **优化 Workflow 质量**:
   - 改进 MetaFlow 生成提示词
   - 添加更多上下文信息
   - 优化 workflow YAML 模板
