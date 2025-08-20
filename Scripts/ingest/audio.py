#!/usr/bin/env python3
"""
Audio processing module for voice note ingestion.
Handles transcoding, normalization, filtering, and content hash generation.
"""

import os
import subprocess
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import tempfile

try:
    from pydub import AudioSegment
    from pydub.utils import which
except ImportError:
    AudioSegment = None
    which = None


class AudioProfile:
    """Audio processing profiles for different scenarios."""
    
    AUTO = "auto"
    CALL = "call"      # Telephony - optimize for speech clarity
    WIND = "wind"      # Outdoor - wind/noise reduction
    WIDE = "wide"      # High-quality - preserve full spectrum


class AudioProcessor:
    """Handles audio processing and normalization."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        
        # Check for required tools
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if required audio tools are available."""
        # Check for FFmpeg
        if which and not which("ffmpeg"):
            self.logger.warning("FFmpeg not found - audio processing may be limited")
        elif not which:
            self.logger.warning("pydub not available - cannot check for FFmpeg")
            
        # Check for pydub
        if AudioSegment is None:
            self.logger.warning("pydub not available - falling back to FFmpeg only")
    
    def calculate_content_hash(self, audio_file: Path) -> str:
        """
        Calculate content hash of decoded 16kHz mono PCM data.
        This provides content-based deduplication across different file formats.
        """
        self.logger.debug(f"Calculating content hash for: {audio_file}")
        
        # Create temporary file for normalized PCM
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Convert to 16kHz mono PCM using FFmpeg
            cmd = [
                "ffmpeg", "-i", str(audio_file),
                "-ar", "16000",          # 16kHz sample rate
                "-ac", "1",              # Mono
                "-f", "wav",             # WAV format
                "-acodec", "pcm_s16le",  # 16-bit PCM
                "-y",                    # Overwrite output
                str(temp_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error(f"FFmpeg error: {result.stderr}")
                raise RuntimeError(f"Failed to normalize audio for content hash")
            
            # Calculate hash of the normalized PCM data (skip WAV header)
            sha256_hash = hashlib.sha256()
            with open(temp_path, "rb") as f:
                # Skip WAV header (44 bytes)
                f.seek(44)
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            
            content_hash = sha256_hash.hexdigest()
            self.logger.debug(f"Content hash: {content_hash}")
            return content_hash
            
        finally:
            # Clean up temporary file
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
    
    def process_audio(self, input_file: Path, output_dir: Path, 
                     context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process audio file with appropriate filters and normalization.
        
        Args:
            input_file: Path to input audio file
            output_dir: Directory to save processed audio
            context: Processing context (profile, flags, etc.)
            
        Returns:
            Dictionary with processing results
        """
        self.logger.info(f"Processing audio: {input_file}")
        
        # Determine audio profile
        profile = self._detect_profile(input_file, context)
        
        # Analyze audio properties
        audio_info = self._analyze_audio(input_file)
        
        # Process based on profile and properties
        result = {
            'profile': profile,
            'input_info': audio_info,
            'channels': audio_info.get('channels', 1),
            'duration': audio_info.get('duration', 0.0),
            'sample_rate': audio_info.get('sample_rate', 44100)
        }
        
        # Check for split-channel processing
        if self._should_split_channels(audio_info, context):
            result.update(self._process_split_channels(input_file, output_dir, profile))
        else:
            result.update(self._process_single_channel(input_file, output_dir, profile))
        
        return result
    
    def _detect_profile(self, input_file: Path, context: Dict[str, Any]) -> str:
        """Detect appropriate audio processing profile."""
        # Check for explicit profile in context
        if 'audio_profile' in context:
            return context['audio_profile']
        
        # Check for call flag
        if context.get('is_call', False):
            return AudioProfile.CALL
        
        # Check filename for hints
        filename_lower = input_file.name.lower()
        if 'call' in filename_lower or 'phone' in filename_lower:
            return AudioProfile.CALL
        if 'wind' in filename_lower or 'outdoor' in filename_lower:
            return AudioProfile.WIND
        if 'hd' in filename_lower or 'hifi' in filename_lower:
            return AudioProfile.WIDE
        
        # Auto-detect based on audio properties
        audio_info = self._analyze_audio(input_file)
        
        # Low sample rate suggests telephony
        if audio_info.get('sample_rate', 44100) <= 8000:
            return AudioProfile.CALL
        
        # High quality suggests wide profile
        if audio_info.get('sample_rate', 44100) >= 48000 and audio_info.get('channels', 1) >= 2:
            return AudioProfile.WIDE
        
        return AudioProfile.AUTO
    
    def _analyze_audio(self, input_file: Path) -> Dict[str, Any]:
        """Analyze audio file properties using FFprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(input_file)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.warning(f"FFprobe failed: {result.stderr}")
                return {}
                
            data = json.loads(result.stdout)
            
            # Find audio stream
            audio_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'audio':
                    audio_stream = stream
                    break
            
            if not audio_stream:
                return {}
            
            return {
                'duration': float(data.get('format', {}).get('duration', 0)),
                'sample_rate': int(audio_stream.get('sample_rate', 44100)),
                'channels': int(audio_stream.get('channels', 1)),
                'codec': audio_stream.get('codec_name', 'unknown'),
                'bitrate': int(audio_stream.get('bit_rate', 0)) if audio_stream.get('bit_rate') else 0
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to analyze audio: {e}")
            return {}
    
    def _should_split_channels(self, audio_info: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Determine if we should process channels separately."""
        # Explicit flag
        if context.get('force_split', False):
            return True
        
        # Auto-detect: stereo recordings that might be dual-mic
        channels = audio_info.get('channels', 1)
        duration = audio_info.get('duration', 0)
        
        # Split if stereo and long enough to be a conversation
        return channels == 2 and duration > 30  # 30 seconds minimum
    
    def _process_single_channel(self, input_file: Path, output_dir: Path, 
                               profile: str) -> Dict[str, Any]:
        """Process audio as single channel/mono."""
        output_file = output_dir / "normalized.wav"
        
        # Build FFmpeg filter chain based on profile
        filters = self._build_filter_chain(profile, channels=1)
        
        cmd = [
            "ffmpeg", "-i", str(input_file),
            "-ar", "16000",           # 16kHz sample rate
            "-ac", "1",               # Force mono
            "-af", filters,           # Apply filters
            "-f", "wav",              # WAV output
            "-acodec", "pcm_s16le",   # 16-bit PCM
            "-y",                     # Overwrite
            str(output_file)
        ]
        
        self.logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.logger.error(f"FFmpeg processing failed: {result.stderr}")
            raise RuntimeError("Audio processing failed")
        
        return {
            'normalized_file': str(output_file),
            'processing_mode': 'single_channel',
            'filters_applied': filters
        }
    
    def _process_split_channels(self, input_file: Path, output_dir: Path,
                               profile: str) -> Dict[str, Any]:
        """Process stereo audio as separate left/right channels."""
        left_file = output_dir / "normalized_left.wav"
        right_file = output_dir / "normalized_right.wav"
        merged_file = output_dir / "normalized.wav"
        
        # Build filter chain
        filters = self._build_filter_chain(profile, channels=1)
        
        # Process left channel
        cmd_left = [
            "ffmpeg", "-i", str(input_file),
            "-ar", "16000",
            "-ac", "1",
            "-af", f"pan=mono|c0=0.5*c0,{filters}",  # Extract left + apply filters
            "-f", "wav",
            "-acodec", "pcm_s16le",
            "-y",
            str(left_file)
        ]
        
        # Process right channel  
        cmd_right = [
            "ffmpeg", "-i", str(input_file),
            "-ar", "16000", 
            "-ac", "1",
            "-af", f"pan=mono|c0=0.5*c1,{filters}",  # Extract right + apply filters
            "-f", "wav",
            "-acodec", "pcm_s16le",
            "-y",
            str(right_file)
        ]
        
        # Create merged version (for fallback)
        cmd_merged = [
            "ffmpeg", "-i", str(input_file),
            "-ar", "16000",
            "-ac", "1",
            "-af", filters,
            "-f", "wav", 
            "-acodec", "pcm_s16le",
            "-y",
            str(merged_file)
        ]
        
        for cmd in [cmd_left, cmd_right, cmd_merged]:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error(f"FFmpeg split processing failed: {result.stderr}")
                raise RuntimeError("Split-channel audio processing failed")
        
        return {
            'normalized_file': str(merged_file),
            'left_channel_file': str(left_file),
            'right_channel_file': str(right_file),
            'processing_mode': 'split_channels',
            'filters_applied': filters
        }
    
    def _build_filter_chain(self, profile: str, channels: int) -> str:
        """Build FFmpeg filter chain based on profile."""
        filters = []
        
        if profile == AudioProfile.CALL:
            # Telephony optimization
            filters.extend([
                "highpass=f=80",           # Remove very low frequencies
                "lowpass=f=8000",          # Remove high frequencies beyond speech
                "dynaudnorm=p=0.9:s=5",    # Dynamic range compression
                "alimiter=limit=0.9"       # Soft limiting
            ])
            
        elif profile == AudioProfile.WIND:
            # Outdoor/wind noise reduction
            filters.extend([
                "highpass=f=120",          # More aggressive low-cut for wind
                "lowpass=f=12000",         # Preserve speech clarity
                "afftdn=nr=10:nf=-20",     # Noise reduction
                "dynaudnorm=p=0.85:s=3",   # Gentle compression
                "alimiter=limit=0.85"
            ])
            
        elif profile == AudioProfile.WIDE:
            # High-quality, full spectrum
            filters.extend([
                "highpass=f=20",           # Minimal low-cut
                "dynaudnorm=p=0.95:s=10",  # Very gentle compression
                "alimiter=limit=0.95"      # Conservative limiting
            ])
            
        else:  # AUTO
            # Balanced processing
            filters.extend([
                "highpass=f=60",           # Remove rumble
                "lowpass=f=16000",         # Preserve most audio content
                "dynaudnorm=p=0.9:s=7",    # Moderate compression
                "alimiter=limit=0.9"       # Standard limiting
            ])
        
        return ",".join(filters)