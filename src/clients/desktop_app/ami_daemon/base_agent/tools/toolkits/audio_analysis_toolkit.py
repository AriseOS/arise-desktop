"""
AudioAnalysisToolkit - Audio analysis and transcription for multi-modal agent.

Uses OpenAI Whisper SDK directly for transcription (no CAMEL dependency).
Uses AnthropicProvider for audio reasoning/QA.
"""

import logging
from pathlib import Path
from typing import List, Optional

from openai import OpenAI

from src.common.llm import AnthropicProvider

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...workspace import get_working_directory

logger = logging.getLogger(__name__)


class AudioAnalysisToolkit(BaseToolkit):
    """A toolkit for audio processing and analysis.

    Uses OpenAI Whisper API directly for speech-to-text,
    and AnthropicProvider for reasoning about audio content.
    """

    agent_name: str = "multi_modal_agent"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        reasoning_provider: Optional[AnthropicProvider] = None,
        timeout: Optional[float] = 180.0,
        # Backward compatible kwargs (ignored)
        transcribe_model=None,
        audio_reasoning_model=None,
    ) -> None:
        """Initialize the AudioAnalysisToolkit.

        Args:
            cache_dir: Directory for caching downloaded audio files.
            api_key: OpenAI API key for Whisper.
            base_url: Custom API base URL.
            reasoning_provider: AnthropicProvider for audio reasoning/QA.
            timeout: Operation timeout in seconds.
            transcribe_model: Ignored (backward compatibility).
            audio_reasoning_model: Ignored (backward compatibility).
        """
        super().__init__(timeout=timeout)

        # Determine cache directory
        if cache_dir:
            self._cache_dir = cache_dir
        else:
            try:
                self._cache_dir = str(Path(get_working_directory()) / "audio_cache")
            except RuntimeError as e:
                import tempfile
                self._cache_dir = str(Path(tempfile.gettempdir()) / "ami_audio_cache")
                logger.warning(f"WorkingDirectoryManager not available: {e}. Using temp dir: {self._cache_dir}")

        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)

        # OpenAI client for Whisper
        self._openai_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

        # AnthropicProvider for reasoning
        self._reasoning_provider = reasoning_provider

        logger.info(f"AudioAnalysisToolkit initialized (cache_dir={self._cache_dir})")

    def _transcribe(self, audio_path: str) -> str:
        """Transcribe audio file using Whisper API.

        Args:
            audio_path: Path to audio file.

        Returns:
            Transcribed text.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        with open(audio_path, "rb") as audio_file:
            transcription = self._openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return transcription.text

    @listen_toolkit(
        inputs=lambda self, audio_path: f"Transcribing audio: {audio_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio to text.

        Args:
            audio_path: Path to the audio file.
                Supports MP3, WAV, OGG, and other common formats.

        Returns:
            Transcribed text from the audio.
        """
        logger.info(f"Transcribing audio: {audio_path}")
        return self._transcribe(audio_path)

    @listen_toolkit(
        inputs=lambda self, audio_path, question: f"Asking about audio: {question[:50]}...",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def ask_about_audio(self, audio_path: str, question: str) -> str:
        """Ask a question about audio content.

        Transcribes the audio first, then uses LLM to answer the question.

        Args:
            audio_path: Path to the audio file.
            question: Question to ask about the audio content.

        Returns:
            Answer to the question based on audio content.
        """
        logger.info(f"Asking about audio: {question}")

        # Transcribe first
        transcript = self._transcribe(audio_path)

        if not self._reasoning_provider:
            return f"Transcript:\n{transcript}\n\n(No reasoning provider to answer question)"

        # Use LLM to answer question about transcript
        import asyncio
        prompt = (
            f"<speech_transcription_result>{transcript}</speech_transcription_result>\n\n"
            f"Please answer: <question>{question}</question>"
        )

        async def _reason():
            response = await self._reasoning_provider.generate_with_tools(
                system_prompt="You are an expert audio analyst. Answer questions about the transcribed audio content.",
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                max_tokens=4096,
            )
            return response.get_text()

        return asyncio.run(_reason())

    @listen_toolkit(
        inputs=lambda self, audio_path: f"Summarizing audio: {audio_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def summarize_audio(self, audio_path: str) -> str:
        """Generate a summary of audio content.

        Args:
            audio_path: Path to the audio file.

        Returns:
            Summary of the audio content.
        """
        logger.info(f"Summarizing audio: {audio_path}")
        return self.ask_about_audio(
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
            audio_path: Path to the audio file.

        Returns:
            Information about speakers in the audio.
        """
        logger.info(f"Identifying speakers in audio: {audio_path}")
        return self.ask_about_audio(
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
        """Return a list of FunctionTool objects for this toolkit."""
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
