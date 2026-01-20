"""State and Intent Extraction Prompt - LLM prompt for extracting states and intents.

This prompt is used to identify States (pages/screens) and Intents (operations within pages)
from workflow event sequences.
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class StateIntentExtractionInput(BaseModel):
    """Input for state and intent extraction."""

    events_summary: str = Field(..., description="Formatted summary of workflow events")


class StateData(BaseModel):
    """Extracted state data."""

    page_url: str = Field(..., description="URL or screen identifier")
    page_title: Optional[str] = Field(default=None, description="Title of the page/screen")
    timestamp: int = Field(..., description="When user entered this state (milliseconds)")
    end_timestamp: Optional[int] = Field(default=None, description="When user left this state")
    duration: Optional[int] = Field(default=None, description="Duration in milliseconds")
    description: Optional[str] = Field(default=None, description="Natural language description of the state")
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional attributes"
    )


class IntentData(BaseModel):
    """Extracted intent data."""

    state_index: int = Field(..., description="Index of the state this intent belongs to")
    type: str = Field(..., description="Intent type (PascalCase, e.g., ClickElement)")
    timestamp: int = Field(..., description="When the operation occurred (milliseconds)")
    element_id: Optional[str] = Field(default=None, description="Element ID")
    element_tag: Optional[str] = Field(default=None, description="HTML tag name")
    element_class: Optional[str] = Field(default=None, description="CSS class")
    xpath: Optional[str] = Field(default=None, description="XPath selector")
    css_selector: Optional[str] = Field(default=None, description="CSS selector")
    text: Optional[str] = Field(default=None, description="Text content or label")
    value: Optional[str] = Field(default=None, description="Input value")
    coordinates: Optional[Dict[str, int]] = Field(default=None, description="Click coordinates (x, y)")
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional attributes"
    )


class StateIntentExtractionOutput(BaseModel):
    """Output from state and intent extraction."""

    states: List[StateData] = Field(..., description="List of extracted states")
    intents: List[IntentData] = Field(..., description="List of extracted intents")


class StateIntentExtractionPrompt(BasePrompt[StateIntentExtractionInput, StateIntentExtractionOutput]):
    """Prompt for state and intent extraction from workflow events."""

    def __init__(self):
        """Initialize the prompt."""
        super().__init__(prompt_name="state_intent_extraction", version="1.0")

    def get_system_prompt(self) -> str:
        """Get system prompt."""
        return """你是一个专业的用户行为分析专家，擅长从事件序列中识别页面状态（State）和用户操作（Intent）。

你的核心任务：
1. 准确区分页面状态和页面内操作，确保每个Intent都正确关联到对应的State
2. **提取完整的元素定位信息**，使得后续系统能够精确重现用户的每一个操作
3. 不要截断或省略任何信息，特别是文本内容、XPath、CSS选择器等关键字段

关键原则：
- Intent是页面内操作，不会导致页面跳转
- 提取所有可用的元素定位信息（id, class, xpath, css_selector, text, coordinates）
- 文本内容必须完整，不要用"..."省略
- 多重定位方式能提高操作重现的成功率"""

    def build_prompt(self, input_data: StateIntentExtractionInput) -> str:
        """Build the prompt."""
        prompt = f'''分析以下用户行为事件序列，识别State（页面/屏幕状态）和Intent（页面内操作）。

## 输入事件序列
{input_data.events_summary}

## 任务要求

### 1. 识别State（页面/屏幕状态）
- **State定义**：用户所在的页面或屏幕位置（通过URL或screen ID标识）
- **State特征**：
  - 由page_url唯一标识
  - 包含用户在该页面停留期间的所有操作
  - 有明确的进入时间(timestamp)和离开时间(end_timestamp)
  - 可以计算停留时长(duration)
  - **必须包含description字段**：用自然语言描述该State的核心内容和用户行为
    - 描述应包含：用户在哪个页面、执行了哪些关键操作、操作的目的是什么
    - 示例："用户浏览商品列表页，点击了加入购物车按钮，并在搜索框中输入了搜索内容"
    - 描述应该完整、准确、便于后续语义搜索和理解用户意图

### 2. 识别Intent（页面内操作）
- **Intent定义**：在State内进行的原子级操作
- **Intent特征**：
  - 必须属于某个State（通过state_index关联）
  - 代表具体操作：点击、输入、滚动、选择等
  - **关键约束**：Intent不会导致State转换（不会跳转页面）
  - 包含操作的详细信息（元素、文本、坐标等）

### 3. Intent类型示例
- ClickElement: 点击元素
- TypeText: 输入文本
- ScrollPage: 滚动页面
- SelectOption: 选择选项
- HoverElement: 鼠标悬停
- FocusElement: 聚焦元素

### 4. 操作重现要求（CRITICAL）

**提取的Intent信息必须足够完整，以便后续能够准确重现用户的操作。**

#### 必须提取的字段（如果可用）：

1. **element_id**: 元素的ID属性（最优先的定位方式）
2. **element_tag**: HTML标签名（如button, a, input, div等）
3. **element_class**: 完整的CSS类名（不要截断）
4. **xpath**: 元素的XPath选择器（完整路径）
5. **css_selector**: CSS选择器（如有）
6. **text**: 元素的完整文本内容（**不要截断，必须提取完整文本**）
7. **value**: 对于输入框，提取输入的完整值
8. **coordinates**: 点击坐标 {{"x": 100, "y": 200}}（如果可用）

#### 字段提取原则：

- **完整性优先**：提取所有可用字段，不要省略任何信息
- **不要截断**：text、value、xpath、css_selector等字段必须完整提取，不要用"..."省略
- **精确定位**：优先使用element_id，其次xpath/css_selector，最后才使用text匹配
- **多重保障**：尽可能提供多种定位方式（id + class + xpath + text）
- **属性保留**：将额外的元素属性（如data-*、aria-*等）存入attributes字段

## 输出格式

请严格按照JSON格式输出：

```json
{{
  "states": [
    {{
      "page_url": "https://example.com/products",
      "page_title": "商品列表页",
      "timestamp": 1000000000000,
      "end_timestamp": 1000000010000,
      "duration": 10000,
      "description": "用户浏览商品列表页，点击了加入购物车按钮，并在搜索框中输入了搜索内容",
      "attributes": {{
        "category": "shopping"
      }}
    }}
  ],
  "intents": [
    {{
      "state_index": 0,
      "type": "ClickElement",
      "timestamp": 1000000002000,
      "element_id": "add-to-cart-btn-123",
      "element_tag": "button",
      "element_class": "btn btn-primary add-to-cart-button",
      "xpath": "/html/body/div[1]/main/div[2]/div[1]/button[1]",
      "css_selector": "#add-to-cart-btn-123",
      "text": "加入购物车 - 立即购买享受优惠",
      "coordinates": {{"x": 450, "y": 320}},
      "attributes": {{
        "product_id": "123",
        "data-product-name": "商品名称",
        "aria-label": "添加商品到购物车"
      }}
    }},
    {{
      "state_index": 0,
      "type": "TypeText",
      "timestamp": 1000000005000,
      "element_id": "search-input",
      "element_tag": "input",
      "element_class": "form-control search-box",
      "xpath": "/html/body/div[1]/header/div/input",
      "css_selector": "#search-input",
      "value": "咖啡豆 阿拉比卡",
      "attributes": {{
        "placeholder": "搜索商品",
        "type": "text"
      }}
    }}
  ]
}}
```

## 注意事项

1. **State唯一性**：相同的page_url代表同一个State，即使访问多次
2. **Intent归属**：每个Intent必须通过state_index明确关联到某个State
3. **时序关系**：State和Intent的timestamp必须符合时间顺序
4. **Intent约束**：只有页面内操作才是Intent，导致页面跳转的操作会在后续的Action中处理
5. **完整性**：尽可能识别所有State和Intent
6. **准确性**：type字段应准确描述操作类型，使用PascalCase命名
7. **State描述字段（REQUIRED）**：
   - 每个State必须包含description字段
   - 描述应该用自然语言总结该State的核心内容和用户在该State中的行为
   - 描述要准确、完整、易于理解，便于后续语义搜索
8. **信息完整性（最重要）**：
   - 提取所有可用的元素定位信息（id, class, xpath, css_selector）
   - 文本内容必须完整，不要截断
   - 优先提供多种定位方式以提高重现成功率
   - 坐标、属性等辅助信息也要尽可能提取

请开始分析并输出结果。
'''
        return prompt

    def parse_response(self, llm_response: str) -> StateIntentExtractionOutput:
        """Parse LLM response into structured output."""
        # Extract JSON from response
        start_idx = llm_response.find('{')
        end_idx = llm_response.rfind('}') + 1

        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON found in LLM response")

        json_str = llm_response[start_idx:end_idx]
        data = json.loads(json_str)

        # Validate that states exist
        if not data.get("states"):
            raise ValueError("No states found in LLM response")

        # Parse into Pydantic model
        return StateIntentExtractionOutput(**data)

    def validate_input(self, input_data: StateIntentExtractionInput) -> bool:
        """Validate input data."""
        return bool(input_data.events_summary)

    def validate_output(self, output_data: StateIntentExtractionOutput) -> bool:
        """Validate output data."""
        return bool(output_data.states)


__all__ = [
    "StateIntentExtractionPrompt",
    "StateIntentExtractionInput",
    "StateIntentExtractionOutput",
    "StateData",
    "IntentData",
]
