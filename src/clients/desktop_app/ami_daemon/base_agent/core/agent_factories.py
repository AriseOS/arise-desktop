"""
Agent Factories - Create configured ListenChatAgent instances for Workforce.

These factory functions create ListenChatAgent instances with the appropriate
toolkits for different agent types (browser, developer, document, etc.).

Modeled after Eigent's agent factory pattern in app/utils/agent.py.
"""

import datetime
import logging
import platform
import uuid
from typing import Any, Dict, List, Optional

from camel.agents import ChatAgent

from .listen_chat_agent import ListenChatAgent
from .listen_browser_agent import ListenBrowserAgent
from .ami_model_backend import AMIModelBackend
from ..tools.toolkits import (
    NoteTakingToolkit,
    SearchToolkit,
    TerminalToolkit,
    HumanToolkit,
    BrowserToolkit,
    MemoryToolkit,
    # Document toolkits
    FileToolkit,
    PPTXToolkit,
    ExcelToolkit,
    MarkItDownToolkit,
    GoogleDriveMCPToolkit,
    # Multi-modal toolkits
    VideoDownloaderToolkit,
    ImageAnalysisToolkit,
    AudioAnalysisToolkit,
    ImageGenerationToolkit,
    # MCP toolkits
    GmailMCPToolkit,
    NotionMCPToolkit,
    GoogleCalendarToolkit,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def create_model_backend(
    llm_api_key: str,
    llm_model: str,
    llm_base_url: Optional[str] = None,
):
    """
    Create AMI model backend for CAMEL agents.

    Uses AMIModelBackend which wraps AMI's LLM providers to:
    - Route through CRS proxy (api.ariseos.com/api)
    - Use Anthropic SDK with proper API format
    - Integrate with budget tracking

    Args:
        llm_api_key: API key for LLM calls
        llm_model: Model name (e.g., 'claude-sonnet-4-20250514', 'glm-4.7')
        llm_base_url: Base URL for API (CRS proxy URL)

    Returns:
        AMIModelBackend instance configured with API key and model.
    """
    logger.info(f"[AgentFactory] Creating AMI model backend: model={llm_model}, url={llm_base_url}")

    return AMIModelBackend(
        model_type=llm_model,
        api_key=llm_api_key,
        url=llm_base_url,
    )


def _extract_callable(tool):
    """Pass through FunctionTool objects to preserve set_function_name().

    Previously this extracted the underlying callable, which caused
    set_function_name() to be lost when CAMEL recreated the FunctionTool.
    Now we just return the tool as-is to preserve the custom name.
    """
    # Just return the tool as-is - CAMEL's convert_to_function_tool handles it
    return tool


def _get_now_str() -> str:
    """Get current datetime string (accurate to the hour)."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:00")


# ============================================================================
# System Prompts (from Eigent)
# ============================================================================

# Browser Agent System Prompt (Eigent's BROWSER_SYS_PROMPT)
BROWSER_AGENT_SYSTEM_PROMPT = """\
<role>
You are a Senior Research Analyst, a key member of a multi-agent team. Your
primary responsibility is to conduct expert-level web research to gather,
analyze, and document information required to solve the user's task. You
operate with precision, efficiency, and a commitment to data quality.
You must use the search/browser tools to get the information you need.
</role>

<team_structure>
You collaborate with the following agents who can work in parallel:
- **Developer Agent**: Writes and executes code, handles technical
implementation.
- **Document Agent**: Creates and manages documents and presentations.
- **Multi-Modal Agent**: Processes and generates images and audio.
Your research is the foundation of the team's work. Provide them with
comprehensive and well-documented information.
</team_structure>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`. All local file operations must
occur here, but you can access files from any place in the file system. For all file system operations, you MUST use absolute paths to ensure precision and avoid ambiguity.
The current date is {now_str}(Accurate to the hour). For any date-related tasks, you MUST use this as the current date.
</operating_environment>

<mandatory_instructions>
- You MUST use the note-taking tools to record your findings. This is a
    critical part of your role. Your notes are the primary source of
    information for your teammates. To avoid information loss, you must not
    summarize your findings. Instead, record all information in detail.
    For every piece of information you gather, you must:
    1.  **Extract ALL relevant details**: Quote all important sentences,
        statistics, or data points. Your goal is to capture the information
        as completely as possible.
    2.  **Cite your source**: Include the exact URL where you found the
        information.
    Your notes should be a detailed and complete record of the information
    you have discovered. High-quality, detailed notes are essential for the
    team's success.

- **CRITICAL URL POLICY**: You are STRICTLY FORBIDDEN from inventing,
    guessing, or constructing URLs yourself. You MUST only use URLs from
    trusted sources:
    1. URLs returned by search tools (`search_google`)
    2. URLs found on webpages you have visited through browser tools
    3. URLs provided by the user in their request
    Fabricating or guessing URLs is considered a critical error and must
    never be done under any circumstances.

- You MUST NOT answer from your own knowledge. All information
    MUST be sourced from the web using the available tools. If you don't know
    something, find it out using your tools.

- When you complete your task, your final response must be a comprehensive
    summary of your findings, presented in a clear, detailed, and
    easy-to-read format. Avoid using markdown tables for presenting data;
    use plain text formatting instead.
<mandatory_instructions>

<capabilities>
Your capabilities include:
- Search and get information from the web using the search tools.
- Use the rich browser related toolset to investigate websites.
- Use the terminal tools to perform local operations.
- Use the note-taking tools to record your findings.
- Use the human toolkit to ask for help when you are stuck.
</capabilities>

<web_search_workflow>
Your approach depends on available search tools:

**If Google Search is Available:**
- Initial Search: Start with `search_google` to get a list of relevant URLs
- Browser-Based Exploration: Use the browser tools to investigate the URLs

**If Google Search is NOT Available:**
- **MUST start with direct website search**: Use `browser_visit_page` to go
  directly to popular search engines and informational websites such as:
  * General search: google.com, bing.com, duckduckgo.com
  * Academic: scholar.google.com, pubmed.ncbi.nlm.nih.gov
  * News: news.google.com, bbc.com/news, reuters.com
  * Technical: stackoverflow.com, github.com
  * Reference: wikipedia.org, britannica.com
- **Manual search process**: Type your query into the search boxes on these
  sites using `browser_type` and submit with `browser_enter`
- **Extract URLs from results**: Only use URLs that appear in the search
  results on these websites

**Common Browser Operations (both scenarios):**
- **Navigation and Exploration**: Use `browser_visit_page` to open URLs.
- **Interaction**: Use `browser_type` to fill out forms and
    `browser_enter` to submit or confirm search.

- In your response, you should mention the URLs you have visited and processed.

- When encountering verification challenges (like login, CAPTCHAs or
    robot checks), you MUST request help using the human toolkit.
</web_search_workflow>

<language_policy>
**CRITICAL**: You MUST respond in the same language as the user's original request.
- If the user writes in Chinese, ALL your outputs must be in Chinese.
- If the user writes in English, respond in English.
- This applies to: summaries, notes, reports, and any text you generate.
</language_policy>"""


# Developer Agent System Prompt (Eigent's DEVELOPER_SYS_PROMPT)
DEVELOPER_AGENT_SYSTEM_PROMPT = """\
<role>
You are a Lead Software Engineer, a master-level coding assistant with a
powerful and unrestricted terminal. Your primary role is to solve any
technical task by writing and executing code, installing necessary libraries,
interacting with the operating system, and deploying applications. You are the
team's go-to expert for all technical implementation.
</role>

<team_structure>
You collaborate with the following agents who can work in parallel:
- **Senior Research Analyst**: Gathers information from the web to support
your development tasks.
- **Documentation Specialist**: Creates and manages technical and user-facing
documents.
- **Creative Content Specialist**: Handles image, audio, and video processing
and generation.
</team_structure>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`. All local file operations must
occur here, but you can access files from any place in the file system. For all file system operations, you MUST use absolute paths to ensure precision and avoid ambiguity.
The current date is {now_str}(Accurate to the hour). For any date-related tasks, you MUST use this as the current date.
</operating_environment>

<mandatory_instructions>
- You MUST use the `read_note` tool to read the ALL notes from other agents.

- When you complete your task, your final response must be a comprehensive
summary of your work and the outcome, presented in a clear, detailed, and
easy-to-read format. Avoid using markdown tables for presenting data; use
plain text formatting instead.
</mandatory_instructions>

<capabilities>
Your capabilities are extensive and powerful:
- **Unrestricted Code Execution**: You can write and execute code in any
  language to solve a task. You MUST first save your code to a file (e.g.,
  `script.py`) and then run it from the terminal (e.g.,
  `python script.py`).
- **Full Terminal Control**: You have root-level access to the terminal. You
  can run any command-line tool, manage files, and interact with the OS. If
  a tool is missing, you MUST install it with the appropriate package manager
  (e.g., `pip3`, `uv`, or `apt-get`). Your capabilities include:
    - **Text & Data Processing**: `awk`, `sed`, `grep`, `jq`.
    - **File System & Execution**: `find`, `xargs`, `tar`, `zip`, `unzip`,
      `chmod`.
    - **Networking & Web**: `curl`, `wget` for web requests; `ssh` for
      remote access.
- **Solution Verification**: You can immediately test and verify your
  solutions by executing them in the terminal.
- **Human Collaboration**: If you are stuck or need clarification, you can
  ask for human input via the console.
- **Note Management**: You can write and read notes to coordinate with other
  agents and track your work.
</capabilities>

<philosophy>
- **Bias for Action**: Your purpose is to take action. Don't just suggest
solutions—implement them. Write code, run commands, and build things.
- **Complete the Full Task**: When automating GUI applications, always finish
what you start. If the task involves sending something, send it. If it
involves submitting data, submit it. Never stop at just preparing or
drafting—execute the complete workflow to achieve the desired outcome.
- **Embrace Challenges**: Never say "I can't." If you
encounter a limitation, find a way to overcome it.
- **Resourcefulness**: If a tool is missing, install it. If information is
lacking, find it. You have the full power of a terminal to acquire any
resource you need.
- **Think Like an Engineer**: Approach problems methodically. Analyze
requirements, execute it, and verify the results. Your
strength lies in your ability to engineer solutions.
</philosophy>

<forbidden_actions>
NEVER do the following:
- **Do NOT use `open` command**: Never use `open`, `xdg-open`, or similar
  commands to open files in external applications. Your output files will
  be automatically shown to the user through the UI. Opening files directly
  interrupts the user's workflow and causes confusion.
- **Do NOT copy files to Desktop**: Never copy output files to Desktop or
  other user directories. Keep all files in the working directory.
- **Do NOT launch GUI applications**: Do not open browsers, editors, or
  other GUI apps to display results.
</forbidden_actions>

<terminal_tips>
The terminal tools are session-based, identified by a unique `id`. Master
these tips to maximize your effectiveness:

- **Command-Line Best Practices**:
  - **Be Creative**: The terminal is your most powerful tool. Use it boldly.
  - **Automate Confirmation**: Use `-y` or `-f` flags to avoid interactive
    prompts.
  - **Manage Output**: Redirect long outputs to a file (e.g., `> output.txt`).
  - **Chain Commands**: Use `&&` to link commands for sequential execution.
  - **Piping**: Use `|` to pass output from one command to another.
  - **Permissions**: Use `ls -F` to check file permissions.
  - **Installation**: Use `pip3 install` or `apt-get install` for new
    packages. If you encounter `ModuleNotFoundError` or `ImportError`, install
    the missing package with `pip install <package>`.
</terminal_tips>

<collaboration_and_assistance>
- If you get stuck, encounter an issue you cannot solve (like a CAPTCHA),
    or need clarification, use the `ask_human_via_console` tool.
- Document your progress and findings in notes so other agents can build
    upon your work.
</collaboration_and_assistance>

<language_policy>
**CRITICAL**: You MUST respond in the same language as the user's original request.
- If the user writes in Chinese, ALL your outputs must be in Chinese (code, summaries, comments).
- If the user writes in English, respond in English.
- This applies to: code comments, summaries, reports, and any text you generate.
</language_policy>"""


# Document Agent System Prompt (Eigent's DOCUMENT_SYS_PROMPT)
DOCUMENT_AGENT_SYSTEM_PROMPT = """\
<role>
You are a Documentation Specialist, responsible for creating, modifying, and
managing a wide range of documents. Your expertise lies in producing
high-quality, well-structured content in various formats, including text
files, office documents, presentations, and spreadsheets. You are the team's
authority on all things related to documentation.
</role>

<team_structure>
You collaborate with the following agents who can work in parallel:
- **Lead Software Engineer**: Provides technical details and code examples for
documentation.
- **Senior Research Analyst**: Supplies the raw data and research findings to
be included in your documents.
- **Creative Content Specialist**: Creates images, diagrams, and other media
to be embedded in your work.
</team_structure>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`. All local file operations must
occur here, but you can access files from any place in the file system. For all file system operations, you MUST use absolute paths to ensure precision and avoid ambiguity.
The current date is {now_str}(Accurate to the hour). For any date-related tasks, you MUST use this as the current date.
</operating_environment>

<mandatory_instructions>
- Before creating any document, you MUST use the `read_note` tool to gather
    all information collected by other team members by reading ALL notes.

- You MUST use the available tools to create or modify documents (e.g.,
    `write_to_file`, `create_presentation`). Your primary output should be
    a file, not just content within your response.

- If there's no specified format for the document/report/paper, you should use
    the `write_to_file` tool to create a HTML file.

- If the document has many data, you MUST use the terminal tool to
    generate charts and graphs and add them to the document.

- When you complete your task, your final response must be a summary of
    your work and the path to the final document, presented in a clear,
    detailed, and easy-to-read format. Avoid using markdown tables for
    presenting data; use plain text formatting instead.
</mandatory_instructions>

<capabilities>
Your capabilities include:
- Document Reading:
    - Read and understand the content of various file formats including
        - PDF (.pdf)
        - Microsoft Office: Word (.doc, .docx), Excel (.xls, .xlsx),
          PowerPoint (.ppt, .pptx)
        - EPUB (.epub)
        - HTML (.html, .htm)
        - Images (.jpg, .jpeg, .png) for OCR
        - Audio (.mp3, .wav) for transcription
        - Text-based formats (.csv, .json, .xml, .txt)
        - ZIP archives (.zip) using the `read_files` tool.

- Document Creation & Editing:
    - Create and write to various file formats including Markdown (.md),
    Word documents (.docx), PDFs, CSV files, JSON, YAML, and HTML using
    UTF-8 encoding for default.
    - Apply formatting options including custom encoding, font styles, and
    layout settings
    - Modify existing files with automatic backup functionality
    - Support for mathematical expressions in PDF documents through LaTeX
    rendering

- PowerPoint Presentation Creation:
    - Create professional PowerPoint presentations with title slides and
    content slides
    - Format text with bold and italic styling
    - Create bullet point lists with proper hierarchical structure
    - Support for step-by-step process slides with visual indicators
    - Create tables with headers and rows of data
    - Support for custom templates and slide layouts
    - IMPORTANT: The `create_presentation` tool requires content to be a JSON
    string, not plain text. You must format your content as a JSON array of
    slide objects, then use `json.dumps()` to convert it to a string. Example:
      ```python
      import json
      slides = [
          {{"title": "Main Title", "subtitle": "Subtitle"}},
          {{"heading": "Slide Title", "bullet_points": ["Point 1", "Point 2"]}},
          {{"heading": "Data", "table": {{"headers": ["Col1", "Col2"], "rows": [["A", "B"]]}}}}
      ]
      content_json = json.dumps(slides)
      create_presentation(content=content_json, filename="presentation.pptx")
      ```

- Excel Spreadsheet Management:
    - Extract and analyze content from Excel files (.xlsx, .xls, .csv)
    with detailed cell information and markdown formatting
    - Create new Excel workbooks from scratch with multiple sheets
    - Perform comprehensive spreadsheet operations including:
        * Sheet creation, deletion, and data clearing
        * Cell-level operations (read, write, find specific values)
        * Row and column manipulation (add, update, delete)
        * Range operations for bulk data processing
        * Data export to CSV format for compatibility
    - Handle complex data structures with proper formatting and validation
    - Support for both programmatic data entry and manual cell updates

- Terminal and File System:
    - You have access to a full suite of terminal tools to interact with
    the file system within your working directory (`{working_directory}`).
    - You can execute shell commands (`shell_exec`), list files, and manage
    your workspace as needed to support your document creation tasks.
    - You can also use the terminal to create data visualizations such as
    charts and graphs. For example, you can write a Python script that uses
    libraries like `plotly` or `matplotlib` to create a chart and save it
    as an image file.

- Human Interaction:
    - Ask questions to users and receive their responses
    - Send informative messages to users without requiring responses
</capabilities>

<document_creation_workflow>
When working with documents, you should:
- Suggest appropriate file formats based on content requirements
- Maintain proper formatting and structure in all created documents
- Provide clear feedback about document creation and modification processes
- Ask clarifying questions when user requirements are ambiguous
- Recommend best practices for document organization and presentation
- For PowerPoint presentations, ALWAYS convert your slide content to JSON
  format before calling `create_presentation`. Never pass plain text or
  instructions - only properly formatted JSON strings as shown in the
  capabilities section
- For Excel files, always provide clear data structure and organization
- When creating spreadsheets, consider data relationships and use
appropriate sheet naming conventions
- To include data visualizations, write and execute Python scripts using
  the terminal. Use libraries like `plotly` to generate charts and
  graphs, and save them as image files that can be embedded in documents.
</document_creation_workflow>

<language_policy>
**CRITICAL**: You MUST write documents in the same language as the user's original request.
- If the user writes in Chinese, the document content MUST be in Chinese.
- If the user writes in English, the document content must be in English.
- This applies to: document titles, headings, body text, slide content, spreadsheet labels, etc.
- File names can remain in English for compatibility, but ALL content inside must match user's language.
</language_policy>

Your goal is to help users efficiently create, modify, and manage their
documents with professional quality and appropriate formatting across all
supported formats including advanced spreadsheet functionality."""


# Multi-Modal Agent System Prompt (Eigent's MULTI_MODAL_SYS_PROMPT)
MULTI_MODAL_AGENT_SYSTEM_PROMPT = """\
<role>
You are a Creative Content Specialist, specializing in analyzing and
generating various types of media content. Your expertise includes processing
video and audio, understanding image content, and creating new images from
text prompts. You are the team's expert for all multi-modal tasks.
</role>

<team_structure>
You collaborate with the following agents who can work in parallel:
- **Lead Software Engineer**: Integrates your generated media into
applications and websites.
- **Senior Research Analyst**: Provides the source material and context for
your analysis and generation tasks.
- **Documentation Specialist**: Embeds your visual content into reports,
presentations, and other documents.
</team_structure>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`. All local file operations must
occur here, but you can access files from any place in the file system. For all file system operations, you MUST use absolute paths to ensure precision and avoid ambiguity.
The current date is {now_str}(Accurate to the hour). For any date-related tasks, you MUST use this as the current date.
</operating_environment>

<mandatory_instructions>
- You MUST use the `read_note` tool to to gather all information collected
    by other team members by reading ALL notes and write down your findings in
    the notes.

- When you complete your task, your final response must be a comprehensive
    summary of your analysis or the generated media, presented in a clear,
    detailed, and easy-to-read format. Avoid using markdown tables for
    presenting data; use plain text formatting instead.
<mandatory_instructions>

<capabilities>
Your capabilities include:
- Video & Audio Analysis:
    - Download videos from URLs for analysis.
    - Transcribe speech from audio files to text with high accuracy
    - Answer specific questions about audio content
    - Process audio from both local files and URLs
    - Handle various audio formats including MP3, WAV, and OGG

- Image Analysis & Understanding:
    - Generate detailed descriptions of image content
    - Answer specific questions about images
    - Identify objects, text, people, and scenes in images
    - Process images from both local files and URLs

- Terminal and File System:
    - You have access to terminal tools to manage media files.
    - You can leverage powerful CLI tools like `ffmpeg` for any necessary video
    and audio conversion or manipulation. You can also use tools like `find`
    to locate media files, `wget` or `curl` to download them, and `du` or
    `df` to monitor disk space.

- Human Interaction:
    - Ask questions to users and receive their responses
    - Send informative messages to users without requiring responses

</capabilities>

<multi_modal_processing_workflow>
When working with multi-modal content, you should:
- Provide detailed and accurate descriptions of media content
- Extract relevant information based on user queries
- Generate appropriate media when requested
- Explain your analysis process and reasoning
- Ask clarifying questions when user requirements are ambiguous
</multi_modal_processing_workflow>

<language_policy>
**CRITICAL**: You MUST respond in the same language as the user's original request.
- If the user writes in Chinese, ALL your outputs must be in Chinese.
- If the user writes in English, respond in English.
- This applies to: descriptions, analysis results, summaries, and any text you generate.
</language_policy>

Your goal is to help users effectively process, understand, and create
multi-modal content across audio and visual domains."""


# Social Medium Agent System Prompt (Eigent's SOCIAL_MEDIA_SYS_PROMPT)
SOCIAL_MEDIUM_AGENT_SYSTEM_PROMPT = """\
You are a Social Media Management Assistant with comprehensive capabilities
across multiple platforms. You MUST use the `send_message_to_user` tool to
inform the user of every decision and action you take. Your message must
include a short title and a one-sentence description. This is a mandatory
part of your workflow. When you complete your task, your final response must
be a comprehensive summary of your actions, presented in a clear, detailed,
and easy-to-read format. Avoid using markdown tables for presenting data;
use plain text formatting instead.

- **Working Directory**: `{working_directory}`. All local file operations must
occur here, but you can access files from any place in the file system. For all file system operations, you MUST use absolute paths to ensure precision and avoid ambiguity.
The current date is {now_str}(Accurate to the hour). For any date-related tasks, you MUST use this as the current date.

Your integrated toolkits enable you to:

1. Gmail Management (GmailMCPToolkit):
   - Send emails to contacts
   - Search and read emails
   - Manage labels and inbox

2. Google Calendar Management (GoogleCalendarToolkit):
   - Create and manage calendar events
   - Check availability
   - Set reminders

3. Notion Workspace Management (NotionMCPToolkit):
   - List all pages and users in a Notion workspace
   - Retrieve and extract text content from Notion blocks

4. Human Interaction (HumanToolkit):
   - Ask questions to users and send messages via console.

5. File System Access:
   - You can use terminal tools to interact with the local file system in
   your working directory (`{working_directory}`), for example, to access
   files needed for posting. You can use tools like `find` to locate files,
   `grep` to search within them, and `curl` to interact with web APIs that
   are not covered by other tools.

When assisting users, always:
- Identify which platform's functionality is needed for the task.
- Check if required API credentials are available before attempting
operations.
- Provide clear explanations of what actions you're taking.
- Handle rate limits and API restrictions appropriately.
- Ask clarifying questions when user requests are ambiguous.

<language_policy>
**CRITICAL**: You MUST respond in the same language as the user's original request.
- If the user writes in Chinese, ALL your outputs must be in Chinese.
- If the user writes in English, respond in English.
- This applies to: messages, summaries, email drafts, and any text you generate.
</language_policy>"""


# Task Summary Agent System Prompt (Eigent's TASK_SUMMARY_SYS_PROMPT)
TASK_SUMMARY_AGENT_SYSTEM_PROMPT = """You are a helpful task assistant that can help users summarize the content of their tasks.

Your role is to:
1. Analyze the results from multiple subtasks
2. Synthesize findings into a clear, concise summary
3. Highlight key accomplishments and important data
4. Present information in a user-friendly format

Guidelines:
- Be concise but comprehensive
- Use bullet points or sections for clarity
- Highlight key findings or outputs
- Mention any important files created or actions taken
- DO NOT repeat the task description - focus on results
- Keep it professional but conversational

**CRITICAL Language Policy**:
- You MUST write the summary in the same language as the user's original request.
- If the user's request is in Chinese, the summary MUST be in Chinese.
- If the user's request is in English, the summary must be in English.
"""


# ============================================================================
# Agent Descriptions for Lazy Loading
# ============================================================================
# These descriptions are used by AMIWorkforce for task assignment decisions
# BEFORE actually creating the agents. This enables lazy loading pattern.

AGENT_DESCRIPTIONS = {
    "browser_agent": (
        "Browser Agent: Can search the web, extract webpage content, "
        "simulate browser actions, and provide relevant information to "
        "solve the given task."
    ),
    "developer_agent": (
        "Developer Agent: A master-level coding assistant with a powerful "
        "terminal. It can write and execute code, manage files, automate "
        "desktop tasks, and deploy web applications to solve complex "
        "technical challenges."
    ),
    "document_agent": (
        "Document Agent: A document processing assistant skilled in creating "
        "and modifying a wide range of file formats. It can generate "
        "text-based files/reports (Markdown, JSON, YAML, HTML), "
        "office documents (Word, PDF), presentations (PowerPoint), and "
        "data files (Excel, CSV)."
    ),
    "multi_modal_agent": (
        "Multi-Modal Agent: A specialist in media processing. It can "
        "analyze images and audio, transcribe speech, download videos, and "
        "generate new images from text prompts."
    ),
    "social_medium_agent": (
        "Social Medium Agent: A social media and communication specialist. "
        "It can send and read emails via Gmail, manage Google Calendar events, "
        "and access Notion workspace."
    ),
}


async def create_browser_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    notes_directory: Optional[str] = None,
    browser_data_directory: Optional[str] = None,
    headless: bool = False,
    memory_api_base_url: Optional[str] = None,
    ami_api_key: Optional[str] = None,
    user_id: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for browser-based research tasks.

    This factory function creates a ListenChatAgent with:
    - BrowserToolkit for web interaction (browser session created on-demand)
    - TerminalToolkit for command execution
    - NoteTakingToolkit for documentation
    - SearchToolkit for web search
    - HumanToolkit for user interaction
    - MemoryToolkit (optional) for knowledge retrieval

    Based on Eigent's browser_agent factory.

    Note: BrowserToolkit uses session_id mode, where the browser session is
    created on-demand when the first browser tool is called. This is clone-safe:
    multiple agent clones with the same task_id share the same browser session.

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier (used as session_id for browser)
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        browser_data_directory: Directory for browser user data
        headless: Whether to run browser in headless mode
        memory_api_base_url: API URL for memory service
        ami_api_key: AMI API key
        user_id: User identifier
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured ListenChatAgent instance
    """
    logger.info(f"[AgentFactory] Creating browser agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")
    logger.info(f"[AgentFactory] Browser data directory: {browser_data_directory}")
    logger.info(f"[AgentFactory] Headless mode: {headless}")

    agent_name = "browser_agent"
    # Use working_directory for notes so files can be accessed by shell in same directory
    notes_dir = working_directory

    # Initialize toolkits
    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    search_toolkit = SearchToolkit()
    search_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    # Create BrowserToolkit with session_id mode
    # Session is created on-demand using HybridBrowserSession's singleton mechanism.
    # This is clone-safe - multiple agent clones share the same browser via session_id.
    browser_toolkit = BrowserToolkit(
        session_id=task_id,  # Use task_id for session isolation
        headless=headless,
        user_data_dir=browser_data_directory,
    )
    browser_toolkit.set_task_state(task_state)
    logger.info(f"[AgentFactory] BrowserToolkit created with session_id={task_id}")

    tools = [
        *[_extract_callable(t) for t in note_toolkit.get_tools()],
        *[_extract_callable(t) for t in search_toolkit.get_tools()],
        *[_extract_callable(t) for t in terminal_toolkit.get_tools()],
        *[_extract_callable(t) for t in human_toolkit.get_tools()],
        *[_extract_callable(t) for t in browser_toolkit.get_tools()],
    ]

    # Add memory toolkit if configured
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit = MemoryToolkit(
            memory_api_base_url=memory_api_base_url,
            ami_api_key=ami_api_key,
            user_id=user_id,
        )
        memory_toolkit.set_task_state(task_state)
        tools.extend([_extract_callable(t) for t in memory_toolkit.get_tools()])
        logger.info("[AgentFactory] MemoryToolkit added")

    # Build system prompt (using Eigent's BROWSER_SYS_PROMPT)
    system_message = BROWSER_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create model configuration
    model_config = None
    if llm_api_key and llm_model:
        model_config = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Create the agent
    # Set token_limit to enable CAMEL's automatic context summarization
    agent = ListenChatAgent(
        task_state=task_state,
        agent_name=agent_name,
        system_message=system_message,
        model=model_config,
        tools=tools,
        agent_id=f"{agent_name}_{task_id}_{uuid.uuid4().hex[:8]}",
        token_limit=150000,  # Enable auto-summarization when context exceeds 75k tokens (50%)
    )

    # Set NoteTakingToolkit reference for workflow guide persistence
    agent.set_note_toolkit(note_toolkit)

    # Set agent reference in toolkits for IntentSequence cache integration
    # This enables:
    # - BrowserToolkit: URL change notifications for cache invalidation
    # - MemoryToolkit: Caching query_page_operations results
    browser_toolkit.set_agent(agent)
    if memory_api_base_url and ami_api_key and user_id:
        # Note: memory_toolkit was created above, need to set agent reference
        memory_toolkit.set_agent(agent)

    logger.info(f"[AgentFactory] Browser agent created with {len(tools)} tools")
    return agent


async def create_listen_browser_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    notes_directory: Optional[str] = None,
    browser_data_directory: Optional[str] = None,
    headless: bool = False,
    export_model_visible_snapshots: bool = False,
    memory_api_base_url: Optional[str] = None,
    ami_api_key: Optional[str] = None,
    user_id: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenBrowserAgent:
    """
    Create a ListenBrowserAgent with full TaskOrchestrator capabilities.

    This factory creates a ListenBrowserAgent which includes:
    - All toolkits from create_browser_agent (Browser, NoteTaking, Search, Terminal, Human, Memory)
    - Internal TaskOrchestrator for subtask management
    - Internal task management tools (get_current_plan, complete_subtask, replan_task)
    - Memory L1 direct subtask conversion from cognitive_phrase

    Use this when you need an agent that can:
    - Handle a complete browser task with internal decomposition
    - Track progress through internal subtask management
    - Dynamically replan when discovering new items

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier (used as session_id for browser)
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        browser_data_directory: Directory for browser user data
        headless: Whether to run browser in headless mode
        memory_api_base_url: API URL for memory service
        ami_api_key: AMI API key
        user_id: User identifier
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured ListenBrowserAgent instance
    """
    logger.info(f"[AgentFactory] Creating ListenBrowserAgent for task {task_id}")

    agent_name = "listen_browser_agent"
    # Use working_directory for notes as well, so files created by create_note
    # can be accessed by shell_exec_async in the same directory
    notes_dir = working_directory

    # Initialize toolkits
    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    search_toolkit = SearchToolkit()
    search_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    # Create BrowserToolkit with session_id mode
    browser_toolkit = BrowserToolkit(
        session_id=task_id,
        headless=headless,
        user_data_dir=browser_data_directory,
    )
    browser_toolkit.set_task_state(task_state)

    # Create MemoryToolkit if configured
    memory_toolkit = None
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit = MemoryToolkit(
            memory_api_base_url=memory_api_base_url,
            ami_api_key=ami_api_key,
            user_id=user_id,
        )
        memory_toolkit.set_task_state(task_state)

    # Create model configuration
    model_config = None
    if llm_api_key and llm_model:
        model_config = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Build tools list for LLM - same as create_browser_agent
    tools = [
        *[_extract_callable(t) for t in note_toolkit.get_tools()],
        *[_extract_callable(t) for t in search_toolkit.get_tools()],
        *[_extract_callable(t) for t in terminal_toolkit.get_tools()],
        *[_extract_callable(t) for t in human_toolkit.get_tools()],
        *[_extract_callable(t) for t in browser_toolkit.get_tools()],
    ]

    # Add memory toolkit tools if available
    if memory_toolkit:
        tools.extend([_extract_callable(t) for t in memory_toolkit.get_tools()])

    # Create the agent with tools passed to parent class
    # Set token_limit to enable CAMEL's automatic context summarization
    # GLM-4 has ~200k context, so we set 150k as limit to leave room for response
    agent = ListenBrowserAgent(
        task_state=task_state,
        agent_name=agent_name,
        browser_session=None,  # Will be created on-demand by BrowserToolkit
        browser_toolkit=browser_toolkit,
        note_toolkit=note_toolkit,
        search_toolkit=search_toolkit,
        terminal_toolkit=terminal_toolkit,
        human_toolkit=human_toolkit,
        memory_toolkit=memory_toolkit,
        working_directory=working_directory,
        model=model_config,
        tools=tools,  # Pass tools to parent class for LLM awareness
        token_limit=150000,  # Enable auto-summarization when context exceeds 75k tokens (50%)
    )

    if export_model_visible_snapshots:
        agent.enable_model_visible_snapshot_export(True)

    # Set agent reference in toolkits for IntentSequence cache integration
    browser_toolkit.set_agent(agent)
    if memory_toolkit:
        memory_toolkit.set_agent(agent)

    logger.info(f"[AgentFactory] ListenBrowserAgent created")
    return agent


def create_developer_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    notes_directory: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for development tasks.

    This factory function creates a ListenChatAgent with:
    - TerminalToolkit for command execution
    - NoteTakingToolkit for documentation
    - HumanToolkit for user interaction

    Based on Eigent's developer_agent factory.

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured ListenChatAgent instance
    """
    logger.info(f"[AgentFactory] Creating developer agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    agent_name = "developer_agent"
    # Use working_directory for notes so files can be accessed by shell in same directory
    notes_dir = working_directory

    # Initialize toolkits
    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    tools = [
        *[_extract_callable(t) for t in note_toolkit.get_tools()],
        *[_extract_callable(t) for t in terminal_toolkit.get_tools()],
        *[_extract_callable(t) for t in human_toolkit.get_tools()],
    ]

    # Build system prompt (using Eigent's DEVELOPER_SYS_PROMPT)
    system_message = DEVELOPER_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create model configuration
    model_config = None
    if llm_api_key and llm_model:
        model_config = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Create the agent
    # Set token_limit to enable CAMEL's automatic context summarization
    agent = ListenChatAgent(
        task_state=task_state,
        agent_name=agent_name,
        system_message=system_message,
        model=model_config,
        tools=tools,
        agent_id=f"{agent_name}_{task_id}_{uuid.uuid4().hex[:8]}",
        token_limit=150000,  # Enable auto-summarization when context exceeds 75k tokens (50%)
    )

    # Set NoteTakingToolkit reference for workflow guide persistence
    agent.set_note_toolkit(note_toolkit)

    logger.info(f"[AgentFactory] Developer agent created with {len(tools)} tools")
    return agent


async def create_document_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    notes_directory: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for document creation tasks.

    This factory function creates a ListenChatAgent with:
    - FileToolkit for file reading and writing
    - PPTXToolkit for PowerPoint presentations
    - ExcelToolkit for spreadsheet operations
    - MarkItDownToolkit for document reading
    - GoogleDriveMCPToolkit for Google Drive integration (if configured)
    - TerminalToolkit for command execution
    - NoteTakingToolkit for documentation
    - HumanToolkit for user interaction

    Based on Eigent's document_agent factory.

    Note: This is an async function because GoogleDriveMCPToolkit requires
    async initialization.

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured ListenChatAgent instance
    """
    logger.info(f"[AgentFactory] Creating document agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    agent_name = "document_agent"
    # Use working_directory for notes so files can be accessed by shell in same directory
    notes_dir = working_directory

    # Initialize toolkits
    file_toolkit = FileToolkit(working_directory=working_directory)
    file_toolkit.set_task_state(task_state)

    pptx_toolkit = PPTXToolkit(working_directory=working_directory)
    pptx_toolkit.set_task_state(task_state)

    excel_toolkit = ExcelToolkit(working_directory=working_directory)
    excel_toolkit.set_task_state(task_state)

    markitdown_toolkit = MarkItDownToolkit()
    markitdown_toolkit.set_task_state(task_state)

    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    tools = [
        *[_extract_callable(t) for t in file_toolkit.get_tools()],
        *[_extract_callable(t) for t in pptx_toolkit.get_tools()],
        *[_extract_callable(t) for t in excel_toolkit.get_tools()],
        *[_extract_callable(t) for t in markitdown_toolkit.get_tools()],
        *[_extract_callable(t) for t in note_toolkit.get_tools()],
        *[_extract_callable(t) for t in terminal_toolkit.get_tools()],
        *[_extract_callable(t) for t in human_toolkit.get_tools()],
    ]

    # Try to add Google Drive MCP toolkit if configured
    try:
        import os
        if os.environ.get("GDRIVE_CREDENTIALS_PATH"):
            gdrive_toolkit = GoogleDriveMCPToolkit()
            if await gdrive_toolkit.initialize():
                gdrive_toolkit.set_task_state(task_state)
                tools.extend([_extract_callable(t) for t in gdrive_toolkit.get_function_tools()])
                logger.info("[AgentFactory] GoogleDriveMCPToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize GoogleDriveMCPToolkit: {e}")

    # Build system prompt (using Eigent's DOCUMENT_SYS_PROMPT)
    system_message = DOCUMENT_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create model configuration
    model_config = None
    if llm_api_key and llm_model:
        model_config = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Create the agent
    # Set token_limit to enable CAMEL's automatic context summarization
    agent = ListenChatAgent(
        task_state=task_state,
        agent_name=agent_name,
        system_message=system_message,
        model=model_config,
        tools=tools,
        agent_id=f"{agent_name}_{task_id}_{uuid.uuid4().hex[:8]}",
        token_limit=150000,  # Enable auto-summarization when context exceeds 75k tokens (50%)
    )

    # Set NoteTakingToolkit reference for workflow guide persistence
    agent.set_note_toolkit(note_toolkit)

    logger.info(f"[AgentFactory] Document agent created with {len(tools)} tools")
    return agent


def create_multi_modal_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    notes_directory: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for multi-modal processing tasks.

    This factory function creates a ListenChatAgent with:
    - VideoDownloaderToolkit for video download
    - ImageAnalysisToolkit for image analysis
    - AudioAnalysisToolkit for audio transcription and QA (OpenAI platform only)
    - ImageGenerationToolkit for DALL-E image generation (OpenAI platform only)
    - TerminalToolkit for command execution
    - NoteTakingToolkit for documentation
    - HumanToolkit for user interaction

    Based on Eigent's multi_modal_agent factory.

    Note: AudioAnalysisToolkit and ImageGenerationToolkit are only added when
    using OpenAI platform, as they require OpenAI-specific APIs (Whisper, DALL-E).

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        llm_api_key: LLM API key (used for OpenAI audio/image APIs when on OpenAI platform)
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured ListenChatAgent instance
    """
    logger.info(f"[AgentFactory] Creating multi-modal agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    agent_name = "multi_modal_agent"
    # Use working_directory for notes so files can be accessed by shell in same directory
    notes_dir = working_directory

    # Create model configuration for vision/audio toolkits
    vision_model = None
    if llm_api_key and llm_model:
        vision_model = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Initialize core toolkits (always available)
    video_toolkit = VideoDownloaderToolkit(working_directory=working_directory)
    video_toolkit.set_task_state(task_state)

    image_toolkit = ImageAnalysisToolkit(model=vision_model)
    image_toolkit.set_task_state(task_state)

    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    tools = [
        *[_extract_callable(t) for t in video_toolkit.get_tools()],
        *[_extract_callable(t) for t in image_toolkit.get_tools()],
        *[_extract_callable(t) for t in note_toolkit.get_tools()],
        *[_extract_callable(t) for t in terminal_toolkit.get_tools()],
        *[_extract_callable(t) for t in human_toolkit.get_tools()],
    ]

    # Determine if we're using OpenAI platform (Eigent pattern)
    # AudioAnalysisToolkit and ImageGenerationToolkit require OpenAI APIs
    is_openai_platform = False
    if llm_model:
        model_lower = llm_model.lower()
        # Check for OpenAI model patterns
        is_openai_platform = any(pattern in model_lower for pattern in [
            'gpt-', 'gpt4', 'o1-', 'o3-', 'chatgpt', 'openai'
        ])

    logger.info(f"[AgentFactory] Model platform detection: model={llm_model}, is_openai={is_openai_platform}")

    if is_openai_platform and llm_api_key:
        # Add AudioAnalysisToolkit (requires OpenAI Whisper API)
        try:
            from camel.models import OpenAIAudioModels

            # Create OpenAI audio model with user's API key and base URL
            audio_model = OpenAIAudioModels(
                api_key=llm_api_key,
                url=llm_base_url,
            )

            audio_toolkit = AudioAnalysisToolkit(
                cache_dir=working_directory,
                transcribe_model=audio_model,
                audio_reasoning_model=vision_model,
            )
            audio_toolkit.set_task_state(task_state)
            tools.extend([_extract_callable(t) for t in audio_toolkit.get_tools()])
            logger.info("[AgentFactory] AudioAnalysisToolkit added (OpenAI platform)")
        except Exception as e:
            logger.warning(f"[AgentFactory] Could not initialize AudioAnalysisToolkit: {e}")

        # Add ImageGenerationToolkit (requires OpenAI DALL-E API)
        try:
            image_gen_toolkit = ImageGenerationToolkit(
                working_directory=working_directory,
                api_key=llm_api_key,
                base_url=llm_base_url,
            )
            image_gen_toolkit.set_task_state(task_state)
            tools.extend([_extract_callable(t) for t in image_gen_toolkit.get_tools()])
            logger.info("[AgentFactory] ImageGenerationToolkit added (OpenAI platform)")
        except Exception as e:
            logger.warning(f"[AgentFactory] Could not initialize ImageGenerationToolkit: {e}")
    else:
        logger.info(f"[AgentFactory] Skipping OpenAI-specific toolkits: not on OpenAI platform or no API key")

    # Build system prompt (using Eigent's MULTI_MODAL_SYS_PROMPT)
    system_message = MULTI_MODAL_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create model configuration
    model_config = None
    if llm_api_key and llm_model:
        model_config = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Create the agent
    # Set token_limit to enable CAMEL's automatic context summarization
    agent = ListenChatAgent(
        task_state=task_state,
        agent_name=agent_name,
        system_message=system_message,
        model=model_config,
        tools=tools,
        agent_id=f"{agent_name}_{task_id}_{uuid.uuid4().hex[:8]}",
        token_limit=150000,  # Enable auto-summarization when context exceeds 75k tokens (50%)
    )

    # Set NoteTakingToolkit reference for workflow guide persistence
    agent.set_note_toolkit(note_toolkit)

    logger.info(f"[AgentFactory] Multi-modal agent created with {len(tools)} tools")
    return agent


async def create_social_medium_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> ListenChatAgent:
    """
    Create a configured ListenChatAgent for social media and communication tasks.

    This factory function creates a ListenChatAgent with:
    - GmailMCPToolkit for email operations (if configured)
    - GoogleCalendarToolkit for calendar management (if configured)
    - NotionMCPToolkit for Notion integration (if configured)
    - TerminalToolkit for command execution
    - NoteTakingToolkit for documentation
    - HumanToolkit for user interaction

    Based on Eigent's social_medium_agent factory.

    Note: This is an async function because some MCP toolkits require
    async initialization.

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier
        working_directory: Directory for file operations
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured ListenChatAgent instance
    """
    logger.info(f"[AgentFactory] Creating social medium agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    agent_name = "social_medium_agent"

    # Initialize core toolkits
    note_toolkit = NoteTakingToolkit(notes_directory=working_directory)
    note_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    tools = [
        *[_extract_callable(t) for t in note_toolkit.get_tools()],
        *[_extract_callable(t) for t in terminal_toolkit.get_tools()],
        *[_extract_callable(t) for t in human_toolkit.get_tools()],
    ]

    # Try to add Gmail MCP toolkit if configured
    try:
        gmail_toolkit = GmailMCPToolkit()
        if await gmail_toolkit.initialize():
            gmail_toolkit.set_task_state(task_state)
            tools.extend([_extract_callable(t) for t in gmail_toolkit.get_function_tools()])
            logger.info("[AgentFactory] GmailMCPToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize GmailMCPToolkit: {e}")

    # Try to add Google Calendar toolkit if configured
    try:
        import os
        # GoogleCalendarToolkit requires GCAL_CREDENTIALS_PATH, not GOOGLE_CLIENT_ID/SECRET
        if os.environ.get("GCAL_CREDENTIALS_PATH"):
            calendar_toolkit = GoogleCalendarToolkit()
            await calendar_toolkit.initialize()
            calendar_toolkit.set_task_state(task_state)
            tools.extend([_extract_callable(t) for t in calendar_toolkit.get_tools()])
            logger.info("[AgentFactory] GoogleCalendarToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize GoogleCalendarToolkit: {e}")

    # Try to add Notion MCP toolkit if configured
    try:
        notion_toolkit = NotionMCPToolkit()
        if await notion_toolkit.initialize():
            notion_toolkit.set_task_state(task_state)
            tools.extend([_extract_callable(t) for t in notion_toolkit.get_function_tools()])
            logger.info("[AgentFactory] NotionMCPToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize NotionMCPToolkit: {e}")

    # Build system prompt (using Eigent's SOCIAL_MEDIA_SYS_PROMPT)
    system_message = SOCIAL_MEDIUM_AGENT_SYSTEM_PROMPT.format(
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create model configuration
    model_config = None
    if llm_api_key and llm_model:
        model_config = create_model_backend(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Create the agent
    # Set token_limit to enable CAMEL's automatic context summarization
    agent = ListenChatAgent(
        task_state=task_state,
        agent_name=agent_name,
        system_message=system_message,
        model=model_config,
        tools=tools,
        agent_id=f"{agent_name}_{task_id}_{uuid.uuid4().hex[:8]}",
        token_limit=150000,  # Enable auto-summarization when context exceeds 75k tokens (50%)
    )

    # Set NoteTakingToolkit reference for workflow guide persistence
    agent.set_note_toolkit(note_toolkit)

    logger.info(f"[AgentFactory] Social medium agent created with {len(tools)} tools")
    return agent


# ============================================================================
# Task Summary Agent
# ============================================================================

def create_task_summary_agent(
    llm_api_key: str,
    llm_model: str,
    llm_base_url: Optional[str] = None,
) -> ChatAgent:
    """
    Create a ChatAgent for summarizing task results.

    This agent is used to aggregate and summarize the results from multiple
    subtasks into a coherent, user-friendly output.

    Based on Eigent's task_summary_agent.

    Args:
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured ChatAgent instance for summarization
    """
    logger.info(f"[AgentFactory] Creating task summary agent with model={llm_model}")

    model_config = create_model_backend(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    agent = ChatAgent(
        system_message=TASK_SUMMARY_AGENT_SYSTEM_PROMPT,
        model=model_config,
    )

    logger.info("[AgentFactory] Task summary agent created")
    return agent


async def summarize_subtasks_results(
    agent: ChatAgent,
    main_task: str,
    subtasks: List[Dict[str, Any]],
) -> str:
    """
    Summarize the aggregated results from all subtasks into a concise summary.

    Based on Eigent's summary_subtasks_result function.

    Args:
        agent: The summary agent to use
        main_task: The main task description
        subtasks: List of subtask dicts with 'id', 'content', 'result' fields

    Returns:
        A concise summary of all subtask results
    """
    # Build subtasks info
    subtasks_info = ""
    for i, subtask in enumerate(subtasks, 1):
        subtasks_info += f"\n**Subtask {i}**\n"
        subtasks_info += f"Description: {subtask.get('content', 'N/A')}\n"
        subtasks_info += f"Result: {subtask.get('result', 'No result')}\n"
        subtasks_info += "---\n"

    prompt = f"""Summarize the results of the following subtasks.

Main Task: {main_task}

Subtasks (with descriptions and results):
---
{subtasks_info}
---

Instructions:
1. Provide a concise summary of what was accomplished
2. Highlight key findings or outputs from each subtask
3. Mention any important files created or actions taken
4. Use bullet points or sections for clarity
5. DO NOT repeat the task name in your summary - go straight to the results
6. Keep it professional but conversational

Summary:
"""

    response = await agent.astep(prompt)
    summary = response.msgs[0].content if response.msgs else response.msg.content

    logger.info(f"[AgentFactory] Generated summary for {len(subtasks)} subtasks")
    return summary

