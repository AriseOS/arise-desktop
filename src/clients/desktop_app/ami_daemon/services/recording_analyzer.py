"""Recording Analyzer - Local analysis of recordings using LLM.

Analyzes user recordings to identify workflow patterns,
without requiring Cloud Backend.
"""

import logging
from typing import Any, Dict, List

from .llm_service import get_llm_service

logger = logging.getLogger(__name__)

# Pattern recognition prompt
ANALYSIS_PROMPT = """分析以下用户浏览器操作录制，识别这是什么类型的工作流模式。

## 操作记录：
{operations_summary}

## 要识别的模式类型：
1. **has_loop**: 是否有循环/重复模式（如：浏览多个商品、批量操作）
2. **has_extraction**: 是否在提取/复制数据（如：复制文本、截图、导出）
3. **has_form_fill**: 是否在填写表单（如：登录、注册、提交信息）
4. **has_navigation**: 是否在多页面间导航（如：从首页到详情页）
5. **has_search**: 是否在搜索内容（如：搜索商品、搜索信息）

## 响应格式（JSON）：
```json
{{
  "name": "简短的工作流名称（3-8个词）",
  "task_description": "一句话描述用户做了什么",
  "user_query": "用户想达成的目标",
  "patterns": {{
    "has_loop": false,
    "has_extraction": false,
    "has_form_fill": false,
    "has_navigation": true,
    "has_search": false
  }}
}}
```

只返回 JSON 对象，不要其他文字。"""


def _summarize_operations(operations: List[Dict[str, Any]], max_ops: int = 30) -> str:
    """Summarize operations for LLM analysis."""
    if not operations:
        return "(无操作)"

    lines = []
    for i, op in enumerate(operations[:max_ops]):
        op_type = op.get("type", "unknown")
        url = op.get("url", "")
        text = op.get("text", "") or op.get("target_text", "")

        if op_type == "click":
            lines.append(f"{i+1}. 点击: {text[:50] or '元素'}")
        elif op_type == "type":
            value = op.get("value", "")[:20]
            lines.append(f"{i+1}. 输入: '{value}' 到 {text[:30] or '输入框'}")
        elif op_type == "navigate":
            lines.append(f"{i+1}. 导航: {url[:60]}")
        elif op_type == "scroll":
            lines.append(f"{i+1}. 滚动")
        else:
            lines.append(f"{i+1}. {op_type}: {text[:40] or url[:40]}")

    if len(operations) > max_ops:
        lines.append(f"... 还有 {len(operations) - max_ops} 个操作")

    return "\n".join(lines)


async def analyze_recording(
    operations: List[Dict[str, Any]],
    api_key: str,
) -> Dict[str, Any]:
    """Analyze recording to identify workflow patterns.

    Args:
        operations: List of operation events from recording
        api_key: User's API key for LLM service

    Returns:
        Dict with name, task_description, user_query, and detected patterns
    """
    if not operations:
        return {
            "name": "空录制",
            "task_description": "没有录制到操作",
            "user_query": "",
            "patterns": {
                "has_loop": False,
                "has_extraction": False,
                "has_form_fill": False,
                "has_navigation": False,
                "has_search": False,
            },
        }

    logger.info(f"Analyzing {len(operations)} operations for patterns...")

    llm_service = get_llm_service()
    provider = llm_service.get_provider(api_key)

    operations_summary = _summarize_operations(operations)
    prompt = ANALYSIS_PROMPT.format(operations_summary=operations_summary)

    try:
        response = await provider.generate_response(
            system_prompt="你是一个擅长识别用户行为模式的助手。始终用有效的 JSON 格式响应。",
            user_prompt=prompt,
        )

        import json

        response_text = response.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            start_idx = 1 if lines[0].startswith("```") else 0
            end_idx = len(lines) - 1 if lines[-1] == "```" else len(lines)
            response_text = "\n".join(lines[start_idx:end_idx])

        result = json.loads(response_text)

        analysis_result = {
            "name": result.get("name", "未命名任务"),
            "task_description": result.get("task_description", ""),
            "user_query": result.get("user_query", ""),
            "patterns": result.get("patterns", {
                "has_loop": False,
                "has_extraction": False,
                "has_form_fill": False,
                "has_navigation": True,
                "has_search": False,
            }),
        }

        logger.info(f"Analysis complete: {analysis_result['name']}, patterns: {analysis_result['patterns']}")
        return analysis_result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Response was: {response[:500] if response else 'empty'}")
        return {
            "name": "录制分析",
            "task_description": f"录制了 {len(operations)} 个浏览器操作",
            "user_query": "",
            "patterns": {
                "has_loop": False,
                "has_extraction": False,
                "has_form_fill": False,
                "has_navigation": True,
                "has_search": False,
            },
        }
    except Exception as e:
        logger.error(f"Failed to analyze recording: {e}")
        raise
