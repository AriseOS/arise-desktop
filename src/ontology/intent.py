"""Intent module - Atomic intent unit.

Intent represents an atomic intent unit extracted from browser or APP events.
The complete event is a JSON object.
"""

from enum import Enum
from typing import Any
from typing import Dict
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class IntentType(Enum):
    """Enumeration of atomic intent types.

    Defines all possible atomic-level user operation types.
    """

    # Click operations
    CLICK_ELEMENT = 'ClickElement'
    DOUBLE_CLICK = 'DoubleClick'
    RIGHT_CLICK = 'RightClick'

    # Text operations
    TYPE_TEXT = 'TypeText'
    COPY_TEXT = 'CopyText'
    CUT_TEXT = 'CutText'
    PASTE_TEXT = 'PasteText'
    SELECT_TEXT = 'SelectText'
    DELETE_TEXT = 'DeleteText'

    # Navigation operations
    NAVIGATE_TO = 'NavigateTo'
    NAVIGATE_PAGE = 'NavigatePage'
    GO_BACK = 'GoBack'
    GO_FORWARD = 'GoForward'
    REFRESH_PAGE = 'RefreshPage'
    SCROLL_PAGE = 'ScrollPage'

    # Form operations
    FILL_INPUT = 'FillInput'
    SELECT_OPTION = 'SelectOption'
    CHECK_CHECKBOX = 'CheckCheckbox'
    UNCHECK_CHECKBOX = 'UncheckCheckbox'
    SUBMIT_FORM = 'SubmitForm'

    # Drag and drop operations
    DRAG_ELEMENT = 'DragElement'
    DROP_ELEMENT = 'DropElement'

    # Hover operations
    HOVER_ELEMENT = 'HoverElement'

    # Window operations
    OPEN_TAB = 'OpenTab'
    CLOSE_TAB = 'CloseTab'
    SWITCH_TAB = 'SwitchTab'

    # Keyboard operations
    PRESS_KEY = 'PressKey'
    KEY_COMBINATION = 'KeyCombination'

    # Other operations
    UNKNOWN = 'Unknown'


class Intent(BaseModel):
    """Intent - Atomic intent unit.

    Represents an atomic intent unit extracted from browser or APP events.
    This is the fundamental data unit of the memory system, representing
    a single atomic-level user operation.

    Attributes:
        type: Intent type.
        timestamp: Timestamp in milliseconds.
        page_url: Page URL.
        page_title: Page title (optional).
        element_id: Element ID (optional).
        element_tag: Element tag (optional).
        element_class: Element CSS class (optional).
        xpath: XPath (optional).
        css_selector: CSS selector (optional).
        text: Element text content (optional).
        value: Input or selected value (optional).
        coordinates: Coordinates dict with x, y (optional).
        user_id: User ID (optional).
        session_id: Session ID (optional).
        attributes: Additional attributes.
        confidence_score: Confidence score for LLM extraction (optional).
    """

    # Core attributes
    type: IntentType = Field(..., description='Intent type')
    timestamp: int = Field(..., description='Timestamp in milliseconds')

    # Page information
    page_url: str = Field(..., description='Page URL')
    page_title: Optional[str] = Field(
        default=None, description='Page title')

    # Element information
    element_id: Optional[str] = Field(default=None, description='Element ID')
    element_tag: Optional[str] = Field(
        default=None, description='Element tag')
    element_class: Optional[str] = Field(
        default=None, description='Element CSS class')
    xpath: Optional[str] = Field(default=None, description='XPath')
    css_selector: Optional[str] = Field(
        default=None, description='CSS selector')

    # Content data
    text: Optional[str] = Field(
        default=None, description='Element text content')
    value: Optional[str] = Field(
        default=None, description='Input or selected value')

    # Coordinate information
    coordinates: Optional[Dict[str, float]] = Field(
        default=None, description='Coordinates {x, y}')

    # User session information
    user_id: Optional[str] = Field(default=None, description='User ID')
    session_id: Optional[str] = Field(default=None, description='Session ID')

    # Extended attributes
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description='Additional attributes')

    # Confidence (for LLM extraction)
    confidence_score: Optional[float] = Field(
        default=None, description='Confidence score', ge=0.0, le=1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the intent.
        """
        data = self.model_dump()
        data['type'] = self.type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Intent':
        """Create instance from dictionary.

        Args:
            data: Dictionary containing intent data.

        Returns:
            Intent instance.
        """
        if isinstance(data.get('type'), str):
            data['type'] = IntentType(data['type'])
        return cls(**data)


# Backward compatibility aliases
AtomicIntent = Intent
AtomicIntentType = IntentType


__all__ = [
    'Intent',
    'IntentType',
    'AtomicIntent',  # Backward compatibility
    'AtomicIntentType',  # Backward compatibility
]
