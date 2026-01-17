"""
Tavily Agent - Web search and research agent via Tavily API
"""
import logging
from typing import Any, Dict, List, Optional

try:
    from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
    from ..core.schemas import (
        AgentContext, AgentInput, AgentOutput
    )
except ImportError:
    # Absolute import as fallback
    from base_agent.agents.base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
    from base_agent.core.schemas import (
        AgentContext, AgentInput, AgentOutput
    )


class TavilyAgent(BaseStepAgent):
    """Web search agent powered by Tavily API

    Supports operations:
    - search: Basic web search, returns list of URLs with snippets

    Note: research operation is disabled (too expensive)
    """

    INPUT_SCHEMA = InputSchema(
        description="Tavily agent for web search",
        fields={
            "operation": FieldSchema(
                type="str",
                required=True,
                enum=["search"],  # research disabled
                description="Operation type: 'search' for web search"
            ),
            "query": FieldSchema(
                type="str",
                required=True,
                description="Search query"
            ),
            # ============ search operation parameters ============
            "max_results": FieldSchema(
                type="int",
                required=False,
                description="Number of results to return (default: 10)"
            ),
            "search_depth": FieldSchema(
                type="str",
                required=False,
                enum=["basic", "advanced"],
                description="Search depth: 'basic' (default), 'advanced' (comprehensive)"
            ),
            "topic": FieldSchema(
                type="str",
                required=False,
                enum=["general", "news", "finance"],
                description="Search category: 'general' (default), 'news', 'finance'"
            ),
            "days": FieldSchema(
                type="int",
                required=False,
                description="Limit search to results from the past N days (e.g., days=3 for last 3 days)"
            ),
            "time_range": FieldSchema(
                type="str",
                required=False,
                enum=["day", "week", "month", "year"],
                description="Time range filter: 'day', 'week', 'month', 'year'"
            ),
            "include_domains": FieldSchema(
                type="list",
                required=False,
                items_type="str",
                description="Only include results from these domains"
            ),
            "exclude_domains": FieldSchema(
                type="list",
                required=False,
                items_type="str",
                description="Exclude results from these domains"
            ),
            "include_answer": FieldSchema(
                type="bool",
                required=False,
                description="Include LLM-generated answer summary"
            ),
            "include_raw_content": FieldSchema(
                type="bool",
                required=False,
                description="Include raw page content"
            ),
            "include_images": FieldSchema(
                type="bool",
                required=False,
                description="Include image results"
            ),
            "country": FieldSchema(
                type="str",
                required=False,
                description="Country code for localized results (e.g., 'us', 'cn', 'jp')"
            ),
            # ============ research operation parameters (DISABLED) ============
            # "stream": FieldSchema(
            #     type="bool",
            #     required=False,
            #     description="Enable streaming for research operation (default: false)"
            # ),
            # "model": FieldSchema(
            #     type="str",
            #     required=False,
            #     enum=["mini", "pro", "auto"],
            #     description="Research model: 'mini' (fast), 'pro' (comprehensive), 'auto' (default)"
            # ),
            # "citation_format": FieldSchema(
            #     type="str",
            #     required=False,
            #     enum=["numbered", "mla", "apa", "chicago"],
            #     description="Citation format for research output (default: 'numbered')"
            # ),
        },
        examples=[
            {
                "operation": "search",
                "query": "AI news",
                "max_results": 10,
                "days": 3,
                "topic": "news"
            },
            {
                "operation": "search",
                "query": "machine learning tutorials",
                "search_depth": "advanced",
                "include_answer": True
            },
        ]
    )

    def __init__(self):
        metadata = AgentMetadata(
            name="tavily_agent",
            description="Web search and research agent powered by Tavily API",
        )
        super().__init__(metadata)
        self.cloud_client = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize Tavily Agent"""
        if not context.agent_instance:
            return False

        # Get cloud_client from agent_instance
        if not hasattr(context.agent_instance, 'cloud_client') or not context.agent_instance.cloud_client:
            if context.logger:
                context.logger.error("CloudClient not available")
            return False

        self.cloud_client = context.agent_instance.cloud_client
        self.is_initialized = True
        return True

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        if isinstance(input_data, AgentInput):
            data = input_data.data
        elif isinstance(input_data, dict):
            data = input_data.get("data", input_data)
        else:
            return False

        # Check required fields
        if "operation" not in data or "query" not in data:
            return False

        # Validate operation value
        if data["operation"] not in ["search", "research"]:
            return False

        return True

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute Tavily search or research operation"""
        operation = "unknown"  # Initialize before try block to avoid NameError in except
        try:
            # Ensure input is AgentInput type
            if isinstance(input_data, dict):
                agent_input = AgentInput(**input_data)
            else:
                agent_input = input_data

            # Extract parameters
            operation = agent_input.data.get("operation", "unknown")
            query = agent_input.data.get("query")

            self.logger.info(f"[TavilyAgent] Executing {operation}: {query[:50]}...")

            # Send start log to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"🔍 Starting Tavily {operation}...",
                        {"query": query[:100], "operation": operation}
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to send log callback: {e}")

            if operation == "search":
                result = await self._execute_search(agent_input.data, context)
            # elif operation == "research":  # DISABLED - too expensive
            #     result = await self._execute_research(agent_input.data, context)
            else:
                raise ValueError(f"Unknown operation: {operation}. Only 'search' is supported.")

            # Note: Detailed success logs are sent from _execute_search/_execute_research

            return AgentOutput(
                success=True,
                data={"result": result},
                message=f"Tavily {operation} completed"
            )

        except Exception as e:
            self.logger.error(f"[TavilyAgent] {operation} failed: {str(e)}")
            import traceback
            self.logger.error(f"  Traceback: {traceback.format_exc()}")

            if context.logger:
                context.logger.error(f"Tavily {operation} failed: {str(e)}")

            return AgentOutput(
                success=False,
                data={},
                message=f"Tavily {operation} failed: {str(e)}"
            )

    async def _execute_search(self, data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Execute Tavily search operation"""
        query = data.get("query")
        max_results = data.get("max_results", 10)
        search_depth = data.get("search_depth", "basic")
        topic = data.get("topic")
        days = data.get("days")
        time_range = data.get("time_range")
        include_domains = data.get("include_domains")
        exclude_domains = data.get("exclude_domains")
        include_answer = data.get("include_answer")
        include_raw_content = data.get("include_raw_content")
        include_images = data.get("include_images")
        country = data.get("country")

        self.logger.info(f"[TavilyAgent] Search: query={query[:50]}, max={max_results}, depth={search_depth}, topic={topic}, days={days}")

        # Send search parameters to frontend
        if context and context.log_callback:
            try:
                search_params = {
                    "query": query,
                    "max_results": max_results,
                    "search_depth": search_depth,
                }
                if topic:
                    search_params["topic"] = topic
                if days:
                    search_params["days"] = days
                await context.log_callback(
                    "info",
                    f"🌐 Searching web: {query[:80]}...",
                    search_params
                )
            except Exception as e:
                self.logger.warning(f"Failed to send log callback: {e}")

        # Call cloud client
        response = await self.cloud_client.tavily_search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            topic=topic,
            days=days,
            time_range=time_range,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            include_images=include_images,
            country=country
        )

        results = response.get("results", [])

        if not results:
            self.logger.warning(f"[TavilyAgent] No results found for query: {query[:100]}")
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "warning",
                        f"⚠️ No results found for: {query[:50]}...",
                        {"query": query}
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to send warning callback: {e}")
        else:
            self.logger.info(f"[TavilyAgent] Search returned {len(results)} results")
            # Send search results summary to frontend
            if context and context.log_callback:
                try:
                    # Build results preview (first 3 results)
                    results_preview = []
                    for r in results[:3]:
                        results_preview.append({
                            "title": r.get("title", "")[:60],
                            "url": r.get("url", ""),
                        })

                    result_details = {
                        "total_results": len(results),
                        "results_preview": results_preview,
                    }
                    if response.get("answer"):
                        result_details["has_answer"] = True
                        result_details["answer_preview"] = response["answer"][:200] + "..." if len(response.get("answer", "")) > 200 else response.get("answer", "")

                    await context.log_callback(
                        "info",
                        f"📋 Found {len(results)} results",
                        result_details
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to send results callback: {e}")

        # Return full response (includes answer, images if requested)
        return response

    # ============================================================
    # Research operation - DISABLED (too expensive)
    # ============================================================
    # async def _execute_research(self, data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
    #     """Execute Tavily research operation"""
    #     query = data.get("query")
    #     stream = data.get("stream", False)
    #     model = data.get("model")
    #     citation_format = data.get("citation_format")
    #
    #     self.logger.info(f"[TavilyAgent] Research: query={query[:50]}, stream={stream}, model={model}")
    #
    #     # Send research start to frontend
    #     if context and context.log_callback:
    #         try:
    #             research_params = {
    #                 "query": query,
    #                 "stream": stream,
    #             }
    #             if model:
    #                 research_params["model"] = model
    #             await context.log_callback(
    #                 "info",
    #                 f"📚 Starting deep research: {query[:80]}...",
    #                 research_params
    #             )
    #         except Exception as e:
    #             self.logger.warning(f"Failed to send log callback: {e}")
    #
    #     # Progress callback for streaming
    #     async def progress_callback(level: str, message: str, details: Dict[str, Any]):
    #         if context and context.log_callback:
    #             try:
    #                 await context.log_callback(level, message, details)
    #             except Exception as e:
    #                 self.logger.warning(f"Failed to send progress: {e}")
    #
    #     # Call cloud client
    #     response = await self.cloud_client.tavily_research(
    #         query=query,
    #         stream=stream,
    #         model=model,
    #         citation_format=citation_format,
    #         progress_callback=progress_callback if stream else None
    #     )
    #
    #     self.logger.info(f"[TavilyAgent] Research completed")
    #
    #     # Send research completion to frontend
    #     if context and context.log_callback:
    #         try:
    #             report = response.get("report", "") or response.get("content", "")
    #             sources = response.get("sources", [])
    #             result_details = {
    #                 "report_length": len(report),
    #                 "sources_count": len(sources),
    #             }
    #             if report:
    #                 result_details["report_preview"] = report[:300] + "..." if len(report) > 300 else report
    #             if sources:
    #                 result_details["sources_preview"] = [{"title": s.get("title", ""), "url": s.get("url", "")} for s in sources[:3]]
    #
    #             await context.log_callback(
    #                 "info",
    #                 f"📝 Research report generated ({len(report)} chars, {len(sources)} sources)",
    #                 result_details
    #             )
    #         except Exception as e:
    #             self.logger.warning(f"Failed to send completion callback: {e}")
    #
    #     return response

    def _get_result_summary(self, operation: str, result: Any) -> str:
        """Get a summary of the result for logging"""
        if operation == "search":
            if isinstance(result, dict):
                results_count = len(result.get("results", []))
                has_answer = "answer" in result and result["answer"]
                has_images = "images" in result and result["images"]
                parts = [f"{results_count} results"]
                if has_answer:
                    parts.append("with answer")
                if has_images:
                    parts.append(f"{len(result['images'])} images")
                return ", ".join(parts)
            elif isinstance(result, list):
                return f"{len(result)} search results"
            return "Search completed"
        # elif operation == "research":  # DISABLED
        #     if isinstance(result, dict):
        #         report_len = len(result.get("report", "") or result.get("content", ""))
        #         sources_count = len(result.get("sources", []))
        #         return f"Report ({report_len} chars), {sources_count} sources"
        #     return "Research completed"
        return "Completed"
