# LLM Client 重构方案

> 2026-01-21 重构记录
> **状态**: 已完成

## 1. 问题

### 1.1 当前问题

1. **代码重复**：`memgraph/services/llm/AnthropicLLMClient` 重复封装了 `src/common/llm/AnthropicProvider`
2. **阻塞事件循环**：`AnthropicLLMClient.generate()` 使用 `ThreadPoolExecutor` 运行 async 代码，在 FastAPI 中仍会阻塞
3. **接口不一致**：memgraph 使用 `LLMClient` 接口，其他服务直接使用 `AnthropicProvider`

### 1.2 影响

- `POST /api/v1/memory/add` 处理时会阻塞整个 cloud backend
- 一个用户的 memory 添加操作会导致其他用户的请求无法处理

## 2. 目标

1. 统一使用 `src/common/llm/AnthropicProvider`
2. `WorkflowProcessor` 改为全异步，不阻塞事件循环
3. 删除冗余的 `memgraph/services/llm/anthropic_client.py`

## 3. 改造内容

### 3.1 删除文件

- [x] `src/cloud_backend/memgraph/services/llm/anthropic_client.py`

### 3.2 修改文件

#### 3.2.1 `WorkflowProcessor` (`workflow_processor.py`)

**改造点**：
- [x] `__init__`: 接收 `AnthropicProvider` (可选) 而非 `LLMClient`
- [x] `process_workflow()` → `async process_workflow()`
- [x] `_generate_state_description()` → `async _generate_state_description()`
- [x] `_generate_intent_sequence_description()` → `async _generate_intent_sequence_description()`
- [x] `_generate_action_description()` → `async _generate_action_description()`
- [x] `_generate_workflow_description()` → `async _generate_workflow_description()`
- [x] `_generate_descriptions()` → `async _generate_descriptions()`
- [x] 修复 `self.model_name` 未定义问题
- [x] 所有 LLM 方法支持 `llm_provider=None` 情况，返回默认值

**LLM 调用方式变更**：
```python
# Before (LLMClient)
messages = [LLMMessage(role="user", content=prompt)]
response = self.llm_client.generate(messages, temperature=0.3, max_tokens=100)
return response.content

# After (AnthropicProvider)
response = await self.llm_provider.generate_response(
    system_prompt="",
    user_prompt=prompt
)
return response
```

#### 3.2.2 `main.py`

**改造点**：
- [x] `add_to_memory()`: `processor.process_workflow()` → `await processor.process_workflow()`
- [x] `upload_recording()`: 同上
- [x] 创建 `WorkflowProcessor` 时传入 `AnthropicProvider` 而非 `LLMClient`
- [x] `_get_reasoner_for_user()`: 使用 `llm_provider` 参数

```python
# Before
from src.cloud_backend.memgraph.services import create_llm_client, LLMProvider
llm_client = create_llm_client(
    provider=LLMProvider.ANTHROPIC,
    model_name=...,
    api_key=...,
    base_url=...
)
processor = WorkflowProcessor(llm_client=llm_client, ...)

# After
from src.common.llm import AnthropicProvider
llm_provider = AnthropicProvider(
    api_key=...,
    model_name=...,
    base_url=...
)
processor = WorkflowProcessor(llm_provider=llm_provider, ...)
```

#### 3.2.3 `Reasoner` 和相关组件

**改造点**：
- [x] `Reasoner`: 使用 `llm_provider` 参数，`plan()` 改为 async
- [x] `CognitivePhraseChecker`: 使用 `llm_provider`，`check()` 和 `_llm_check()` 改为 async
- [x] `RetrievalTool`: 使用 `llm_provider`，`execute()` 和相关方法改为 async

#### 3.2.4 `memgraph/services/llm/__init__.py`

**改造点**：
- [x] 移除 `AnthropicLLMClient`, `ClaudeLLMClient` 导出
- [x] 保留 `LLMClient` 抽象类（其他地方可能用到）
- [x] 移除 `create_llm_client` 函数

#### 3.2.5 `memgraph/services/__init__.py`

**改造点**：
- [x] 移除 `AnthropicLLMClient`, `ClaudeLLMClient`, `MockLLMClient`, `create_llm_client` 导出

#### 3.2.6 `memgraph/__init__.py`

**改造点**：
- [x] 移除 `AnthropicLLMClient`, `ClaudeLLMClient`, `create_llm_client` 导出

#### 3.2.7 `llm_client.py`

**改造点**：
- [x] 删除 `create_llm_client` 函数

### 3.3 simple_model 支持

`AnthropicProvider` 需要支持在调用时覆盖 model：

**方案 A**：创建两个 provider 实例
```python
llm_provider = AnthropicProvider(model_name="claude-sonnet-4-5")
simple_provider = AnthropicProvider(model_name="claude-haiku-4")
processor = WorkflowProcessor(
    llm_provider=llm_provider,
    simple_llm_provider=simple_provider
)
```

采用 **方案 A**，更简单，不需要修改 AnthropicProvider。

## 4. 改造步骤

1. [x] 修改 `WorkflowProcessor`
   - [x] 改 `__init__` 参数
   - [x] 所有 LLM 相关方法改为 async
   - [x] 修改 LLM 调用方式
   - [x] 支持无 LLM provider 情况

2. [x] 修改 `main.py`
   - [x] 修改 `add_to_memory` endpoint
   - [x] 修改 `upload_recording` endpoint
   - [x] 修改 `_get_reasoner_for_user`

3. [x] 修改 `Reasoner` 相关组件
   - [x] `Reasoner` 改为 async
   - [x] `CognitivePhraseChecker` 改为 async
   - [x] `RetrievalTool` 改为 async

4. [x] 清理 memgraph/services/llm
   - [x] 删除 `anthropic_client.py`
   - [x] 更新 `__init__.py` 导出
   - [x] 删除 `create_llm_client` 函数

5. [x] 清理 memgraph/services 和 memgraph 的 `__init__.py`

6. [ ] 测试
   - [ ] 启动 cloud backend
   - [ ] 测试 memory add
   - [ ] 确认不阻塞其他请求

## 5. 回滚方案

如果出现问题，可以通过 git 回滚：
```bash
git checkout -- src/cloud_backend/memgraph/
git checkout -- src/cloud_backend/main.py
```
