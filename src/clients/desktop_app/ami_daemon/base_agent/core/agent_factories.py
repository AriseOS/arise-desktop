"""
Agent Factories - Create configured AMIAgent instances for task execution.

These factory functions create AMIAgent instances with the appropriate
toolkits for different agent types (browser, developer, document, etc.).

Modeled after Eigent's agent factory pattern in app/utils/agent.py.
"""

import datetime
import logging
import platform
from typing import Any, Dict, List, Optional

from src.common.llm import AnthropicProvider

from .ami_agent import AMIAgent
from .ami_browser_agent import AMIBrowserAgent
from .ami_tool import AMITool

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def create_provider(
    llm_api_key: str,
    llm_model: str,
    llm_base_url: Optional[str] = None,
) -> AnthropicProvider:
    """
    Create AnthropicProvider for agent LLM calls.

    Args:
        llm_api_key: API key for LLM calls
        llm_model: Model name (e.g., 'claude-sonnet-4-20250514')
        llm_base_url: Base URL for API (CRS proxy URL)

    Returns:
        AnthropicProvider instance configured with API key and model.
    """
    logger.info(f"[AgentFactory] Creating provider: model={llm_model}, url={llm_base_url}")

    return AnthropicProvider(
        api_key=llm_api_key,
        model_name=llm_model,
        base_url=llm_base_url,
    )


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

- You SHOULD keep the user informed by providing message_title and
    message_description parameters when calling tools. These optional
    parameters are available on all tools and will automatically notify
    the user of your progress.
</mandatory_instructions>

<capabilities>
Your capabilities include:
- Search and get information from the web using the search tools.
- Use the rich browser related toolset to investigate websites.
- Use the terminal tools to perform local operations.
- Use the note-taking tools to record your findings.
- Use the human toolkit to ask for help when you are stuck.
- Use the memory toolkit to query known page operations when exploring unfamiliar pages.
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
- When encountering persistent network errors, page load failures, or
    access denied errors, use the human toolkit to inform the user and
    ask how to proceed.
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

- You SHOULD keep the user informed by providing message_title and message_description
    parameters when calling tools. These optional parameters are available on all tools
    and will automatically notify the user of your progress.

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
    - **IMPORTANT:** Before the task gets started, you can use `shell_exec` to
      run `ls {working_directory}` to check for important files in the working
      directory, and then use terminal commands like `cat`, `grep`, or `head`
      to read and examine these files.
    - **Text & Data Processing**: `awk`, `sed`, `grep`, `jq`.
    - **File System & Execution**: `find`, `xargs`, `tar`, `zip`, `unzip`,
      `chmod`.
    - **Networking & Web**: `curl`, `wget` for web requests; `ssh` for
      remote access.
- **Screen Observation**: You can take screenshots to analyze GUIs and visual
  context, enabling you to perform tasks that require sight.
- **Desktop Automation**: You can control desktop applications
  programmatically.
  - **On macOS**, you MUST prioritize using **AppleScript** for its robust
    control over native applications. Execute simple commands with
    `osascript -e '...'` or run complex scripts from a `.scpt` file.
  - **On other systems**, use **pyautogui** for cross-platform GUI
    automation.
  - **IMPORTANT**: Always complete the full automation workflow—do not just
    prepare or suggest actions. Execute them to completion.
- **Solution Verification**: You can immediately test and verify your
  solutions by executing them in the terminal.
- **Web Deployment**: You can deploy web applications and content, serve
  files, and manage deployments.
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

- **GUI Automation Strategy**:
  - **AppleScript (macOS Priority)**: For robust control of macOS apps, use
    `osascript`.
    - Example (open Slack):
      `osascript -e 'tell application "Slack" to activate'`
    - Example (run script file): `osascript my_script.scpt`
  - **pyautogui (Cross-Platform)**: For other OSes or simple automation.
    - Key functions: `pyautogui.click(x, y)`, `pyautogui.typewrite("text")`,
      `pyautogui.hotkey('ctrl', 'c')`, `pyautogui.press('enter')`.
    - Safety: Always use `time.sleep()` between actions to ensure stability
      and add `pyautogui.FAILSAFE = True` to your scripts.
    - Workflow: Your scripts MUST complete the entire task, from start to
      final submission.

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

- Stop a Process: If a process needs to be terminated, use
    `shell_kill_process(id="...")`.
</terminal_tips>

<collaboration_and_assistance>
- If you get stuck, encounter an issue you cannot solve (like a CAPTCHA),
    encounter persistent network errors, or need clarification, use the
    `ask_human` tool.
- Document your progress and findings in notes so other agents can build
    upon your work.
</collaboration_and_assistance>

<language_policy>
**CRITICAL**: You MUST respond in the same language as the user's original request.
- If the user writes in Chinese, ALL your outputs must be in Chinese (code comments, summaries, reports).
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

- You SHOULD keep the user informed by providing message_title and
    message_description parameters when calling tools. These optional
    parameters are available on all tools and will automatically notify
    the user of your progress.
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
- If you encounter errors you cannot resolve, use the human toolkit to
    ask the user for help.
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

- You SHOULD keep the user informed by providing message_title and
    message_description parameters when calling tools. These optional
    parameters are available on all tools and will automatically notify
    the user of your progress.
</mandatory_instructions>

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
- If you encounter errors you cannot resolve (download failures, format
    issues), use the human toolkit to ask the user for help.
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
- If you encounter authentication errors, permission issues, or other
    errors you cannot resolve, use the human toolkit to ask the user.

<language_policy>
**CRITICAL**: You MUST respond in the same language as the user's original request.
- If the user writes in Chinese, ALL your outputs must be in Chinese.
- If the user writes in English, respond in English.
- This applies to: messages, summaries, email drafts, and any text you generate.
</language_policy>"""


# Task Summary Agent System Prompt (Eigent's TASK_SUMMARY_SYS_PROMPT)
TASK_SUMMARY_AGENT_SYSTEM_PROMPT = """You are a task completion assistant. After a task finishes, you review the results and decide what to present to the user.

You have TWO responsibilities:

1. **Text Summary**: Write a concise summary of what was accomplished.
2. **File Selection**: From the list of workspace files, select ONLY the key deliverable files to send to the user.

Guidelines for text summary:
- Be concise but comprehensive
- Use bullet points or sections for clarity
- Highlight key findings or outputs
- DO NOT repeat the task description — focus on results
- Keep it professional but conversational

Guidelines for file selection:
- Select only the FINAL deliverable files that the user actually needs
- DO NOT select intermediate files: research notes, raw data dumps, temporary files
- Prefer well-formatted files (HTML, CSV, Excel, Word) over plain text/markdown
- If the task result is a simple text answer, select NO files
- When in doubt, fewer files is better than too many

**CRITICAL Language Policy**:
- You MUST write the summary in the same language as the user's original request.
- If the user's request is in Chinese, the summary MUST be in Chinese.
- If the user's request is in English, the summary must be in English.

**Output format** (respond in valid JSON):
{"summary": "Your text summary here...", "selected_files": ["report.html", "data.xlsx"]}

If no files should be delivered:
{"summary": "Your text summary here...", "selected_files": []}
"""


# ============================================================================
# Agent Descriptions for Lazy Loading
# ============================================================================
# These descriptions are used for task assignment decisions
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
) -> AMIAgent:
    """
    Create a configured AMIAgent for browser-based research tasks.

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
        Configured AMIAgent instance
    """
    from ..tools.toolkits import (
        NoteTakingToolkit, SearchToolkit, TerminalToolkit,
        HumanToolkit, BrowserToolkit, MemoryToolkit,
    )

    logger.info(f"[AgentFactory] Creating browser agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")
    logger.info(f"[AgentFactory] Browser data directory: {browser_data_directory}")
    logger.info(f"[AgentFactory] Headless mode: {headless}")

    agent_name = "browser_agent"
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

    browser_toolkit = BrowserToolkit(
        session_id=task_id,
        headless=headless,
        user_data_dir=browser_data_directory,
    )
    browser_toolkit.set_task_state(task_state)
    logger.info(f"[AgentFactory] BrowserToolkit created with session_id={task_id}")

    tools = [
        *note_toolkit.get_tools(),
        *search_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
        *human_toolkit.get_tools(),
        *browser_toolkit.get_tools(),
    ]

    # Add memory toolkit if configured
    if memory_api_base_url and ami_api_key and user_id:
        memory_toolkit = MemoryToolkit(
            memory_api_base_url=memory_api_base_url,
            ami_api_key=ami_api_key,
            user_id=user_id,
        )
        memory_toolkit.set_task_state(task_state)
        tools.extend(memory_toolkit.get_tools())
        logger.info("[AgentFactory] MemoryToolkit added")

    # Build system prompt
    system_message = BROWSER_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create provider
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
    )

    # Set NoteTakingToolkit reference for workflow guide persistence
    agent.set_note_toolkit(note_toolkit)

    # Set agent reference in toolkits for URL change notifications and cache
    browser_toolkit.set_agent(agent)
    if memory_api_base_url and ami_api_key and user_id:
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
) -> AMIBrowserAgent:
    """
    Create an AMIBrowserAgent with full browser automation capabilities.

    This factory creates an AMIBrowserAgent which includes:
    - All toolkits (Browser, NoteTaking, Search, Terminal, Human, Memory)
    - Memory page operations (auto-queried on URL change)

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier (used as session_id for browser)
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        browser_data_directory: Directory for browser user data
        headless: Whether to run browser in headless mode
        export_model_visible_snapshots: Whether to export model-visible snapshots
        memory_api_base_url: API URL for memory service
        ami_api_key: AMI API key
        user_id: User identifier
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured AMIBrowserAgent instance
    """
    logger.info(f"[AgentFactory] Creating AMIBrowserAgent for task {task_id}")

    from ..tools.toolkits import (
        NoteTakingToolkit, SearchToolkit, TerminalToolkit,
        HumanToolkit, BrowserToolkit, MemoryToolkit,
    )

    agent_name = "listen_browser_agent"
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

    # Build tools list
    tools = [
        *note_toolkit.get_tools(),
        *search_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
        *human_toolkit.get_tools(),
        *browser_toolkit.get_tools(),
    ]

    if memory_toolkit:
        tools.extend(memory_toolkit.get_tools())

    # Build system prompt (same as browser agent)
    system_message = BROWSER_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create provider
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIBrowserAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
        memory_toolkit=memory_toolkit,
    )

    # Set NoteTakingToolkit reference
    agent.set_note_toolkit(note_toolkit)

    if export_model_visible_snapshots:
        agent.enable_model_visible_snapshot_export(True)

    # Set agent reference in toolkits
    browser_toolkit.set_agent(agent)
    if memory_toolkit:
        memory_toolkit.set_agent(agent)

    logger.info(f"[AgentFactory] AMIBrowserAgent created")
    return agent


def create_developer_agent(
    task_state: Any,
    task_id: str,
    working_directory: str,
    notes_directory: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> AMIAgent:
    """
    Create a configured AMIAgent for development tasks.

    Args:
        task_state: TaskState for SSE event emission
        task_id: Task identifier
        working_directory: Directory for file operations
        notes_directory: Directory for notes (defaults to working_directory)
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        Configured AMIAgent instance
    """
    logger.info(f"[AgentFactory] Creating developer agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    from ..tools.toolkits import (
        NoteTakingToolkit, TerminalToolkit, HumanToolkit,
    )

    agent_name = "developer_agent"
    notes_dir = working_directory

    # Initialize toolkits
    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    tools = [
        *note_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
        *human_toolkit.get_tools(),
    ]

    # Build system prompt
    system_message = DEVELOPER_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create provider
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
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
) -> AMIAgent:
    """
    Create a configured AMIAgent for document creation tasks.

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
        Configured AMIAgent instance
    """
    logger.info(f"[AgentFactory] Creating document agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    from ..tools.toolkits import (
        NoteTakingToolkit, TerminalToolkit, HumanToolkit,
        FileToolkit, PPTXToolkit, ExcelToolkit, MarkItDownToolkit,
        GoogleDriveMCPToolkit,
    )

    agent_name = "document_agent"
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
        *file_toolkit.get_tools(),
        *pptx_toolkit.get_tools(),
        *excel_toolkit.get_tools(),
        *markitdown_toolkit.get_tools(),
        *note_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
        *human_toolkit.get_tools(),
    ]

    # Try to add Google Drive MCP toolkit if configured
    try:
        import os
        if os.environ.get("GDRIVE_CREDENTIALS_PATH"):
            gdrive_toolkit = GoogleDriveMCPToolkit()
            if await gdrive_toolkit.initialize():
                gdrive_toolkit.set_task_state(task_state)
                tools.extend(gdrive_toolkit.get_function_tools())
                logger.info("[AgentFactory] GoogleDriveMCPToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize GoogleDriveMCPToolkit: {e}")

    # Build system prompt
    system_message = DOCUMENT_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create provider
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
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
) -> AMIAgent:
    """
    Create a configured AMIAgent for multi-modal processing tasks.

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
        Configured AMIAgent instance
    """
    logger.info(f"[AgentFactory] Creating multi-modal agent for task {task_id}")
    logger.info(f"[AgentFactory] Working directory: {working_directory}")

    from ..tools.toolkits import (
        NoteTakingToolkit, TerminalToolkit, HumanToolkit,
        VideoDownloaderToolkit, ImageAnalysisToolkit,
        AudioAnalysisToolkit, ImageGenerationToolkit,
    )

    agent_name = "multi_modal_agent"
    notes_dir = working_directory

    # Create vision provider for ImageAnalysisToolkit
    vision_provider = None
    if llm_api_key and llm_model:
        vision_provider = create_provider(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
        )

    # Initialize core toolkits (always available)
    video_toolkit = VideoDownloaderToolkit(working_directory=working_directory)
    video_toolkit.set_task_state(task_state)

    image_toolkit = ImageAnalysisToolkit(provider=vision_provider)
    image_toolkit.set_task_state(task_state)

    note_toolkit = NoteTakingToolkit(notes_directory=notes_dir)
    note_toolkit.set_task_state(task_state)

    terminal_toolkit = TerminalToolkit(working_directory=working_directory)
    terminal_toolkit.set_task_state(task_state)

    human_toolkit = HumanToolkit()
    human_toolkit.set_task_state(task_state)

    tools = [
        *video_toolkit.get_tools(),
        *image_toolkit.get_tools(),
        *note_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
        *human_toolkit.get_tools(),
    ]

    # Determine if we're using OpenAI platform
    # AudioAnalysisToolkit and ImageGenerationToolkit require OpenAI APIs
    is_openai_platform = False
    if llm_model:
        model_lower = llm_model.lower()
        is_openai_platform = any(pattern in model_lower for pattern in [
            'gpt-', 'gpt4', 'o1-', 'o3-', 'chatgpt', 'openai'
        ])

    logger.info(f"[AgentFactory] Model platform detection: model={llm_model}, is_openai={is_openai_platform}")

    if is_openai_platform and llm_api_key:
        # Add AudioAnalysisToolkit (requires OpenAI Whisper API)
        try:
            audio_toolkit = AudioAnalysisToolkit(
                cache_dir=working_directory,
                api_key=llm_api_key,
                base_url=llm_base_url,
                reasoning_provider=vision_provider,
            )
            audio_toolkit.set_task_state(task_state)
            tools.extend(audio_toolkit.get_tools())
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
            tools.extend(image_gen_toolkit.get_tools())
            logger.info("[AgentFactory] ImageGenerationToolkit added (OpenAI platform)")
        except Exception as e:
            logger.warning(f"[AgentFactory] Could not initialize ImageGenerationToolkit: {e}")
    else:
        logger.info(f"[AgentFactory] Skipping OpenAI-specific toolkits: not on OpenAI platform or no API key")

    # Build system prompt
    system_message = MULTI_MODAL_AGENT_SYSTEM_PROMPT.format(
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create provider for the agent
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
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
) -> AMIAgent:
    """
    Create a configured AMIAgent for social media and communication tasks.

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
        Configured AMIAgent instance
    """
    from ..tools.toolkits import (
        NoteTakingToolkit, TerminalToolkit, HumanToolkit,
        GmailMCPToolkit, NotionMCPToolkit, GoogleCalendarToolkit,
    )

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
        *note_toolkit.get_tools(),
        *terminal_toolkit.get_tools(),
        *human_toolkit.get_tools(),
    ]

    # Try to add Gmail MCP toolkit if configured
    try:
        gmail_toolkit = GmailMCPToolkit()
        if await gmail_toolkit.initialize():
            gmail_toolkit.set_task_state(task_state)
            tools.extend(gmail_toolkit.get_function_tools())
            logger.info("[AgentFactory] GmailMCPToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize GmailMCPToolkit: {e}")

    # Try to add Google Calendar toolkit if configured
    try:
        import os
        if os.environ.get("GCAL_CREDENTIALS_PATH"):
            calendar_toolkit = GoogleCalendarToolkit()
            await calendar_toolkit.initialize()
            calendar_toolkit.set_task_state(task_state)
            tools.extend(calendar_toolkit.get_tools())
            logger.info("[AgentFactory] GoogleCalendarToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize GoogleCalendarToolkit: {e}")

    # Try to add Notion MCP toolkit if configured
    try:
        notion_toolkit = NotionMCPToolkit()
        if await notion_toolkit.initialize():
            notion_toolkit.set_task_state(task_state)
            tools.extend(notion_toolkit.get_function_tools())
            logger.info("[AgentFactory] NotionMCPToolkit added")
    except Exception as e:
        logger.warning(f"[AgentFactory] Could not initialize NotionMCPToolkit: {e}")

    # Build system prompt
    system_message = SOCIAL_MEDIUM_AGENT_SYSTEM_PROMPT.format(
        working_directory=working_directory,
        now_str=_get_now_str(),
    )

    # Create provider
    provider = create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )

    # Create the agent
    agent = AMIAgent(
        task_state=task_state,
        agent_name=agent_name,
        provider=provider,
        system_prompt=system_message,
        tools=tools,
    )

    # Set NoteTakingToolkit reference for workflow guide persistence
    agent.set_note_toolkit(note_toolkit)

    logger.info(f"[AgentFactory] Social medium agent created with {len(tools)} tools")
    return agent


# ============================================================================
# Task Summary
# ============================================================================

def create_task_summary_provider(
    llm_api_key: str,
    llm_model: str,
    llm_base_url: Optional[str] = None,
) -> AnthropicProvider:
    """
    Create an AnthropicProvider for summarizing task results.

    Args:
        llm_api_key: LLM API key
        llm_model: LLM model name
        llm_base_url: LLM base URL

    Returns:
        AnthropicProvider for summarization
    """
    logger.info(f"[AgentFactory] Creating task summary provider with model={llm_model}")
    return create_provider(
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )


async def summarize_subtasks_results(
    provider: AnthropicProvider,
    main_task: str,
    subtasks: List[Dict[str, Any]],
    workspace_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Summarize subtask results and select deliverable files.

    Args:
        provider: AnthropicProvider to use for summarization
        main_task: The main task description
        subtasks: List of subtask dicts with 'id', 'content', 'result' fields
        workspace_files: List of filenames available in workspace (candidates for delivery)

    Returns:
        Dict with 'summary' (str) and 'selected_files' (List[str])
    """
    import json

    # Build subtasks info
    subtasks_info = ""
    for i, subtask in enumerate(subtasks, 1):
        subtasks_info += f"\n**Subtask {i}**\n"
        subtasks_info += f"Description: {subtask.get('content', 'N/A')}\n"
        subtasks_info += f"Result: {subtask.get('result', 'No result')}\n"
        subtasks_info += "---\n"

    # Build file list section
    files_section = ""
    if workspace_files:
        file_list = "\n".join(f"- {f}" for f in workspace_files)
        files_section = f"""
Available files in workspace:
{file_list}

Select which files should be delivered to the user as final deliverables.
"""

    prompt = f"""Main Task: {main_task}

Subtasks (with descriptions and results):
---
{subtasks_info}
---
{files_section}
Respond in JSON format: {{"summary": "...", "selected_files": ["file1.html", ...]}}
"""

    response = await provider.generate_with_tools(
        system_prompt=TASK_SUMMARY_AGENT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        max_tokens=4096,
    )
    raw_text = response.get_text()

    # Parse JSON response
    try:
        # Extract JSON from response (LLM may wrap it in markdown code blocks)
        json_text = raw_text.strip()
        if json_text.startswith("```"):
            # Strip markdown code fences
            lines = json_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            json_text = "\n".join(lines).strip()

        result = json.loads(json_text)
        summary = result.get("summary", raw_text)
        selected_files = result.get("selected_files", [])
        if not isinstance(selected_files, list):
            selected_files = []

        logger.info(
            f"[AgentFactory] Summary generated, selected {len(selected_files)} deliverable files"
        )
        return {"summary": summary, "selected_files": selected_files}

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        # Fallback: treat entire response as summary, select all files
        logger.warning(
            f"[AgentFactory] Failed to parse summary JSON ({e}), using raw text as summary"
        )
        return {"summary": raw_text, "selected_files": workspace_files or []}

