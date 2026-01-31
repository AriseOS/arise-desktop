"""Domain Extractor - Extracts domain information from workflow data.

This module uses LLM to identify domains (apps/websites) from user workflow data.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.ontology.domain import Domain
from src.cloud_backend.memgraph.services.llm import LLMClient, LLMMessage, LLMResponse
from src.cloud_backend.memgraph.thinker.prompts.domain_extraction_prompt import (
    DomainExtractionInput,
    DomainExtractionPrompt,
)

logger = logging.getLogger(__name__)


class DomainExtractionResult:
    """Result of domain extraction.

    Attributes:
        domains: List of extracted Domain objects
        domain_mapping: Mapping from URLs to domain objects
        extraction_metadata: Metadata about extraction process
        llm_response: Raw LLM response
        timestamp: When extraction was performed
    """

    def __init__(
        self,
        domains: List[Domain],
        domain_mapping: Dict[str, Domain],
        extraction_metadata: Dict[str, Any],
        llm_response: str
    ):
        """Initialize extraction result.

        Args:
            domains: List of Domain objects
            domain_mapping: URL to Domain mapping
            extraction_metadata: Extraction metadata
            llm_response: Raw LLM response
        """
        self.domains = domains
        self.domain_mapping = domain_mapping
        self.extraction_metadata = extraction_metadata
        self.llm_response = llm_response
        self.timestamp = datetime.now()


class DomainExtractor:
    """Extractor for identifying domains from workflow data using LLM.

    Uses LLM to analyze workflow events and identify distinct domains
    (apps or websites) that the user interacted with.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str = "gpt-4"
    ):
        """Initialize DomainExtractor.

        Args:
            llm_client: LLM client for extraction (required)
            model_name: Name of LLM model to use

        Raises:
            ValueError: If llm_client is None
        """
        if not llm_client:
            raise ValueError("LLM client is required for DomainExtractor")

        self.llm_client = llm_client
        self.model_name = model_name
        self.prompt = DomainExtractionPrompt()

    def extract_domains(
        self,
        workflow_data: List[Dict[str, Any]],
        user_id: Optional[str] = None
    ) -> DomainExtractionResult:
        """Extract domains from workflow data using LLM.

        Args:
            workflow_data: List of workflow event dictionaries
            user_id: User ID (optional)

        Returns:
            DomainExtractionResult containing extracted domains

        Raises:
            ValueError: If input is invalid
        """
        if not workflow_data:
            raise ValueError("Workflow data is empty")

        # Extract all unique URLs from workflow data
        urls = set()
        for event in workflow_data:
            page_url = event.get("page_url") or event.get("url", "")
            if page_url:
                urls.add(page_url)

        if not urls:
            raise ValueError("No URLs found in workflow data")

        # Build prompt using prompt object
        prompt_input = DomainExtractionInput(urls=list(urls))

        # Validate input
        if not self.prompt.validate_input(prompt_input):
            raise ValueError("Invalid prompt input: no URLs provided")

        user_prompt = self.prompt.build_prompt(prompt_input)
        system_prompt = self.prompt.get_system_prompt()

        # Call LLM
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]

        response: LLMResponse = self.llm_client.generate(
            messages,
            temperature=0.1,
            max_tokens=4000
        )

        # Parse response using prompt object
        parsed_output = self.prompt.parse_response(response.content)

        # Validate output
        if not self.prompt.validate_output(parsed_output):
            raise ValueError("LLM returned invalid output: no domains extracted")

        # Create Domain objects from parsed output
        domains = []
        domain_mapping = {}
        current_time = int(datetime.now().timestamp() * 1000)

        for domain_data in parsed_output.domains:
            try:
                domain = Domain(
                    domain_url=domain_data.domain_url,
                    domain_name=domain_data.domain_name,
                    domain_type=domain_data.domain_type,
                    created_at=current_time,
                    user_id=user_id,
                    attributes=domain_data.attributes
                )
                domains.append(domain)

                # Add to mapping: domain_url -> Domain
                domain_mapping[domain.domain_url] = domain

                # Also map all related URLs -> Domain
                for related_url in domain_data.related_urls:
                    domain_mapping[related_url] = domain

            except Exception as domain_err:
                logger.warning(f" Failed to create domain from data: {str(domain_err)}")
                continue

        if not domains:
            raise ValueError("No valid domains could be created from LLM output")

        # Build metadata
        metadata = {
            "extraction_method": "llm",
            "domain_count": len(domains),
            "llm_model": self.model_name,
            "total_events": len(workflow_data),
            "unique_urls": len(urls),
            "url_to_domain_mappings": len(domain_mapping)
        }

        return DomainExtractionResult(
            domains=domains,
            domain_mapping=domain_mapping,
            extraction_metadata=metadata,
            llm_response=response.content
        )


__all__ = [
    "DomainExtractor",
    "DomainExtractionResult",
]
