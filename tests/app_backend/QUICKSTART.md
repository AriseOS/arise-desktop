# Quick Start Guide - Workflow Generation Tests

## 📝 概述

完整测试从用户操作录制到生成可执行 workflow 的流程。

## 🚀 5 分钟快速开始

### Step 1: 启动服务 (2 个终端)

**终端 1 - App Backend:**
```bash
./scripts/start_http_daemon.sh
```

**终端 2 - Cloud Backend:**
```bash
./scripts/start_cloud_backend.sh
```

### Step 2: 配置 LLM API Key

```bash
export ANTHROPIC_API_KEY=your_anthropic_key
# 或
export OPENAI_API_KEY=your_openai_key
```

### Step 3: 创建录制数据

**终端 3:**
```bash
python tests/app_backend/1_test_recording.py
```

这会：
1. 启动浏览器到 Google
2. 等待你执行一些操作（输入、点击等）
3. 按 ENTER 停止录制
4. 保存到 `~/ami/users/default_user/recordings/`

### Step 4: 生成 Workflow

```bash
# 2. 生成 Workflow (自定义描述可选)
python tests/app_backend/2_test_generate_workflow.py "我想在淘宝搜索机械键盘"

# 或使用默认描述
python tests/app_backend/2_test_generate_workflow.py
```

## 📊 期望输出

### Test 1: Recording
```
✓ Recording started: session_20251108_160557
✓ Recording stopped: 15 operations
```

### Test 2: Generate Workflow
```
✓ Found recording: session_20251108_160557
  Operations: 15
✓ Workflow generated!
  Workflow Name: workflow_20251108_160557
  Local Path: ~/ami/users/default_user/workflows/workflow_20251108_160557/workflow.yaml
✓ Workflow file exists!
```

## 🎯 单独运行测试

### Test 1: 录制
```bash
python tests/app_backend/1_test_recording.py
```

### Test 2: 生成 Workflow
```bash
# 使用默认描述
python tests/app_backend/2_test_generate_workflow.py

# 自定义描述
python tests/app_backend/2_test_generate_workflow.py "我要搜索咖啡机并查看价格"
```

## ⚠️ 常见问题

### 1. Cloud Backend 连接失败
```
✗ Cannot connect to Cloud Backend at http://localhost:9000
```

**解决:** 启动 Cloud Backend
```bash
./scripts/start_cloud_backend.sh
```

### 2. 没有录制数据
```
✗ No recordings found at ~/ami/users/default_user/recordings
```

**解决:** 先创建录制
```bash
python tests/app_backend/1_test_recording.py
```

### 3. LLM API Key 未配置
```
✗ No LLM API key found
```

**解决:** 设置环境变量
```bash
export ANTHROPIC_API_KEY=sk-ant-xxx
```

### 4. LLM 请求超时
```
✗ Request timeout (LLM took too long)
```

**解决:**
- 检查网络连接
- 确认 API key 有效
- 可能需要增加超时时间（修改脚本中的 `timeout=120`）

## 📁 输出文件位置

### 录制文件
```
~/ami/users/default_user/recordings/session_YYYYMMDD_HHMMSS/operations.json
```

### Workflow 文件
```
~/ami/users/default_user/workflows/workflow_name/workflow.yaml
```

### 测试状态文件
```
tests/app_backend/.test_state.json
```

## 🔍 调试技巧

### 查看详细日志

**App Backend 日志:**
启动 daemon 的终端会显示所有 HTTP 请求

**Cloud Backend 日志:**
启动 Cloud Backend 的终端会显示 LLM 请求和响应

### 查看测试状态
```bash
cat tests/app_backend/.test_state.json
```

输出示例：
```json
{
  "recording_id": "rec_abc123",
  "session_id": "session_20251108_160557",
  "metaflow_id": "metaflow_xyz789",
  "workflow_name": "search_workflow_20251108"
}
```

### 查看生成的 Workflow
```bash
cat ~/ami/users/default_user/workflows/*/workflow.yaml
```

## 🎓 示例场景

### 场景 1: Google 搜索
```bash
# 1. 录制操作
python tests/app_backend/1_test_recording.py

# 2. 上传、生成 MetaFlow 和 Workflow
python tests/app_backend/2_test_upload_recording.py
python tests/app_backend/3_test_generate_metaflow.py "我想在 Google 搜索咖啡机并查看第一个结果"
python tests/app_backend/4_test_generate_workflow.py
```

### 场景 2: 电商网站
```bash
# 1. 录制操作
python tests/app_backend/1_test_recording.py

# 2. 上传、生成 MetaFlow 和 Workflow
python tests/app_backend/2_test_upload_recording.py
python tests/app_backend/3_test_generate_metaflow.py "在淘宝搜索机械键盘，按销量排序，查看前三个产品"
python tests/app_backend/4_test_generate_workflow.py
```

## 📈 下一步

测试通过后：

1. **执行 Workflow:**
   ```bash
   curl -X POST http://localhost:8765/api/workflow/execute \
     -H 'Content-Type: application/json' \
     -d '{"workflow_name": "workflow_xxx", "user_id": "default_user"}'
   ```

2. **监控执行状态:**
   ```bash
   curl http://localhost:8765/api/workflow/status/task_xxx
   ```

3. **集成到 Desktop App:**
   - 在 Tauri UI 中展示测试流程
   - 添加用户描述输入
   - 显示生成进度
   - 执行并监控 workflow
