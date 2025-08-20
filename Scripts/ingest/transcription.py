#!/usr/bin/env python3
"""
Transcription engine using whisper.cpp for voice note processing.
Handles single-channel and multi-speaker transcription with diarization.
"""

import os
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import tempfile
from datetime import datetime, timezone


class TranscriptionEngine:
    """Handles audio transcription using whisper.cpp."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        
        # Default model and settings
        self.model = "large-v3"
        self.model_path = self._find_whisper_model()
        
        # Check dependencies
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if whisper.cpp is available."""
        if not self._find_whisper_executable():
            self.logger.warning("whisper.cpp not found - transcription may fail")
            self.logger.info("Install whisper.cpp: https://github.com/ggerganov/whisper.cpp")
    
    def _find_whisper_executable(self) -> Optional[str]:
        """Find whisper.cpp executable."""
        # Common locations
        possible_paths = [
            "whisper",
            "whisper.cpp",
            "/usr/local/bin/whisper",
            "/opt/homebrew/bin/whisper",
            "~/whisper.cpp/main"
        ]
        
        for path in possible_paths:
            expanded_path = Path(path).expanduser()
            if expanded_path.exists() and expanded_path.is_file():
                return str(expanded_path)
        
        # Try which command
        try:
            result = subprocess.run(["which", "whisper"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
            
        return None
    
    def _find_whisper_model(self) -> Optional[str]:
        """Find whisper model file."""
        model_name = f"ggml-{self.model}.bin"
        
        # Common model locations
        possible_locations = [
            f"~/whisper.cpp/models/{model_name}",
            f"/usr/local/share/whisper/{model_name}",
            f"/opt/homebrew/share/whisper/{model_name}",
            f"~/.whisper/{model_name}",
            f"./models/{model_name}"
        ]
        
        for location in possible_locations:
            path = Path(location).expanduser()
            if path.exists():
                return str(path)
        
        self.logger.warning(f"Whisper model {model_name} not found")
        return None
    
    def transcribe(self, audio_result: Dict[str, Any], output_dir: Path,
                  context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transcribe audio file(s) to text with timestamps.
        
        Args:
            audio_result: Result from audio processing
            output_dir: Directory to save transcription files
            context: Processing context
            
        Returns:
            Dictionary with transcription results
        """
        self.logger.info("Starting transcription")
        
        processing_mode = audio_result.get('processing_mode', 'single_channel')
        
        if processing_mode == 'split_channels':
            return self._transcribe_split_channels(audio_result, output_dir, context)
        else:
            return self._transcribe_single_channel(audio_result, output_dir, context)
    
    def _transcribe_single_channel(self, audio_result: Dict[str, Any], 
                                  output_dir: Path, context: Dict[str, Any]) -> Dict[str, Any]:
        """Transcribe single channel audio."""
        normalized_file = Path(audio_result['normalized_file'])
        
        # Determine if we need diarization
        use_diarization = self._should_use_diarization(audio_result, context)
        
        # Generate transcription
        transcript_data = self._run_whisper(
            normalized_file, 
            output_dir,
            use_diarization=use_diarization,
            speaker_names=context.get('speaker_names', [])
        )
        
        # Save transcript files
        self._save_transcript_files(transcript_data, output_dir)
        
        # Generate metadata
        meta_data = {
            'transcription_method': 'single_channel',
            'model': self.model,
            'diarization_enabled': use_diarization,
            'processing_time': transcript_data.get('processing_time', 0),
            'language': transcript_data.get('language', 'unknown'),
            'confidence': transcript_data.get('confidence', 0.0),
            'speaker_count': len(transcript_data.get('speakers', [])),
            'word_count': len(transcript_data.get('text', '').split()),
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Save metadata
        meta_file = output_dir / "meta.json"
        with open(meta_file, 'w') as f:
            json.dump(meta_data, f, indent=2)
        
        return {
            'transcript_file': str(output_dir / "transcript.txt"),
            'srt_file': str(output_dir / "transcript.srt"),
            'vtt_file': str(output_dir / "transcript.vtt"),
            'meta_file': str(meta_file),
            'meta_data': meta_data,
            'transcript_text': transcript_data.get('text', '')
        }
    
    def _transcribe_split_channels(self, audio_result: Dict[str, Any],
                                  output_dir: Path, context: Dict[str, Any]) -> Dict[str, Any]:
        """Transcribe split channels separately and merge timelines."""
        left_file = Path(audio_result['left_channel_file'])
        right_file = Path(audio_result['right_channel_file'])
        
        # Get speaker names if provided
        speaker_names = context.get('speaker_names', ['Speaker 1', 'Speaker 2'])
        
        # Transcribe each channel
        left_transcript = self._run_whisper(left_file, output_dir, prefix="left_")
        right_transcript = self._run_whisper(right_file, output_dir, prefix="right_")
        
        # Merge transcripts with speaker attribution
        merged_transcript = self._merge_channel_transcripts(
            left_transcript, right_transcript, speaker_names
        )
        
        # Save merged transcript files
        self._save_transcript_files(merged_transcript, output_dir)
        
        # Generate metadata
        meta_data = {
            'transcription_method': 'split_channels',
            'model': self.model,
            'speaker_names': speaker_names,
            'left_processing_time': left_transcript.get('processing_time', 0),
            'right_processing_time': right_transcript.get('processing_time', 0),
            'language': merged_transcript.get('language', 'unknown'),
            'word_count': len(merged_transcript.get('text', '').split()),
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Save metadata
        meta_file = output_dir / "meta.json"
        with open(meta_file, 'w') as f:
            json.dump(meta_data, f, indent=2)
        
        return {
            'transcript_file': str(output_dir / "transcript.txt"),
            'srt_file': str(output_dir / "transcript.srt"),
            'vtt_file': str(output_dir / "transcript.vtt"),
            'meta_file': str(meta_file),
            'meta_data': meta_data,
            'transcript_text': merged_transcript.get('text', '')
        }
    
    def _should_use_diarization(self, audio_result: Dict[str, Any], 
                               context: Dict[str, Any]) -> bool:
        """Determine if we should use speaker diarization."""
        # Explicit flag
        if 'use_diarization' in context:
            return context['use_diarization']
        
        # Auto-detect based on duration and context
        duration = audio_result.get('duration', 0)
        
        # Use diarization for longer recordings that might have multiple speakers
        if duration > 120:  # 2 minutes
            return True
        
        # Use if call recording
        if context.get('is_call', False):
            return True
        
        # Use if multiple speaker names provided
        if len(context.get('speaker_names', [])) > 1:
            return True
        
        return False
    
    def _run_whisper(self, audio_file: Path, output_dir: Path, 
                    prefix: str = "", use_diarization: bool = False,
                    speaker_names: List[str] = None) -> Dict[str, Any]:
        """Run whisper.cpp on audio file."""
        whisper_exe = self._find_whisper_executable()
        if not whisper_exe:
            raise RuntimeError("whisper.cpp executable not found")
        
        # Prepare output files
        output_txt = output_dir / f"{prefix}raw_transcript.txt"
        output_json = output_dir / f"{prefix}raw_transcript.json"
        
        # Build whisper command
        cmd = [
            whisper_exe,
            "-f", str(audio_file),           # Input file
            "-ot", str(output_txt),          # Text output
            "-oj", str(output_json),         # JSON output
            "-l", "auto",                    # Auto-detect language
            "-t", "4",                       # Threads
            "--print-progress"               # Show progress
        ]
        
        # Add model if available
        if self.model_path:
            cmd.extend(["-m", self.model_path])
        
        # Add diarization if requested
        if use_diarization:
            cmd.append("-tdrz")  # Enable diarization
        
        self.logger.debug(f"Whisper command: {' '.join(cmd)}")
        
        # Run whisper
        start_time = datetime.now()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end_time = datetime.now()
        
        if result.returncode != 0:
            self.logger.error(f"Whisper failed: {result.stderr}")
            raise RuntimeError(f"Transcription failed: {result.stderr}")
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Parse results
        transcript_data = self._parse_whisper_output(output_json, processing_time)
        
        return transcript_data
    
    def _parse_whisper_output(self, json_file: Path, processing_time: float) -> Dict[str, Any]:
        """Parse whisper.cpp JSON output."""
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to parse whisper output: {e}")
            return {'text': '', 'segments': [], 'processing_time': processing_time}
        
        # Extract text and segments
        text = ""
        segments = []
        speakers = set()
        
        for segment in data.get('transcription', []):
            if isinstance(segment, dict):
                segment_text = segment.get('text', '').strip()
                if segment_text:
                    text += segment_text + " "
                    
                    # Build segment data
                    seg_data = {
                        'start': segment.get('offsets', {}).get('from', 0) / 1000.0,  # Convert to seconds
                        'end': segment.get('offsets', {}).get('to', 0) / 1000.0,
                        'text': segment_text,
                        'speaker': segment.get('speaker', 'unknown')
                    }
                    segments.append(seg_data)
                    speakers.add(seg_data['speaker'])
        
        return {
            'text': text.strip(),
            'segments': segments,
            'speakers': list(speakers),
            'language': data.get('result', {}).get('language', 'unknown'),
            'processing_time': processing_time
        }
    
    def _merge_channel_transcripts(self, left_transcript: Dict[str, Any],
                                  right_transcript: Dict[str, Any],
                                  speaker_names: List[str]) -> Dict[str, Any]:
        """Merge left and right channel transcripts into timeline."""
        # Get segments from both channels
        left_segments = left_transcript.get('segments', [])
        right_segments = right_transcript.get('segments', [])
        
        # Assign speakers
        left_speaker = speaker_names[0] if len(speaker_names) > 0 else 'Speaker 1'
        right_speaker = speaker_names[1] if len(speaker_names) > 1 else 'Speaker 2'
        
        # Tag segments with speakers
        for seg in left_segments:
            seg['speaker'] = left_speaker
            seg['channel'] = 'left'
        
        for seg in right_segments:
            seg['speaker'] = right_speaker
            seg['channel'] = 'right'
        
        # Merge and sort by timestamp
        all_segments = left_segments + right_segments
        all_segments.sort(key=lambda x: x['start'])
        
        # Build merged text
        merged_text = ""
        for seg in all_segments:
            merged_text += f"[{seg['speaker']}] {seg['text']} "
        
        return {
            'text': merged_text.strip(),
            'segments': all_segments,
            'speakers': [left_speaker, right_speaker],
            'language': left_transcript.get('language', 'unknown'),
            'processing_time': (left_transcript.get('processing_time', 0) + 
                               right_transcript.get('processing_time', 0))
        }
    
    def _save_transcript_files(self, transcript_data: Dict[str, Any], output_dir: Path):
        """Save transcript in multiple formats."""
        # Plain text
        txt_file = output_dir / "transcript.txt"
        with open(txt_file, 'w') as f:
            f.write(transcript_data.get('text', ''))
        
        # SRT format
        srt_file = output_dir / "transcript.srt"
        self._save_srt(transcript_data.get('segments', []), srt_file)
        
        # VTT format
        vtt_file = output_dir / "transcript.vtt"
        self._save_vtt(transcript_data.get('segments', []), vtt_file)
    
    def _save_srt(self, segments: List[Dict[str, Any]], output_file: Path):
        """Save transcript in SRT format."""
        with open(output_file, 'w') as f:
            for i, seg in enumerate(segments, 1):
                start_time = self._format_timestamp(seg['start'], srt_format=True)
                end_time = self._format_timestamp(seg['end'], srt_format=True)
                
                f.write(f"{i}\\n")
                f.write(f"{start_time} --> {end_time}\\n")
                
                # Include speaker if available
                if 'speaker' in seg and seg['speaker'] != 'unknown':
                    f.write(f"[{seg['speaker']}] {seg['text']}\\n")
                else:
                    f.write(f"{seg['text']}\\n")
                f.write("\\n")
    
    def _save_vtt(self, segments: List[Dict[str, Any]], output_file: Path):
        """Save transcript in WebVTT format."""
        with open(output_file, 'w') as f:
            f.write("WEBVTT\\n\\n")
            
            for seg in segments:
                start_time = self._format_timestamp(seg['start'])
                end_time = self._format_timestamp(seg['end'])
                
                f.write(f"{start_time} --> {end_time}\\n")
                
                # Include speaker if available
                if 'speaker' in seg and seg['speaker'] != 'unknown':
                    f.write(f"<v {seg['speaker']}>{seg['text']}\\n")
                else:
                    f.write(f"{seg['text']}\\n")
                f.write("\\n")
    
    def _format_timestamp(self, seconds: float, srt_format: bool = False) -> str:
        """Format timestamp for subtitle files."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        if srt_format:
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')
        else:
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"