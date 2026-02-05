"""
WebDeployToolkit - Deploy web applications and content.

Wraps CAMEL's WebDeployToolkit with SSE event support.
Used by Developer Agent for deploying HTML content and web applications.
"""

import uuid
import logging
from typing import Any, Dict, List, Optional

from camel.toolkits import WebDeployToolkit as BaseWebDeployToolkit
from camel.toolkits import FunctionTool

from .base_toolkit import BaseToolkit

logger = logging.getLogger(__name__)


class WebDeployToolkit(BaseToolkit):
    """
    Web deployment toolkit for serving and deploying web content.

    Capabilities:
    - Deploy HTML content to a web server
    - Deploy entire folders as static websites
    - Generate unique URLs for each deployment

    Based on CAMEL's WebDeployToolkit.
    """

    def __init__(
        self,
        timeout: Optional[float] = None,
        add_branding_tag: bool = False,  # Default to False for 2ami
        logo_path: Optional[str] = None,
        tag_text: str = "Created by AMI",
        tag_url: str = "https://ami.ariseos.com/",
        remote_server_ip: Optional[str] = None,
        remote_server_port: int = 8080,
    ):
        """
        Initialize WebDeployToolkit.

        Args:
            timeout: Timeout for deployment operations.
            add_branding_tag: Whether to add branding to deployed content.
            logo_path: Path to logo for branding.
            tag_text: Text for branding tag.
            tag_url: URL for branding link.
            remote_server_ip: IP of remote deployment server.
            remote_server_port: Port of remote deployment server.
        """
        super().__init__()

        self._timeout = timeout
        self._add_branding_tag = add_branding_tag

        # Initialize CAMEL's base toolkit
        self._base_toolkit = BaseWebDeployToolkit(
            timeout=timeout,
            add_branding_tag=add_branding_tag,
            logo_path=logo_path,
            tag_text=tag_text,
            tag_url=tag_url,
            remote_server_ip=remote_server_ip,
            remote_server_port=remote_server_port,
        )

        logger.info(
            f"[WebDeployToolkit] Initialized with remote_server={remote_server_ip}:{remote_server_port}"
        )

    @staticmethod
    def toolkit_name() -> str:
        """Return toolkit name for identification."""
        return "WebDeployToolkit"

    def get_tools(self) -> List[FunctionTool]:
        """
        Get all tools from this toolkit.

        Returns:
            List of FunctionTool instances.
        """
        # Create wrapped tools that generate unique subdirectories
        tools = [
            FunctionTool(self.deploy_html_content),
            FunctionTool(self.deploy_folder),
        ]
        return tools

    def deploy_html_content(
        self,
        html_content: Optional[str] = None,
        html_file_path: Optional[str] = None,
        file_name: str = "index.html",
        port: int = 8080,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deploy HTML content to a web server.

        Args:
            html_content: HTML content as a string.
            html_file_path: Path to an HTML file to deploy.
            file_name: Name for the deployed file.
            port: Port to serve on.
            domain: Domain for the deployment.

        Returns:
            Dictionary with deployment URL and status.
        """
        # Generate unique subdirectory for this deployment
        subdirectory = str(uuid.uuid4())

        # Emit start event
        self._emit_tool_event("deploy_html_content", "start", {
            "file_name": file_name,
            "subdirectory": subdirectory,
        })

        try:
            result = self._base_toolkit.deploy_html_content(
                html_content=html_content,
                html_file_path=html_file_path,
                file_name=file_name,
                port=port,
                domain=domain,
                subdirectory=subdirectory,
            )

            # Emit success event
            self._emit_tool_event("deploy_html_content", "success", {
                "url": result.get("url", ""),
            })

            return result
        except Exception as e:
            self._emit_tool_event("deploy_html_content", "error", {"error": str(e)})
            raise

    def deploy_folder(
        self,
        folder_path: str,
        port: int = 8080,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deploy a folder as a static website.

        Args:
            folder_path: Path to the folder to deploy.
            port: Port to serve on.
            domain: Domain for the deployment.

        Returns:
            Dictionary with deployment URL and status.
        """
        # Generate unique subdirectory for this deployment
        subdirectory = str(uuid.uuid4())

        # Emit start event
        self._emit_tool_event("deploy_folder", "start", {
            "folder_path": folder_path,
            "subdirectory": subdirectory,
        })

        try:
            result = self._base_toolkit.deploy_folder(
                folder_path=folder_path,
                port=port,
                domain=domain,
                subdirectory=subdirectory,
            )

            # Emit success event
            self._emit_tool_event("deploy_folder", "success", {
                "url": result.get("url", ""),
            })

            return result
        except Exception as e:
            self._emit_tool_event("deploy_folder", "error", {"error": str(e)})
            raise

    def _emit_tool_event(self, tool_name: str, status: str, data: dict) -> None:
        """Emit SSE event for tool execution."""
        if self._task_state is None:
            return

        try:
            from ..events import ToolCallData
            from ..events.toolkit_listen import _run_async_safely

            event = ToolCallData(
                tool_name=tool_name,
                status=status,
                data=data,
            )
            _run_async_safely(self._task_state.put_queue(event))
        except Exception as e:
            logger.debug(f"[WebDeployToolkit] Failed to emit event: {e}")
