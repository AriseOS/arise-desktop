"""
Recording Service - Workflow recording functionality
Chrome extension based recording - operations are sent from extension
"""
import uuid
from typing import Dict, Optional, List
from datetime import datetime

class RecordingSession:
    """Recording session for a single workflow recording"""

    def __init__(self, session_id: str, title: str, description: str, user_id: int):
        self.session_id = session_id
        self.title = title
        self.description = description
        self.user_id = user_id
        self.created_at = datetime.now()
        self.operation_list = []
        self.is_recording = False

    async def start(self):
        """Start recording session"""
        try:
            self.is_recording = True
            print(f"✅ Recording session started: {self.session_id}")
            print(f"📋 Session ready to receive operations from Chrome extension")

            return {
                "success": True,
                "session_id": self.session_id,
                "message": "Recording started"
            }
        except Exception as e:
            print(f"❌ Failed to start recording: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }

    def add_operation(self, operation: dict):
        """Add a captured operation to the list"""
        self.operation_list.append(operation)
        print(f"📝 Operation added: {operation.get('type', 'unknown')} (total: {len(self.operation_list)})")

    async def stop(self):
        """Stop recording session and return captured operations"""
        try:
            self.is_recording = False

            print(f"✅ Recording session stopped: {self.session_id}")
            print(f"   Captured {len(self.operation_list)} operations")

            return {
                "success": True,
                "session_id": self.session_id,
                "operations": self.operation_list,
                "operation_count": len(self.operation_list)
            }
        except Exception as e:
            print(f"❌ Failed to stop recording: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }

    async def get_status(self):
        """Get current recording status"""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "description": self.description,
            "is_recording": self.is_recording,
            "operation_count": len(self.operation_list),
            "created_at": self.created_at.isoformat()
        }


class RecordingService:
    """Service to manage workflow recording sessions"""

    def __init__(self):
        self.active_sessions: Dict[str, RecordingSession] = {}
        print("🎬 RecordingService initialized")

    async def create_session(self, title: str, description: str, user_id: int) -> Dict:
        """Create a new recording session"""
        session_id = f"rec_{uuid.uuid4().hex[:12]}"

        # Clean up any old inactive sessions for this user first
        sessions_to_remove = []
        for sid, s in self.active_sessions.items():
            if s.user_id == user_id and not s.is_recording:
                sessions_to_remove.append(sid)

        for sid in sessions_to_remove:
            del self.active_sessions[sid]
            print(f"🧹 Cleaned up inactive session: {sid}")

        # Check if user already has an ACTIVE recording session
        user_sessions = [s for s in self.active_sessions.values()
                        if s.user_id == user_id and s.is_recording]

        if user_sessions:
            return {
                "success": False,
                "error": "User already has an active recording session"
            }

        # Create new session
        session = RecordingSession(session_id, title, description, user_id)
        self.active_sessions[session_id] = session

        # Start recording
        result = await session.start()

        if not result["success"]:
            # Clean up if failed to start
            del self.active_sessions[session_id]

        return result

    async def stop_session(self, session_id: str, user_id: int) -> Dict:
        """Stop a recording session"""
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "error": "Recording session not found"
            }

        session = self.active_sessions[session_id]

        # Verify user owns this session
        if session.user_id != user_id:
            return {
                "success": False,
                "error": "Unauthorized"
            }

        # Stop recording
        result = await session.stop()

        # Keep session for a while to allow retrieving results
        # In production, you might want to save to database instead

        return result

    async def get_session_status(self, session_id: str, user_id: int) -> Optional[Dict]:
        """Get status of a recording session"""
        if session_id not in self.active_sessions:
            return None

        session = self.active_sessions[session_id]

        # Verify user owns this session
        if session.user_id != user_id:
            return None

        return await session.get_status()

    async def get_session_data(self, session_id: str, user_id: int) -> Optional[Dict]:
        """Get complete session data for export"""
        if session_id not in self.active_sessions:
            return None

        session = self.active_sessions[session_id]

        # Verify user owns this session
        if session.user_id != user_id:
            return None

        return {
            "title": session.title,
            "description": session.description,
            "start_time": session.created_at.isoformat(),
            "operations": session.operation_list
        }

    def cleanup_session(self, session_id: str):
        """Remove a completed session from memory"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            print(f"🧹 Cleaned up session: {session_id}")


# Global service instance
recording_service = RecordingService()
