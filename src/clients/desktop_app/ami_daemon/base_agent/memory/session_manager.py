"""
Session Manager for Conversation Persistence

Simple session-based conversation management:
- Each session is a JSONL file
- Sessions timeout after 30 minutes of inactivity
- New sessions load context from previous session

Inspired by OpenClaw's session management pattern.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Session timeout in minutes
SESSION_TIMEOUT_MINUTES = 30

# Number of messages to carry over to new session
CONTEXT_MESSAGES_COUNT = 5


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"sess_{uuid.uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_message_id() -> str:
    """Generate a unique message ID."""
    return f"msg_{uuid.uuid4().hex[:8]}"


class SessionManager:
    """
    Manages conversation sessions with automatic timeout handling.

    Usage:
        manager = SessionManager()

        # Get or create session (handles timeout automatically)
        session = manager.get_active_session()

        # Append message
        manager.append_message("user", "Hello")
        manager.append_message("assistant", "Hi there!")

        # Load messages for display
        messages = manager.get_recent_messages(limit=50)
    """

    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize session manager.

        Args:
            base_path: Base directory for sessions. Defaults to ~/.ami/sessions/
        """
        if base_path is None:
            base_path = Path.home() / ".ami" / "sessions"

        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.index_path = self.base_path / "index.json"
        self._index_cache: Optional[Dict] = None

    # ==================== Index Management ====================

    def _load_index(self) -> Dict:
        """Load session index from disk."""
        if self._index_cache is not None:
            return self._index_cache

        if not self.index_path.exists():
            self._index_cache = {
                "current_session_id": None,
                "last_activity": None,
                "sessions": {},
            }
            return self._index_cache

        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                self._index_cache = json.load(f)
                return self._index_cache
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load session index: {e}")
            self._index_cache = {
                "current_session_id": None,
                "last_activity": None,
                "sessions": {},
            }
            return self._index_cache

    def _save_index(self) -> None:
        """Save session index to disk."""
        if self._index_cache is None:
            return

        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self._index_cache, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Failed to save session index: {e}")

    def _invalidate_cache(self) -> None:
        """Invalidate index cache."""
        self._index_cache = None

    # ==================== Session Lifecycle ====================

    def _is_session_expired(self) -> bool:
        """Check if current session has expired (30 min timeout)."""
        index = self._load_index()

        last_activity_str = index.get("last_activity")
        if not last_activity_str:
            logger.debug("Session expired: no last_activity")
            return True

        try:
            # Parse ISO format timestamp
            if last_activity_str.endswith("Z"):
                last_activity_str = last_activity_str[:-1] + "+00:00"
            last_activity = datetime.fromisoformat(last_activity_str)

            # Ensure timezone aware comparison
            now = datetime.now(timezone.utc)
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)

            timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            elapsed = now - last_activity
            expired = elapsed > timeout

            if expired:
                logger.debug(f"Session expired: last_activity={last_activity}, elapsed={elapsed}")

            return expired
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse last_activity: {e}")
            return True

    def _create_new_session(self, carry_context: bool = True) -> str:
        """
        Create a new session.

        Args:
            carry_context: Whether to carry messages from previous session

        Returns:
            New session ID
        """
        index = self._load_index()
        previous_session_id = index.get("current_session_id")

        # Generate new session
        new_session_id = generate_session_id()
        now = _utc_now_iso()

        # Create session file with header
        session_file = self.base_path / f"{new_session_id}.jsonl"
        header = {
            "type": "header",
            "session_id": new_session_id,
            "created_at": now,
            "previous_session_id": previous_session_id,
        }

        with open(session_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(header, ensure_ascii=False) + "\n")

        # Update index
        index["current_session_id"] = new_session_id
        index["last_activity"] = now
        index["sessions"][new_session_id] = {
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "previous_session_id": previous_session_id,
        }
        self._save_index()

        logger.info(f"Created new session: {new_session_id}")

        # Carry context from previous session
        if carry_context and previous_session_id:
            self._carry_context_from_previous(previous_session_id, new_session_id)

        return new_session_id

    def _carry_context_from_previous(self, previous_id: str, new_id: str) -> None:
        """Copy last N messages from previous session to new session as context."""
        previous_file = self.base_path / f"{previous_id}.jsonl"
        if not previous_file.exists():
            return

        # Read last N messages from previous session
        messages = []
        try:
            with open(previous_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("type") == "message":
                            messages.append(record)
                    except json.JSONDecodeError:
                        continue
        except IOError:
            return

        # Get last N messages
        context_messages = messages[-CONTEXT_MESSAGES_COUNT:]
        if not context_messages:
            return

        # Append to new session as context
        new_file = self.base_path / f"{new_id}.jsonl"
        with open(new_file, "a", encoding="utf-8") as f:
            for msg in context_messages:
                # Mark as context from previous session
                msg["is_context"] = True
                msg["from_session"] = previous_id
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        logger.debug(f"Carried {len(context_messages)} messages from {previous_id} to {new_id}")

    def get_active_session(self) -> str:
        """
        Get or create active session.

        If current session is expired (> 30 min), creates new session
        and carries context from previous session.

        Returns:
            Active session ID
        """
        index = self._load_index()

        # No current session or expired
        if not index.get("current_session_id") or self._is_session_expired():
            return self._create_new_session(carry_context=True)

        return index["current_session_id"]

    def force_new_session(self) -> str:
        """
        Force create a new session regardless of timeout.

        Returns:
            New session ID
        """
        return self._create_new_session(carry_context=True)

    # ==================== Message Operations ====================

    def append_message(
        self,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        attachments: Optional[List[Dict]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Append a message to the current session.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
            message_id: Optional message ID (auto-generated if not provided)
            attachments: Optional attachments
            metadata: Optional metadata

        Returns:
            Message ID
        """
        session_id = self.get_active_session()
        session_file = self.base_path / f"{session_id}.jsonl"

        if message_id is None:
            message_id = generate_message_id()

        now = _utc_now_iso()

        message = {
            "type": "message",
            "id": message_id,
            "role": role,
            "content": content,
            "timestamp": now,
        }

        if attachments:
            message["attachments"] = attachments
        if metadata:
            message["metadata"] = metadata

        # Append to file
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")

        # Update index
        index = self._load_index()
        index["last_activity"] = now
        if session_id in index["sessions"]:
            index["sessions"][session_id]["updated_at"] = now
            index["sessions"][session_id]["message_count"] = \
                index["sessions"][session_id].get("message_count", 0) + 1
        self._save_index()

        return message_id

    def get_messages(self, session_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Get messages from a session.

        Args:
            session_id: Session ID (defaults to current session)
            limit: Maximum messages to return

        Returns:
            List of message dicts (oldest to newest, limited to most recent)
        """
        if session_id is None:
            index = self._load_index()
            session_id = index.get("current_session_id")
            if not session_id:
                return []

        session_file = self.base_path / f"{session_id}.jsonl"
        if not session_file.exists():
            return []

        messages = []
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("type") == "message":
                            messages.append(record)
                    except json.JSONDecodeError:
                        continue
        except IOError:
            return []

        # Return most recent messages
        if len(messages) > limit:
            return messages[-limit:]
        return messages

    def get_recent_messages(self, limit: int = 50) -> List[Dict]:
        """
        Get recent messages from current session.

        Convenience method for loading messages on app start.

        Args:
            limit: Maximum messages to return

        Returns:
            List of recent messages
        """
        return self.get_messages(limit=limit)

    # ==================== Session Info ====================

    def get_current_session_id(self) -> Optional[str]:
        """Get current session ID without triggering timeout check."""
        index = self._load_index()
        return index.get("current_session_id")

    def get_session_info(self, session_id: Optional[str] = None) -> Optional[Dict]:
        """Get session metadata."""
        if session_id is None:
            session_id = self.get_current_session_id()
        if not session_id:
            return None

        index = self._load_index()
        return index.get("sessions", {}).get(session_id)

    def list_sessions(self, limit: int = 20) -> List[Dict]:
        """
        List recent sessions.

        Args:
            limit: Maximum sessions to return

        Returns:
            List of session info dicts, sorted by updated_at descending
        """
        index = self._load_index()
        sessions = []

        for session_id, info in index.get("sessions", {}).items():
            sessions.append({
                "session_id": session_id,
                **info,
            })

        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)

        return sessions[:limit]

    def touch_session(self) -> None:
        """Update last_activity timestamp without adding a message."""
        index = self._load_index()
        if index.get("current_session_id"):
            now = _utc_now_iso()
            index["last_activity"] = now
            self._save_index()
