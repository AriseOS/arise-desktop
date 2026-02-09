"""Path planning prompt for L2 LLM-as-Reasoner."""

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


def build_path_planning_user_prompt(task: str, states_text: str, actions_text: str) -> str:
    """Build user prompt with task and subgraph context."""
    return PATH_PLANNING_USER_PROMPT_TEMPLATE.format(
        task=task,
        states_text=states_text,
        actions_text=actions_text,
    )


__all__ = [
    "PATH_PLANNING_SYSTEM_PROMPT",
    "PATH_PLANNING_USER_PROMPT_TEMPLATE",
    "build_path_planning_user_prompt",
]
