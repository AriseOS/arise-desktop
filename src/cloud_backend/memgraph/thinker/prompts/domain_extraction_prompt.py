"""Domain Extraction Prompt - LLM prompt for extracting domains from URLs.

This prompt is used to identify unique domains (apps/websites) from workflow event URLs.
"""

import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class DomainExtractionInput(BaseModel):
    """Input for domain extraction."""

    urls: List[str] = Field(..., description="List of URLs to analyze")


class DomainData(BaseModel):
    """Extracted domain data."""

    domain_url: str = Field(..., description="Domain identifier (e.g., example.com)")
    domain_name: str = Field(..., description="Human-readable domain/app name")
    domain_type: str = Field(..., description="Type: 'website' or 'app'")
    related_urls: List[str] = Field(
        default_factory=list, description="All URLs belonging to this domain"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional attributes (category, description, etc.)"
    )


class DomainExtractionOutput(BaseModel):
    """Output from domain extraction."""

    domains: List[DomainData] = Field(..., description="List of extracted domains")


class DomainExtractionPrompt(BasePrompt[DomainExtractionInput, DomainExtractionOutput]):
    """Prompt for domain extraction from URLs."""

    def __init__(self):
        """Initialize the prompt."""
        super().__init__(prompt_name="domain_extraction", version="1.0")

    def get_system_prompt(self) -> str:
        """Get system prompt."""
        return """你是一个专业的域名识别专家，擅长从URL中识别和提取域名信息。
你需要准确识别不同的网站或应用，并提取它们的关键信息。"""

    def build_prompt(self, input_data: DomainExtractionInput) -> str:
        """Build the prompt."""
        # Format URLs
        urls_description = "\n".join(f"- {url}" for url in sorted(input_data.urls))

        prompt = f'''分析以下用户行为数据中的URL，识别出所有不同的域名(Domain)。

## 输入URL列表
{urls_description}

## 任务要求

请识别出所有不同的域名(app/网站)，对于每个域名，提取以下信息：

1. **domain_url**: 域名标识（如 "example.com" 或 "com.app.name"）
2. **domain_name**: 可读的域名/应用名称
3. **domain_type**: 类型 - "website" 或 "app"
4. **related_urls**: 属于该域名的所有相关URL列表
5. **attributes**: 额外属性（如分类、描述等）

## 输出格式

请严格按照JSON格式输出：

```json
{{
  "domains": [
    {{
      "domain_url": "example.com",
      "domain_name": "Example Website",
      "domain_type": "website",
      "related_urls": ["https://example.com", "https://www.example.com"],
      "attributes": {{
        "category": "ecommerce",
        "description": "Online shopping platform"
      }}
    }}
  ]
}}
```

## 注意事项

1. 同一网站的不同子域名可能属于同一域名
2. 如果是app，domain_url使用包名格式（如 com.app.name）
3. related_urls应包含所有属于该域名的URL
4. 确保domain_url是唯一标识符
5. 严格遵循JSON格式

请开始分析并输出结果。
'''
        return prompt

    def parse_response(self, llm_response: str) -> DomainExtractionOutput:
        """Parse LLM response into structured output."""
        # Extract JSON from response
        start_idx = llm_response.find('{')
        end_idx = llm_response.rfind('}') + 1

        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON found in LLM response")

        json_str = llm_response[start_idx:end_idx]
        data = json.loads(json_str)

        # Parse into Pydantic model
        return DomainExtractionOutput(**data)

    def validate_input(self, input_data: DomainExtractionInput) -> bool:
        """Validate input data."""
        return bool(input_data.urls)

    def validate_output(self, output_data: DomainExtractionOutput) -> bool:
        """Validate output data."""
        return bool(output_data.domains)


__all__ = [
    "DomainExtractionPrompt",
    "DomainExtractionInput",
    "DomainExtractionOutput",
    "DomainData",
]
