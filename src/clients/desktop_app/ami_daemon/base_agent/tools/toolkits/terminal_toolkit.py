"""
TerminalToolkit - Shell command execution for agents.

Ported from CAMEL-AI/Eigent project.
Provides safe shell command execution with timeout and security controls.

Working directory isolation:
- If initialized with a working_directory, uses that directory
- Otherwise, uses the current task's workspace from WorkingDirectoryManager
- Falls back to current working directory if no manager is set

Event emission:
- Uses @listen_toolkit decorator for automatic activate/deactivate events
- Terminal-specific events include command, output, and exit code
"""

import asyncio
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...workspace import get_working_directory, get_current_manager
from ...events import listen_toolkit

logger = logging.getLogger(__name__)

# Commands that are potentially dangerous
DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "dd if=",
    "mkfs",
    "format",
    ":(){:|:&};:",  # fork bomb
    "> /dev/sda",
    "chmod -R 777 /",
    "chown -R",
]

# Commands that require extra caution
CAUTION_COMMANDS = [
    "sudo",
    "su ",
    "rm -rf",
    "rm -r",
    "rmdir",
    "shutdown",
    "reboot",
    "halt",
    "init ",
    "systemctl stop",
    "systemctl disable",
    "kill -9",
    "killall",
    "pkill",
]


class TerminalToolkit(BaseToolkit):
    """A toolkit for executing shell commands.

    Provides shell command execution with safety controls including:
    - Working directory restriction
    - Command timeout
    - Dangerous command blocking
    - Output size limits
    - Automatic event emission via @listen_toolkit
    """

    # Agent name for event tracking
    agent_name: str = "terminal_agent"

    def __init__(
        self,
        working_directory: Optional[str] = None,
        timeout: Optional[float] = 60.0,
        max_output_size: int = 50000,
        safe_mode: bool = True,
        allowed_commands: Optional[List[str]] = None,
        use_task_workspace: bool = True,
    ) -> None:
        """Initialize the TerminalToolkit.

        Args:
            working_directory: Directory to execute commands in.
                If not provided, uses task workspace or current directory.
            timeout: Command execution timeout in seconds (default 60).
            max_output_size: Maximum output size in characters (default 50000).
            safe_mode: If True, blocks dangerous commands (default True).
            allowed_commands: If provided, only these command prefixes are allowed.
            use_task_workspace: If True (default), uses current task's workspace
                when working_directory is not provided.
        """
        super().__init__(timeout=timeout)

        self._explicit_working_directory = working_directory
        self._use_task_workspace = use_task_workspace

        # Resolve initial working directory
        if working_directory:
            self._working_directory = Path(working_directory).resolve()
        elif use_task_workspace:
            # Try to get from current task manager
            self._working_directory = Path(get_working_directory())
        else:
            self._working_directory = Path.cwd()

        # Ensure working directory exists
        self._working_directory.mkdir(parents=True, exist_ok=True)

        self._max_output_size = max_output_size
        self._safe_mode = safe_mode
        self._allowed_commands = allowed_commands

        logger.info(
            f"TerminalToolkit initialized in {self._working_directory} "
            f"(safe_mode={safe_mode}, timeout={timeout}s, use_task_workspace={use_task_workspace})"
        )

    def _is_command_safe(self, command: str) -> tuple[bool, str]:
        """Check if a command is safe to execute.

        Args:
            command: The command to check.

        Returns:
            Tuple of (is_safe, reason). If not safe, reason explains why.
        """
        import re

        # Normalize whitespace (tabs, multiple spaces -> single space)
        command_normalized = re.sub(r'\s+', ' ', command).strip().lower()

        # Check for dangerous commands
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous.lower() in command_normalized:
                return False, f"Blocked dangerous command pattern: {dangerous}"

        # Check for shell escapes and encoded commands
        dangerous_patterns = [
            r'base64\s+(-d|--decode)',  # base64 decode
            r'\$\([^)]+\)',  # command substitution $(...)
            r'`[^`]+`',  # backtick command substitution
            r'eval\s+',  # eval command
            r'\|\s*sh\b',  # pipe to sh
            r'\|\s*bash\b',  # pipe to bash
            r'\|\s*zsh\b',  # pipe to zsh
            r';\s*sh\b',  # semicolon then sh
            r';\s*bash\b',  # semicolon then bash
            r'&&\s*sh\b',  # && then sh
            r'&&\s*bash\b',  # && then bash
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, command_normalized):
                return False, f"Blocked potentially dangerous pattern: {pattern}"

        # Check for caution commands in safe mode
        if self._safe_mode:
            for caution in CAUTION_COMMANDS:
                caution_lower = caution.lower()
                # Check at start or after shell operators (; && || |)
                if command_normalized.startswith(caution_lower):
                    return False, f"Command requires caution (safe_mode=True): {caution}"
                # Check after common separators
                separators = ['; ', '&& ', '|| ', '| ']
                for sep in separators:
                    if f"{sep}{caution_lower}" in command_normalized:
                        return False, f"Command requires caution (safe_mode=True): {caution}"

        # Check allowed commands list if provided
        if self._allowed_commands:
            allowed = False
            for prefix in self._allowed_commands:
                if command_normalized.startswith(prefix.lower()):
                    allowed = True
                    break
            if not allowed:
                return False, f"Command not in allowed list: {self._allowed_commands}"

        return True, ""

    @listen_toolkit(
        inputs=lambda self, command, **kw: f"$ {command[:100]}{'...' if len(command) > 100 else ''}",
        return_msg=lambda r: r[:200] if isinstance(r, str) and len(r) > 200 else str(r)
    )
    def shell_exec(
        self,
        command: str,
        timeout: Optional[int] = None,
    ) -> str:
        """Execute a shell command and return the output.

        Args:
            command: The shell command to execute.
            timeout: Override timeout in seconds. Uses default if not provided.

        Returns:
            The command output (stdout + stderr combined).
            If the command fails, returns an error message.
        """
        # Security check
        is_safe, reason = self._is_command_safe(command)
        if not is_safe:
            error_msg = f"Command blocked: {reason}"
            logger.warning(error_msg)
            return error_msg

        effective_timeout = timeout if timeout is not None else self.timeout

        logger.info(f"Executing command: {command[:100]}{'...' if len(command) > 100 else ''}")

        try:
            # Execute the command
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self._working_directory),
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env={**os.environ, "LC_ALL": "C.UTF-8"},
            )

            # Combine stdout and stderr
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output:
                    output += "\n--- stderr ---\n"
                output += result.stderr

            # Add return code info if non-zero
            if result.returncode != 0:
                output += f"\n[Exit code: {result.returncode}]"

            # Truncate if too long
            if len(output) > self._max_output_size:
                output = (
                    output[:self._max_output_size]
                    + f"\n... (truncated, total {len(output)} chars)"
                )

            logger.debug(f"Command completed with exit code {result.returncode}")
            return output if output else "(no output)"

        except subprocess.TimeoutExpired:
            error_msg = f"Command timed out after {effective_timeout} seconds"
            logger.warning(error_msg)
            return error_msg

        except Exception as e:
            error_msg = f"Command execution error: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @listen_toolkit(
        inputs=lambda self, command, **kw: f"$ {command[:100]}{'...' if len(command) > 100 else ''}",
        return_msg=lambda r: r[:200] if isinstance(r, str) and len(r) > 200 else str(r)
    )
    async def shell_exec_async(
        self,
        command: str,
        timeout: Optional[int] = None,
    ) -> str:
        """Execute a shell command asynchronously.

        Args:
            command: The shell command to execute.
            timeout: Override timeout in seconds.

        Returns:
            The command output (stdout + stderr combined).
        """
        # Security check
        is_safe, reason = self._is_command_safe(command)
        if not is_safe:
            error_msg = f"Command blocked: {reason}"
            logger.warning(error_msg)
            return error_msg

        # Convert timeout to int if string (LLM may pass string values)
        if timeout is not None and isinstance(timeout, str):
            try:
                timeout = int(timeout)
            except ValueError:
                timeout = None

        effective_timeout = timeout if timeout is not None else self.timeout

        logger.info(f"Executing async command: {command[:100]}{'...' if len(command) > 100 else ''}")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._working_directory),
                env={**os.environ, "LC_ALL": "C.UTF-8"},
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return f"Command timed out after {effective_timeout} seconds"

            # Combine output
            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                if output:
                    output += "\n--- stderr ---\n"
                output += stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                output += f"\n[Exit code: {process.returncode}]"

            # Truncate if too long
            if len(output) > self._max_output_size:
                output = (
                    output[:self._max_output_size]
                    + f"\n... (truncated, total {len(output)} chars)"
                )

            return output if output else "(no output)"

        except Exception as e:
            error_msg = f"Async command execution error: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @property
    def working_directory(self) -> Path:
        """Get the current working directory.

        If use_task_workspace is True and no explicit directory was provided,
        this dynamically gets the current task's workspace directory.
        """
        # If explicit directory was provided, always use it
        if self._explicit_working_directory:
            return self._working_directory

        # If using task workspace, get current manager's workspace
        if self._use_task_workspace:
            manager = get_current_manager()
            if manager:
                return manager.workspace

        return self._working_directory

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns async version of shell_exec to avoid blocking the event loop
        when called from async agent context.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.shell_exec_async, name="shell_exec"),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Terminal Toolkit"
