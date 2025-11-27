"""Recording Analysis Service - Analyze user operations using LLM"""
import logging
import json
from typing import List, Dict, Any
from src.common.llm import AnthropicProvider

logger = logging.getLogger(__name__)


class RecordingAnalysisService:
    """Analyze user recording operations and generate task descriptions using AI"""

    def __init__(self):
        """Initialize with LLM provider"""
        self.llm_provider = AnthropicProvider()

    async def analyze_operations(
        self,
        operations: List[Dict[str, Any]],
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Analyze user operations and generate descriptions

        Args:
            operations: List of operation dictionaries
            user_id: User ID

        Returns:
            dict with:
                - task_description: What user did (factual)
                - user_query: What user wants to achieve (goal)
                - patterns: Detected patterns
        """
        logger.info(f"Analyzing {len(operations)} operations for user {user_id}")

        # 1. Simplify operations for LLM
        simplified_ops = self._simplify_operations(operations)

        # 2. Build analysis prompt
        prompt = self._build_analysis_prompt(simplified_ops)

        # 3. Call LLM
        logger.info("Calling LLM to analyze operations...")
        response = await self.llm_provider.generate_response(
            system_prompt="You are an AI assistant that analyzes user web operations. Return ONLY valid JSON, no additional text.",
            user_prompt=prompt
        )

        # 4. Parse response
        try:
            # Clean markdown code blocks if present
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]  # Remove ```json
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]  # Remove ```
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]  # Remove trailing ```
            cleaned_response = cleaned_response.strip()

            result = json.loads(cleaned_response)
            logger.info("Analysis successful:")
            logger.info(f"  Name: {result.get('name', 'NOT_IN_RESULT')}")
            logger.info(f"  Task Description: {result.get('task_description', '')[:100]}...")
            logger.info(f"  User Query: {result.get('user_query', '')[:100]}...")
            logger.info(f"  Patterns: {result.get('patterns', {})}")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response: {response}")

            # Fallback: extract manually
            return {
                "name": "Web操作",
                "task_description": "User performed web operations",
                "user_query": "Extract data from website",
                "patterns": {
                    "loop_detected": False,
                    "extracted_fields": [],
                    "navigation_depth": 1
                }
            }

    def _simplify_operations(self, operations: List[Dict]) -> List[Dict]:
        """Simplify operations for LLM consumption"""
        simplified = []

        for op in operations:
            op_type = op.get("type", "unknown")
            simplified_op = {
                "type": op_type,
                "timestamp": op.get("timestamp", ""),
                "url": op.get("url", "")
            }

            # Add type-specific data
            element = op.get("element", {})
            data = op.get("data", {})

            if op_type == "navigate":
                simplified_op["to_url"] = data.get("toUrl", op.get("url", ""))

            elif op_type == "click":
                simplified_op["element_text"] = element.get("textContent", "")[:50]
                simplified_op["element_tag"] = element.get("tagName", "")

            elif op_type == "input":
                simplified_op["field_name"] = element.get("name", "")
                simplified_op["field_type"] = data.get("fieldType", "text")
                simplified_op["value_length"] = data.get("valueLength", 0)

            elif op_type == "select":
                simplified_op["selected_text"] = data.get("selectedText", "")[:100]

            elif op_type == "copy_action":
                simplified_op["copied_text"] = data.get("copiedText", "")[:100]

            elif op_type == "scroll":
                simplified_op["direction"] = data.get("direction", "unknown")
                simplified_op["distance"] = data.get("distance", 0)

            elif op_type == "dataload":
                simplified_op["new_elements"] = data.get("added_elements_count", 0)
                simplified_op["height_change"] = data.get("height_change", 0)

            simplified.append(simplified_op)

        return simplified

    def _build_analysis_prompt(self, simplified_ops: List[Dict]) -> str:
        """Build prompt for LLM analysis"""

        operations_json = json.dumps(simplified_ops, indent=2, ensure_ascii=False)

        prompt = f"""You are analyzing user web operations to understand what they did and what they want to achieve.

**User Operations:**
```json
{operations_json}
```

---

**Example to Learn From:**

**Raw Operations:**
- navigate to https://www.producthunt.com/
- click "Launch archive"
- navigate to /leaderboard/daily/
- click "Weekly" tab
- scroll down
- click on product "v0 by Vercel"
- select text: "v0 by Vercel"
- select text: "5.0"
- select text: "Your collaborative AI assistant to design..."
- click "Team" tab
- select text: "Richárd Kunkli - Mobile @ Vercel"

**Good Analysis:**
```json
{{
  "name": "浏览ProductHunt周榜",
  "task_description": "1. Opened ProductHunt website\n2. Navigated to the weekly leaderboard page\n3. Browsed the product list\n4. Clicked on a product (v0 by Vercel) to view details\n5. Selected the product name, rating, and description\n6. Switched to the Team tab\n7. Selected team member information",
  "user_query": "Extract detailed information (name, rating, description, team members) from all products on ProductHunt's weekly leaderboard",
  "patterns": {{
    "loop_detected": true,
    "loop_count": 10,
    "extracted_fields": ["product_name", "rating", "description", "team_members"],
    "navigation_depth": 3
  }}
}}
```

**Key Points:**

1. **name** - A short, concise title (max 10 characters in Chinese, 20 in English):
   - ❌ Bad: "User performed operations on ProductHunt website"
   - ✅ Good: "浏览ProductHunt周榜" or "Browse PH Weekly"
   - Should capture the essence of what user did
   - Be specific but brief (e.g., "查看知乎热榜", "搜索GitHub", "复制产品信息")

2. **task_description** - Describe user's steps in natural language, focusing on INTENT:
   - ❌ Bad: "Clicked xpath //*[@id='root']/div[1]/button"
   - ✅ Good: "Clicked on the product to view its details"
   - Focus on WHAT the user was trying to do, not HOW (no technical details)
   - Number the steps (1., 2., 3., ...)
   - Use simple, clear language

3. **user_query** - Infer and GENERALIZE the user's goal:
   - ❌ Bad: "Get information about v0 by Vercel"
   - ✅ Good: "Extract detailed information from all products on ProductHunt's weekly leaderboard"
   - If user extracted data from ONE item → they likely want it from MULTIPLE/ALL items
   - Use keywords like: "all products", "top 10", "each item", "every product"
   - Think: what is the REAL task they want to automate?

4. **patterns.loop_detected**:
   - true: if user visited a list page (leaderboard, search results, category page) AND extracted data
   - false: if user just navigated or did one-off actions

5. **patterns.loop_count**:
   - If loop detected: suggest 10 (reasonable default for "top items")
   - Otherwise: null

6. **patterns.extracted_fields**:
   - Semantic names based on what user selected/copied
   - Examples: "product_name", "price", "rating", "title", "author"

---

**Your Task:**

Analyze the operations and return JSON:

```json
{{
  "name": "Short title (max 10 Chinese chars or 20 English chars)",
  "task_description": "Step-by-step description of user's actions in natural language",
  "user_query": "Generalized goal - what does the user want to achieve/automate",
  "patterns": {{
    "loop_detected": true/false,
    "loop_count": <number or null>,
    "extracted_fields": ["field1", "field2"],
    "navigation_depth": <number>
  }}
}}
```

**Important:**
- Return ONLY valid JSON, no markdown code blocks, no extra text
- name: short, concise title (e.g., "浏览知乎热榜", "Search GitHub")
- task_description: natural language, numbered steps, focus on user intent
- user_query: generalize to multiple items if user extracted data from a list

Now analyze:"""

        return prompt

