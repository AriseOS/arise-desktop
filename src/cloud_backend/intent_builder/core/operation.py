"""
Shared Operation data structure for Intent Builder

This module provides a unified Operation definition used by both Intent and MetaFlow.
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ElementInfo(BaseModel):
    """DOM element information

    Captures details about a DOM element for browser automation.
    """
    xpath: Optional[str] = None
    tagName: Optional[str] = Field(None, alias="tagName")
    className: Optional[str] = Field(None, alias="className")
    id: Optional[str] = None
    textContent: Optional[str] = Field(None, alias="textContent")
    href: Optional[str] = None
    src: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    value: Optional[str] = None

    class Config:
        populate_by_name = True


class Operation(BaseModel):
    """Unified Operation definition for Intent and MetaFlow

    Represents a single user operation (navigate, click, extract, etc.)
    with full context information including DOM details.

    Note: type accepts any string to support flexible operation types.
    The WorkflowGenerator is responsible for interpreting and mapping operations.

    Attributes:
        type: Operation type (navigate, click, input, select, copy_action, extract, wait, scroll, etc.)
        timestamp: Human-readable timestamp string (e.g., "2025-10-10 17:52:57")
        url: Page URL
        page_title: Page title
        element: DOM element information
        data: Operation-specific data (e.g., click coordinates, selected text, etc.)
        target: For extract operations - field name
        value: For extract operations - extracted value
        duration: For wait operations - wait duration
        direction: For scroll operations - scroll direction
        distance: For scroll operations - scroll distance
        params: Additional parameters for various operations
    """
    type: str  # Accept any operation type as string
    timestamp: Optional[str] = None  # Human-readable timestamp
    url: Optional[str] = None
    page_title: Optional[str] = Field(None, alias="page_title")

    # DOM element information
    element: Optional[ElementInfo] = None

    # Operation-specific data
    data: Optional[Dict[str, Any]] = None  # Generic data field
    target: Optional[str] = None  # For extract: field name
    value: Optional[Any] = None   # For extract: actual extracted value
    duration: Optional[int] = None  # For wait
    direction: Optional[str] = None  # For scroll
    distance: Optional[int] = None  # For scroll
    params: Optional[Dict[str, Any]] = None  # For store and other params

    class Config:
        populate_by_name = True
        # Allow extra fields for future extensibility
        extra = "allow"
