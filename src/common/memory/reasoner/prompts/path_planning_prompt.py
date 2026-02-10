"""Path planning prompt for L2 LLM-as-Reasoner."""

import json
from typing import Any, Dict

PATH_PLANNING_SYSTEM_PROMPT = (
    "你是一个导航路径规划器。用户给出了一个任务，"
    "以下是我记忆中相关的网页和它们之间的导航关系。"
    "请根据任务目标，从这些页面中选择最佳导航路径。"
)


PATH_PLANNING_USER_PROMPT_TEMPLATE = """## 规则
1. 路径必须是连通的：每相邻两个页面之间必须存在"已知导航关系"
2. 路径应从起点页面开始（通常是某个网站的首页）
3. 路径应到达能完成任务的终点页面
4. 只选择必要的页面，不要包含无关页面
5. 如果记忆中的页面不足以完成任务，设置 can_plan 为 false

## 任务
{task}

## 记忆中的相关页面
{states_text}

## 已知导航关系
{actions_text}

请返回 JSON：
{{
  "can_plan": true/false,
  "path": ["state_id_1", "state_id_2", ...],
  "reasoning": "选择理由"
}}"""

PATH_PLANNING_REPLAN_USER_PROMPT_TEMPLATE = """你上一次给出的路径在系统硬校验中未通过，请基于完整上下文重新规划。

## 首次规划输入（完整）
{base_user_prompt}

## 上一次规划输出
{previous_result_json}

## 校验失败反馈
{failure_feedback}

## 断边修正线索
{neighbor_hints}

## 重规划要求
- 请只使用“已知导航关系”中的连通边来组织路径。
- 如果你判断在当前页面和关系下无法形成连通路径，请返回 `can_plan=false`。
- 如果你判断新路径仍会重复同类断边，也请返回 `can_plan=false`。

请返回 JSON：
{{
  "can_plan": true/false,
  "path": ["state_id_1", "state_id_2", ...],
  "reasoning": "选择理由"
}}"""


def build_path_planning_user_prompt(task: str, states_text: str, actions_text: str) -> str:
    """Build user prompt with task and subgraph context."""
    return PATH_PLANNING_USER_PROMPT_TEMPLATE.format(
        task=task,
        states_text=states_text,
        actions_text=actions_text,
    )

def build_path_planning_replan_user_prompt(
    *,
    base_user_prompt: str,
    previous_result: Dict[str, Any],
    failure_feedback: str,
    neighbor_hints: str,
) -> str:
    """Build retry prompt with full prior context and validation feedback."""
    try:
        previous_result_json = json.dumps(previous_result, ensure_ascii=False, indent=2)
    except TypeError:
        previous_result_json = str(previous_result)

    return PATH_PLANNING_REPLAN_USER_PROMPT_TEMPLATE.format(
        base_user_prompt=base_user_prompt,
        previous_result_json=previous_result_json,
        failure_feedback=failure_feedback,
        neighbor_hints=neighbor_hints,
    )


__all__ = [
    "PATH_PLANNING_SYSTEM_PROMPT",
    "PATH_PLANNING_USER_PROMPT_TEMPLATE",
    "PATH_PLANNING_REPLAN_USER_PROMPT_TEMPLATE",
    "build_path_planning_user_prompt",
    "build_path_planning_replan_user_prompt",
]
