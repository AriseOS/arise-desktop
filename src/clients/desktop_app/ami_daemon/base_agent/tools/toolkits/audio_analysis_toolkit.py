"""
AudioAnalysisToolkit - Audio analysis and transcription for multi-modal agent.

Based on Eigent's AudioAnalysisToolkit implementation which wraps CAMEL's toolkit.
Uses audio models for transcription and question answering.

References:
- Eigent: third-party/eigent/backend/app/utils/toolkit/audio_analysis_toolkit.py
- CAMEL: camel.toolkits.AudioAnalysisToolkit
"""

import logging
from pathlib import Path
from typing import List, Optional

from camel.models import BaseAudioModel, BaseModelBackend
from camel.toolkits import AudioAnalysisToolkit as CAMELAudioAnalysisToolkit

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...workspace import get_working_directory

logger = logging.getLogger(__name__)


class AudioAnalysisToolkit(BaseToolkit):
    """A toolkit for audio processing and analysis.

    Wraps CAMEL's AudioAnalysisToolkit to provide:
    - Audio transcription (speech-to-text)
    - Question answering about audio content
    - Processing of audio from local files and URLs

    Based on Eigent's implementation which wraps CAMEL's AudioAnalysisToolkit.
    """

    agent_name: str = "multi_modal_agent"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        transcribe_model: Optional[BaseAudioModel] = None,
        audio_reasoning_model: Optional[BaseModelBackend] = None,
        timeout: Optional[float] = 180.0,
    ) -> None:
        """Initialize the AudioAnalysisToolkit.

        Args:
            cache_dir: Directory for caching downloaded audio files.
                If not provided, uses task workspace from WorkingDirectoryManager.
            transcribe_model: Model for audio transcription.
                If not provided, CAMEL will use OpenAIAudioModels.
            audio_reasoning_model: Model for audio reasoning/QA.
                If not provided, CAMEL will use default ChatAgent model.
            timeout: Operation timeout in seconds.
        """
        super().__init__(timeout=timeout)

        # Determine cache directory
        if cache_dir:
            self._cache_dir = cache_dir
        else:
            try:
                self._cache_dir = str(Path(get_working_directory()) / "audio_cache")
            except RuntimeError as e:
                # WorkingDirectoryManager not initialized, use temp directory
                import tempfile
                self._cache_dir = str(Path(tempfile.gettempdir()) / "ami_audio_cache")
                logger.warning(f"WorkingDirectoryManager not available: {e}. Using temp dir: {self._cache_dir}")

        # Ensure cache directory exists
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)

        # Initialize CAMEL's toolkit with the provided models
        self._camel_toolkit = CAMELAudioAnalysisToolkit(
            cache_dir=self._cache_dir,
            transcribe_model=transcribe_model,
            audio_reasoning_model=audio_reasoning_model,
            timeout=timeout,
        )

        logger.info(f"AudioAnalysisToolkit initialized (cache_dir={self._cache_dir})")

    @listen_toolkit(
        inputs=lambda self, audio_path: f"Transcribing audio: {audio_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio to text.

        Args:
            audio_path: Path to the audio file or URL.
                Supports MP3, WAV, OGG, and other common formats.

        Returns:
            Transcribed text from the audio.
        """
        logger.info(f"Transcribing audio: {audio_path}")
        return self._camel_toolkit.audio2text(audio_path=audio_path)

    @listen_toolkit(
        inputs=lambda self, audio_path, question: f"Asking about audio: {question[:50]}...",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def ask_about_audio(self, audio_path: str, question: str) -> str:
        """Ask a question about audio content.

        Uses either direct audio question answering (if supported by model)
        or transcription-based approach as fallback.

        Args:
            audio_path: Path to the audio file or URL.
            question: Question to ask about the audio content.

        Returns:
            Answer to the question based on audio content.
        """
        logger.info(f"Asking about audio: {question}")
        return self._camel_toolkit.ask_question_about_audio(
            audio_path=audio_path,
            question=question,
        )

    @listen_toolkit(
        inputs=lambda self, audio_path: f"Summarizing audio: {audio_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def summarize_audio(self, audio_path: str) -> str:
        """Generate a summary of audio content.

        Args:
            audio_path: Path to the audio file or URL.

        Returns:
            Summary of the audio content.
        """
        logger.info(f"Summarizing audio: {audio_path}")
        return self._camel_toolkit.ask_question_about_audio(
            audio_path=audio_path,
            question=(
                "Please provide a comprehensive summary of this audio. "
                "Include the main topics discussed, key points made, "
                "and any important conclusions or takeaways."
            ),
        )

    @listen_toolkit(
        inputs=lambda self, audio_path: f"Extracting speakers from: {audio_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def identify_speakers(self, audio_path: str) -> str:
        """Identify and describe speakers in the audio.

        Args:
            audio_path: Path to the audio file or URL.

        Returns:
            Information about speakers in the audio.
        """
        logger.info(f"Identifying speakers in audio: {audio_path}")
        return self._camel_toolkit.ask_question_about_audio(
            audio_path=audio_path,
            question=(
                "How many speakers are in this audio? "
                "Please describe each speaker's voice characteristics, "
                "their role in the conversation (if apparent), "
                "and summarize what each speaker says."
            ),
        )

    @property
    def cache_directory(self) -> str:
        """Get the cache directory for downloaded audio files."""
        return self._cache_dir

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.transcribe_audio),
            FunctionTool(self.ask_about_audio),
            FunctionTool(self.summarize_audio),
            FunctionTool(self.identify_speakers),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "AudioAnalysis"
