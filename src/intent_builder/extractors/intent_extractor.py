"""
IntentExtractor - Automatically extract Intents from User Operations

Based on: docs/intent_builder/04_intent_extractor_design.md

Strategy:
1. URL-based segmentation (rule-based): Split operations when URL changes
2. LLM extraction (per segment): Generate 1-N intents with semantic descriptions
"""
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List

from src.intent_builder.core.intent import Intent, Operation, generate_intent_id

logger = logging.getLogger(__name__)


class IntentExtractor:
    """Extract Intents from User Operations using URL segmentation + LLM

    This extractor follows a two-step process:
    1. Segment operations by URL changes (rule-based, deterministic)
    2. Extract intents from each segment using LLM (semantic understanding)

    Example:
        >>> extractor = IntentExtractor(llm_provider)
        >>> intents = await extractor.extract_intents(
        ...     operations=user_ops["operations"],
        ...     task_description="Collect coffee product prices from Allegro"
        ... )
    """

    def __init__(self, llm_provider=None):
        """Initialize IntentExtractor

        Args:
            llm_provider: LLM provider instance (Anthropic/OpenAI)
                         If None, will use a mock implementation for testing
        """
        self.llm = llm_provider

    async def extract_intents(
        self,
        operations: List[Dict[str, Any]],
        task_description: str,
        source_session_id: str = "unknown"
    ) -> List[Intent]:
        """Extract intents from user operations

        Args:
            operations: List of operation dictionaries from User Operations JSON
            task_description: High-level task description
            source_session_id: Session ID for tracking

        Returns:
            List of Intent objects with auto-generated descriptions

        Example:
            >>> operations = [
            ...     {"type": "navigate", "url": "https://example.com", ...},
            ...     {"type": "click", "element": {...}, ...},
            ... ]
            >>> intents = await extractor.extract_intents(
            ...     operations, "Collect product info"
            ... )
        """
        # Step 1: URL-based segmentation
        segments = self._split_by_url(operations)

        # Log segmentation results for debugging
        logger.info("=" * 70)
        logger.info("URL-based Segmentation Result")
        logger.info("=" * 70)
        logger.info(f"Total operations: {len(operations)}, Total segments: {len(segments)}")

        for i, segment in enumerate(segments):
            op_types = [op.get('type') for op in segment]
            first_url = segment[0].get('url', 'N/A')
            last_url = segment[-1].get('url', 'N/A')

            logger.info(f"Segment {i+1}: {len(segment)} operations - {' -> '.join(op_types)}")
            if first_url == last_url:
                logger.info(f"  URL: {first_url}")
            else:
                logger.info(f"  URL (start): {first_url}")
                logger.info(f"  URL (end): {last_url}")

        logger.info("=" * 70)

        # Step 2: Extract intents from each segment using LLM
        all_intents = []
        previous_intents = []  # Track intents from previous segments

        for i, segment in enumerate(segments):
            intents = await self._extract_from_segment(
                segment,
                task_description,
                source_session_id,
                previous_intents=previous_intents
            )
            all_intents.extend(intents)
            # Update previous intents for next segment
            previous_intents = all_intents.copy()

        return all_intents

    def _split_by_url(
        self,
        operations: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Split operations into segments based on URL changes

        Rule: When a 'navigate' operation has a different URL than previous,
        add the navigate to current segment (as it's the result of previous actions),
        then start a new segment from the NEXT operation.

        Args:
            operations: List of operation dictionaries

        Returns:
            List of operation segments

        Example:
            >>> ops = [
            ...     {"type": "navigate", "url": "https://example.com/page1"},
            ...     {"type": "click", "url": "https://example.com/page1"},
            ...     {"type": "navigate", "url": "https://example.com/page2"},  # goes to current segment
            ...     {"type": "click", "url": "https://example.com/page2"},     # starts new segment
            ... ]
            >>> segments = extractor._split_by_url(ops)
            >>> len(segments)
            2
            >>> len(segments[0])
            3  # navigate, click, navigate
            >>> len(segments[1])
            1  # click
        """
        if not operations:
            return []

        segments = []
        current_segment = [operations[0]]
        last_url = operations[0].get("url")
        start_new_segment = False

        for op in operations[1:]:
            url = op.get("url")
            op_type = op.get("type")

            # If previous operation triggered a segment split, start new segment now
            if start_new_segment:
                segments.append(current_segment)
                current_segment = [op]
                start_new_segment = False
                if url:
                    last_url = url
            # Check if URL changed (and it's a navigate operation)
            elif op_type == "navigate" and url and last_url and url != last_url:
                # Add navigate to current segment (it's the result of previous action)
                current_segment.append(op)
                last_url = url
                # Mark that next operation should start a new segment
                start_new_segment = True
            else:
                # Same URL or no URL, continue segment
                current_segment.append(op)
                if url:
                    last_url = url

        # Add last segment
        if current_segment:
            segments.append(current_segment)

        return segments

    async def _extract_from_segment(
        self,
        segment: List[Dict[str, Any]],
        task_description: str,
        source_session_id: str,
        previous_intents: List[Intent] = None
    ) -> List[Intent]:
        """Extract 1-N intents from a segment using LLM

        Args:
            segment: List of operations in this segment
            task_description: Overall task description
            source_session_id: Session ID
            previous_intents: List of intents extracted from previous segments (for context)

        Returns:
            List of Intent objects
        """
        # Build prompt for LLM
        prompt = self._build_extraction_prompt(segment, task_description, previous_intents or [])

        # Call LLM
        if self.llm is None:
            raise ValueError("LLM provider is required. Please provide an LLM provider when initializing IntentExtractor.")

        response = await self.llm.generate_response("", prompt)

        # Parse LLM response
        intents_data = self._parse_llm_response(response)

        # Create Intent objects
        intents = []
        for data in intents_data:
            description = data["description"]
            operation_indices = data["operation_indices"]

            # Build operations list
            intent_operations = []
            for idx in operation_indices:
                if 0 <= idx < len(segment):
                    op_dict = segment[idx]

                    # Clean element data - convert empty dicts to None for string fields
                    element = op_dict.get("element", {})
                    if element:
                        # Clean className if it's an empty dict
                        if isinstance(element.get("className"), dict):
                            element = {**element, "className": None}

                    intent_operations.append(
                        Operation(
                            type=op_dict.get("type", ""),
                            timestamp=op_dict.get("timestamp"),
                            url=op_dict.get("url"),
                            page_title=op_dict.get("page_title"),
                            element=element if element else None,
                            data=op_dict.get("data", {})
                        )
                    )

            if intent_operations:  # Only create intent if has operations
                intent = Intent(
                    id=generate_intent_id(description),
                    description=description,
                    operations=intent_operations,
                    created_at=datetime.now(),
                    source_session_id=source_session_id
                )
                intents.append(intent)

        return intents

    def _build_extraction_prompt(
        self,
        segment: List[Dict[str, Any]],
        task_description: str,
        previous_intents: List[Intent]
    ) -> str:
        """Build LLM prompt for intent extraction

        Args:
            segment: Operations segment
            task_description: Task description
            previous_intents: Intents from previous segments for context

        Returns:
            Prompt string
        """
        # Simplify operations for prompt (remove verbose details)
        simplified_ops = []
        for i, op in enumerate(segment):
            simplified = {
                "index": i,
                "type": op.get("type"),
                "url": op.get("url"),
                "page_title": op.get("page_title"),
            }

            # Add relevant element info
            element = op.get("element", {})
            if element.get("textContent"):
                simplified["element_text"] = element.get("textContent")
            if element.get("href"):
                simplified["element_href"] = element.get("href")
            if element.get("tagName"):
                simplified["element_tag"] = element.get("tagName")

            # Add relevant data
            data = op.get("data", {})
            if op.get("type") == "copy_action" and data.get("copiedText"):
                simplified["copied_text"] = data.get("copiedText")
            if op.get("type") == "select" and data.get("selectedText"):
                simplified["selected_text"] = data.get("selectedText")

            simplified_ops.append(simplified)

        # Build context from previous intents
        context_section = ""
        if previous_intents:
            context_section = "\n\nPREVIOUS INTENTS (from earlier segments):\n"
            for i, intent in enumerate(previous_intents, 1):
                context_section += f"{i}. {intent.description}\n"
            context_section += "\nUse these previous intents to understand the user's workflow and avoid duplicating or misinterpreting the current segment's purpose.\n"

        prompt = f"""You are an expert at analyzing user browser operations and extracting semantic intents.

Task Description: {task_description}{context_section}

CONTEXT - What is a Segment:
- A "segment" is a group of consecutive operations within the SAME page context (same URL)
- This segment has been pre-separated from other segments by URL-based navigation
- Operations in this segment all happened on the same page, but they may serve DIFFERENT purposes
- Your goal is to identify the REAL user intents, not to minimize or maximize the number of intents

IMPORTANT - Identify Meaningful vs Meaningless Operations:
- Some operations may be accidental clicks, UI interactions, or side effects that don't represent user intent
- Focus on operations that contribute to achieving the user's ACTUAL goal
- Example: If user wants to "extract product data", a click on product info area that doesn't lead to navigation may just be an accidental interaction - include it in the extraction intent or ignore it, don't create a separate intent for it
- Ask: "Does this operation represent a distinct user goal, or is it just a step/side-effect of achieving another goal?"

CRITICAL - Operation Classification Rules:

**Click Operations**:
1. **Click for Navigation** (links, menu items, category buttons):
   - Purpose: Navigate to a different page or section
   - Should be grouped into a NAVIGATION intent
   - Description should focus on WHERE the user wants to go, not HOW they click
   - Example: "Click menu → click Coffee category" → Intent: "Navigate to coffee category page"

2. **Click for Selection** (selecting content to copy):
   - Purpose: Select data for extraction
   - Should be grouped with subsequent copy/extract operations into EXTRACTION intent
   - Example: "Click price → copy" → Part of extraction intent, not a separate click intent

3. **Click for Interaction** (login buttons, form submissions, expand buttons):
   - Purpose: Trigger actions like login, submit form, reveal hidden content
   - Should be grouped as INTERACTION intent (if genuinely needed for the task)
   - Example: "Click login → enter credentials → click submit" → Intent: "Log into user account"

**Scroll Operations**:
1. **Scroll for Browsing** (just viewing content):
   - Purpose: User manually scrolling to view page content
   - These are usually MEANINGLESS and should be FILTERED OUT
   - Do NOT create separate scroll intents for these

2. **Scroll for Loading More Content** (lazy loading, infinite scroll):
   - Purpose: Trigger loading of additional content (e.g., more products)
   - These are MEANINGFUL and should be kept
   - Should be part of the extraction/navigation intent
   - Example: "Scroll down to load more products → extract all products" → Intent: "Extract all product listings with pagination"

**Key Principle**:
- Focus on the USER'S SEMANTIC GOAL, not the mechanical operations
- Clicks and scrolls are usually just MEANS to achieve a goal (navigate, extract, interact)
- The intent description should describe the GOAL, not the detailed UI operations

Operations Segment:
{json.dumps(simplified_ops, indent=2, ensure_ascii=False)}

Your job:
1. Analyze the operations and understand what the user is trying to accomplish
2. Extract the REAL intents from this segment - each intent represents a **distinct high-level user goal**
3. For each intent, provide:
   - description: A concise semantic description in English (1 sentence, describe WHAT the user wants to do, not HOW)
   - operation_indices: The indices of operations that belong to this intent (array of integers)

**CRITICAL - Generalize Time-Specific Descriptions:**

When describing navigation intents, DO NOT include specific dates, times, or time periods from the demonstration.
Instead, use generalized descriptions that will remain valid in the future.

Examples:
❌ BAD: "Navigate to the daily leaderboard page for October 29, 2025"
✅ GOOD: "Navigate to the current day's leaderboard"

❌ BAD: "Navigate to weekly leaderboard for week 44, 2025"
✅ GOOD: "Navigate to the current week's leaderboard"

❌ BAD: "Access the November 2025 reports"
✅ GOOD: "Access the current month's reports"

❌ BAD: "View products from 2025"
✅ GOOD: "View current year's products"

The operations will preserve the specific URLs/dates from the demonstration,
but the intent description should express the GENERAL goal.

IMPORTANT - Intent Granularity Guidelines:

**Core Principle: Group operations that serve the SAME user goal**

**When to COMBINE operations into ONE intent:**
- Multiple operations are different steps toward completing the SAME task
- Operations have the same target and purpose
- Example: Select title → copy → select price → copy → select rating → copy = ONE intent "Extract product information" (same purpose: data extraction, same target: product attributes)
- Example: Click menu → click category → navigate = ONE intent "Navigate to category page" (same purpose: navigation)

**When to SEPARATE into MULTIPLE intents:**
- Operations have clearly DIFFERENT purposes or goals
- There's a shift in what the user is trying to accomplish
- Example: Click expand button (purpose: reveal content) vs Select/copy data (purpose: extract data) = TWO different intents
- Example: Navigate to page (purpose: arrive at location) vs Extract data (purpose: collect information) = TWO different intents

**Key Question to Ask:**
"Are these operations different steps of ONE task, or are they SEPARATE tasks?"
- If answer is "one task" → combine into one intent
- If answer is "separate tasks" → split into multiple intents

**Examples of GOOD intent extraction:**

Scenario 1 - Navigation with clicks:
Operations: [navigate, click menu, click category link]
✓ GOOD: ONE intent "Navigate to coffee category page through menu"
✗ BAD: THREE intents (over-fragmented)

Scenario 2 - Data extraction on one page:
Operations: [navigate, select title, copy, select price, copy, select rating, copy]
✓ GOOD: TWO intents
  1. "Navigate to product detail page"
  2. "Extract product title, price and rating information"
✗ BAD: FOUR intents (navigate, extract title, extract price, extract rating) - too fragmented

Scenario 3 - Different purposes:
Operations: [navigate to homepage, click login, enter username, enter password, click submit]
✓ GOOD: TWO intents
  1. "Navigate to website homepage"
  2. "Log into user account"
✗ BAD: ONE intent "Navigate and login" - these are different purposes

Output format (JSON array):
```json
[
  {{
    "description": "Navigate to the product category page through menu",
    "operation_indices": [0, 1, 2]
  }},
  {{
    "description": "Extract product information including title, price and ratings",
    "operation_indices": [3, 4, 5, 6, 7, 8]
  }}
]
```

Now analyze the operations above and generate the JSON output:"""

        return prompt

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM response to extract intent data

        Args:
            response: LLM response string (may contain markdown code blocks)

        Returns:
            List of intent data dictionaries

        Example:
            >>> response = '''```json
            ... [{"description": "Navigate", "operation_indices": [0, 1]}]
            ... ```'''
            >>> data = extractor._parse_llm_response(response)
            >>> data[0]["description"]
            'Navigate'
        """
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```json\s*\n(.*?)\n```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON array directly
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response

        try:
            data = json.loads(json_str)
            if not isinstance(data, list):
                raise ValueError("Expected JSON array")
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {response}")
