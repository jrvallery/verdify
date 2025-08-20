"""
Transcription module using whisper.cpp for voice note ingestion pipeline.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from models import ContextInfo
from config import Config

logger = logging.getLogger(__name__)


class TranscriptionResult:
    """Represents the result of transcription."""
    
    def __init__(self, text: str, segments: List[Dict[str, Any]], language: str, model: str):
        self.text = text
        self.segments = segments
        self.language = language
        self.model = model
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "segments": self.segments,
            "language": self.language,
            "model": self.model
        }
    
    def get_formatted_transcript(self, include_timestamps: bool = True) -> str:
        """Get formatted transcript with optional timestamps."""
        if not include_timestamps:
            return self.text
        
        formatted_lines = []
        for segment in self.segments:
            start_time = self._format_timestamp(segment.get("start", 0))
            end_time = self._format_timestamp(segment.get("end", 0))
            text = segment.get("text", "").strip()
            
            if text:
                formatted_lines.append(f"[{start_time} -> {end_time}] {text}")
        
        return "\n".join(formatted_lines)
    
    def get_speakers_transcript(self, speaker_labels: Optional[Dict[str, str]] = None) -> str:
        """Get transcript with speaker labels if available."""
        if not self.segments:
            return self.text
        
        formatted_lines = []
        current_speaker = None
        
        for segment in self.segments:
            speaker_id = segment.get("speaker")
            text = segment.get("text", "").strip()
            
            if not text:
                continue
            
            # Determine speaker name
            if speaker_id and speaker_labels:
                speaker_name = speaker_labels.get(f"speaker_{speaker_id}", f"Speaker {speaker_id}")
            elif speaker_id:
                speaker_name = f"Speaker {speaker_id}"
            else:
                speaker_name = None
            
            # Add speaker label if changed
            if speaker_name and speaker_name != current_speaker:
                formatted_lines.append(f"\n**{speaker_name}:**")
                current_speaker = speaker_name
            
            # Add timestamp and text
            start_time = self._format_timestamp(segment.get("start", 0))
            formatted_lines.append(f"[{start_time}] {text}")
        
        return "\n".join(formatted_lines)
    
    def _format_timestamp(self, seconds: float) -> str:
        """Format timestamp as MM:SS."""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"


class Transcriber:
    """Handles audio transcription using whisper.cpp."""
    
    def __init__(self, config: Config):
        self.config = config
        self.transcription_config = config.processing.transcription
    
    def transcribe(
        self, 
        audio_path: Path, 
        context: Optional[ContextInfo] = None,
        diarization: bool = False
    ) -> TranscriptionResult:
        """Transcribe audio file using whisper.cpp."""
        
        # Build whisper.cpp command
        cmd = self._build_whisper_command(audio_path, diarization)
        
        try:
            # Create temporary file for JSON output
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                json_output_path = Path(temp_file.name)
            
            # Add JSON output to command
            cmd.extend(["-oj", str(json_output_path)])
            
            logger.info(f"Starting transcription: {audio_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse JSON output
            with open(json_output_path, 'r') as f:
                transcript_data = json.load(f)
            
            # Clean up temporary file
            json_output_path.unlink(missing_ok=True)
            
            return self._parse_whisper_output(transcript_data)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Whisper transcription failed: {e}")
            logger.error(f"Whisper stderr: {e.stderr}")
            raise
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Failed to parse whisper output: {e}")
            raise
    
    def transcribe_split_channels(
        self, 
        channel_files: List[Path],
        context: Optional[ContextInfo] = None
    ) -> List[TranscriptionResult]:
        """Transcribe multiple channel files separately."""
        results = []
        
        for i, channel_file in enumerate(channel_files):
            logger.info(f"Transcribing channel {i+1}: {channel_file}")
            result = self.transcribe(channel_file, context, diarization=False)
            results.append(result)
        
        return results
    
    def merge_channel_transcripts(
        self, 
        channel_results: List[TranscriptionResult],
        speaker_labels: Optional[Dict[str, str]] = None
    ) -> TranscriptionResult:
        """Merge transcripts from multiple channels into a timeline."""
        
        # Collect all segments with channel information
        all_segments = []
        for channel_idx, result in enumerate(channel_results):
            for segment in result.segments:
                segment_copy = segment.copy()
                segment_copy["channel"] = channel_idx
                if speaker_labels:
                    channel_name = ["left", "right"][channel_idx]
                    segment_copy["speaker"] = speaker_labels.get(channel_name, f"Channel {channel_idx + 1}")
                all_segments.append(segment_copy)
        
        # Sort by timestamp
        all_segments.sort(key=lambda x: x.get("start", 0))
        
        # Merge text
        merged_text = " ".join(segment.get("text", "").strip() for segment in all_segments if segment.get("text", "").strip())
        
        # Use metadata from first channel
        first_result = channel_results[0] if channel_results else None
        language = first_result.language if first_result else "en"
        model = first_result.model if first_result else "unknown"
        
        return TranscriptionResult(
            text=merged_text,
            segments=all_segments,
            language=language,
            model=model
        )
    
    def _build_whisper_command(self, audio_path: Path, diarization: bool = False) -> List[str]:
        """Build whisper.cpp command with appropriate options."""
        cmd = ["whisper"]  # Assuming whisper.cpp binary is in PATH
        
        # Input file
        cmd.extend(["-f", str(audio_path)])
        
        # Model
        cmd.extend(["-m", self.transcription_config.model])
        
        # Language
        cmd.extend(["-l", self.transcription_config.language])
        
        # Threading
        cmd.extend(["-t", str(self.transcription_config.threads)])
        
        # FP16 precision
        if self.transcription_config.fp16:
            cmd.append("--fp16")
        
        # Diarization
        if diarization:
            cmd.append("-tdrz")
        
        # Output format - JSON for parsing
        cmd.append("-oj")
        
        return cmd
    
    def _parse_whisper_output(self, transcript_data: Dict[str, Any]) -> TranscriptionResult:
        """Parse whisper.cpp JSON output."""
        
        # Extract text
        text = transcript_data.get("text", "").strip()
        
        # Extract segments
        segments = transcript_data.get("transcription", [])
        
        # Extract metadata
        language = transcript_data.get("language", "en")
        model = transcript_data.get("model", "unknown")
        
        return TranscriptionResult(
            text=text,
            segments=segments,
            language=language,
            model=model
        )
    
    def validate_whisper(self) -> bool:
        """Validate that whisper.cpp is available and working."""
        try:
            # Try to run whisper with help flag
            result = subprocess.run(["whisper", "--help"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.debug("whisper.cpp is available")
                return True
            else:
                logger.error("whisper.cpp is not working properly")
                return False
        except FileNotFoundError:
            logger.error("whisper.cpp not found in PATH")
            return False
    
    def get_model_path(self) -> Optional[Path]:
        """Get the path to the whisper model file."""
        # This would depend on how whisper.cpp models are organized
        # For now, assume models are managed by whisper.cpp itself
        return None