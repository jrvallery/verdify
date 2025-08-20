"""
Audio processing module for voice note ingestion pipeline.
"""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

from models import AudioMetadata, AudioProfile, HashInfo
from config import Config, ProcessingProfile

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Handles audio processing, format conversion, and metadata extraction."""
    
    def __init__(self, config: Config):
        self.config = config
        self.processing_config = config.processing
    
    def probe_audio(self, file_path: Path) -> AudioMetadata:
        """Extract audio metadata using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(file_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(result.stdout)
            
            # Find the first audio stream
            audio_stream = None
            for stream in probe_data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break
            
            if not audio_stream:
                raise ValueError("No audio stream found in file")
            
            format_info = probe_data.get("format", {})
            
            return AudioMetadata(
                duration=float(format_info.get("duration", 0)),
                sample_rate=int(audio_stream.get("sample_rate", 0)),
                channels=int(audio_stream.get("channels", 0)),
                bitrate=int(format_info.get("bit_rate", 0)) if format_info.get("bit_rate") else None,
                format=format_info.get("format_name", "unknown"),
                codec=audio_stream.get("codec_name"),
                file_size=int(format_info.get("size", 0))
            )
            
        except subprocess.CalledProcessError as e:
            logger.error(f"ffprobe failed for {file_path}: {e}")
            raise
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse ffprobe output for {file_path}: {e}")
            raise
    
    def detect_profile(self, metadata: AudioMetadata) -> AudioProfile:
        """Auto-detect appropriate processing profile based on audio characteristics."""
        # Simple heuristics for profile detection
        if metadata.sample_rate <= 8000 or (metadata.sample_rate <= 16000 and metadata.channels == 1):
            return AudioProfile.CALL
        elif metadata.sample_rate >= 44100 and metadata.channels >= 2:
            return AudioProfile.WIDE
        else:
            return AudioProfile.AUTO
    
    def get_processing_filters(self, profile: AudioProfile) -> List[str]:
        """Get FFmpeg filter chain for the specified profile."""
        profile_config = self.processing_config.profiles.get(profile.value)
        if not profile_config:
            logger.warning(f"Profile {profile.value} not found, using auto")
            profile_config = self.processing_config.profiles["auto"]
        
        return profile_config.filters
    
    def convert_to_pcm(self, input_path: Path, output_path: Path, profile: AudioProfile) -> Path:
        """Convert audio to standardized PCM format for hash computation and processing."""
        filters = self.get_processing_filters(profile)
        filter_chain = ",".join(filters)
        
        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-ar", str(self.processing_config.sample_rate),
            "-ac", str(self.processing_config.channels),
            "-af", filter_chain,
            "-f", "wav",
            "-y",  # Overwrite output file
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"FFmpeg conversion successful: {input_path} -> {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion failed: {e}")
            logger.error(f"FFmpeg stderr: {e.stderr}")
            raise
    
    def compute_pcm_hash(self, pcm_file: Path) -> str:
        """Compute SHA256 hash of PCM data for content-based deduplication."""
        sha256_hash = hashlib.sha256()
        
        # Hash only the PCM data, not the WAV header
        with open(pcm_file, "rb") as f:
            # Skip WAV header (typically 44 bytes)
            wav_header = f.read(44)
            if not wav_header.startswith(b"RIFF"):
                # Not a proper WAV file, hash the whole file
                f.seek(0)
            
            # Hash the PCM data in chunks
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def compute_hashes(self, file_path: Path, profile: AudioProfile) -> HashInfo:
        """Compute both file hash and content hash."""
        # File hash (raw file)
        sha256_file = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_file.update(chunk)
        file_hash = sha256_file.hexdigest()
        
        # Content hash (processed PCM)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            self.convert_to_pcm(file_path, temp_path, profile)
            pcm_hash = self.compute_pcm_hash(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
        
        return HashInfo(sha256_file=file_hash, sha256_pcm=pcm_hash)
    
    def process_split_channels(self, input_path: Path, output_dir: Path, profile: AudioProfile) -> List[Path]:
        """Process split-channel audio (L/R extraction for dual-mic recordings)."""
        output_paths = []
        
        for channel_index, channel_name in enumerate(["left", "right"]):
            output_path = output_dir / f"{input_path.stem}_{channel_name}.wav"
            
            filters = self.get_processing_filters(profile)
            # Add channel extraction filter
            channel_filter = f"pan=mono|c0=c{channel_index}"
            filters.insert(0, channel_filter)
            filter_chain = ",".join(filters)
            
            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-ar", str(self.processing_config.sample_rate),
                "-ac", "1",  # Force mono output
                "-af", filter_chain,
                "-f", "wav",
                "-y",
                str(output_path)
            ]
            
            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                output_paths.append(output_path)
                logger.info(f"Extracted {channel_name} channel: {output_path}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to extract {channel_name} channel: {e}")
                raise
        
        return output_paths
    
    def validate_tools(self) -> bool:
        """Validate that required audio processing tools are available."""
        tools = ["ffmpeg", "ffprobe"]
        
        for tool in tools:
            try:
                subprocess.run([tool, "-version"], capture_output=True, check=True)
                logger.debug(f"{tool} is available")
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.error(f"Required tool not found: {tool}")
                return False
        
        return True