"""
Main processing pipeline for voice note ingestion.
Orchestrates the complete workflow from file to indexed note.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from models import ProcessingJob, ProcessingState, AudioProfile, IndexEntry
from config import Config
from state import StateManager, LockError
from audio import AudioProcessor
from transcription import Transcriber
from context import ContextParser
from notes import NoteGenerator
from index import IndexManager

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Raised when processing fails."""
    pass


class VoiceNoteProcessor:
    """Main processor for voice note ingestion pipeline."""
    
    def __init__(self, config: Config):
        self.config = config
        self.vault_path = Path(config.vault.base_path)
        
        # Initialize components
        self.state_manager = StateManager(config)
        self.audio_processor = AudioProcessor(config)
        self.transcriber = Transcriber(config)
        self.context_parser = ContextParser()
        self.note_generator = NoteGenerator(config)
        self.index_manager = IndexManager(config)
        
        # Create vault directories
        self._ensure_vault_structure()
    
    def process_file(
        self, 
        source_path: Path,
        cli_overrides: Optional[Dict[str, Any]] = None,
        force_reprocess: bool = False
    ) -> Optional[ProcessingJob]:
        """Process a single voice note file through the complete pipeline."""
        
        if not source_path.exists():
            raise ProcessingError(f"Source file does not exist: {source_path}")
        
        if not self._is_supported_format(source_path):
            raise ProcessingError(f"Unsupported file format: {source_path.suffix}")
        
        # Create processing job
        job = self.state_manager.create_job(source_path)
        
        try:
            # Acquire lock to prevent concurrent processing
            with self.state_manager.acquire_lock(job):
                return self._process_job(job, cli_overrides, force_reprocess)
                
        except LockError:
            logger.warning(f"File is already being processed: {source_path}")
            return None
        except Exception as e:
            logger.error(f"Processing failed for {source_path}: {e}")
            self.state_manager.update_job(job, ProcessingState.ERROR, str(e))
            return job
    
    def _process_job(
        self, 
        job: ProcessingJob,
        cli_overrides: Optional[Dict[str, Any]] = None,
        force_reprocess: bool = False
    ) -> ProcessingJob:
        """Process a job through all pipeline stages."""
        
        try:
            # Stage 1: Staging
            self.state_manager.update_job(job, ProcessingState.STAGING)
            self._stage_file(job)
            
            # Stage 2: Context parsing
            self._parse_context(job, cli_overrides)
            
            # Stage 3: Hashing
            self.state_manager.update_job(job, ProcessingState.HASHING)
            self._compute_hashes(job)
            
            # Stage 4: Deduplication check
            self.state_manager.update_job(job, ProcessingState.DEDUPE_CHECK)
            if not force_reprocess and self._check_duplicate(job):
                logger.info(f"Duplicate content detected, skipping processing: {job.id}")
                self.state_manager.update_job(job, ProcessingState.DONE)
                return job
            
            # Stage 5: Audio processing/transcoding
            self.state_manager.update_job(job, ProcessingState.TRANSCODE)
            self._process_audio(job)
            
            # Stage 6: Transcription
            self.state_manager.update_job(job, ProcessingState.TRANSCRIBE)
            transcript = self._transcribe_audio(job)
            
            # Stage 7: Note generation
            self.state_manager.update_job(job, ProcessingState.ASSEMBLE_NOTE)
            note_path = self._generate_note(job, transcript)
            job.note_path = note_path
            
            # Stage 8: Index update
            self.state_manager.update_job(job, ProcessingState.INDEX_UPDATE)
            self._update_index(job, transcript)
            
            # Stage 9: Finalization
            self.state_manager.update_job(job, ProcessingState.FINALIZE)
            self._finalize_processing(job)
            
            # Stage 10: Done
            self.state_manager.update_job(job, ProcessingState.DONE)
            
            logger.info(f"Successfully processed voice note: {job.original_filename}")
            return job
            
        except Exception as e:
            logger.error(f"Processing failed at stage {job.state.value}: {e}")
            self.state_manager.update_job(job, ProcessingState.ERROR, str(e))
            
            # Cleanup on error
            self._cleanup_failed_job(job)
            raise
    
    def _stage_file(self, job: ProcessingJob):
        """Stage the source file for processing."""
        staging_path = self.state_manager.get_staging_path(job)
        
        # Copy file to staging
        staged_file = staging_path / job.original_filename
        shutil.copy2(job.source_path, staged_file)
        job.staging_path = staged_file
        
        logger.debug(f"Staged file: {staged_file}")
    
    def _parse_context(self, job: ProcessingJob, cli_overrides: Optional[Dict[str, Any]]):
        """Parse context from all available sources."""
        job.context = self.context_parser.parse_context(job.source_path, cli_overrides)
        logger.debug(f"Parsed context: {len(job.context.tags)} tags, {len(job.context.participants)} participants")
    
    def _compute_hashes(self, job: ProcessingJob):
        """Compute file and content hashes."""
        # Extract audio metadata first
        job.audio_metadata = self.audio_processor.probe_audio(job.staging_path)
        
        # Determine processing profile
        if not job.profile:
            if job.context.profile:
                job.profile = job.context.profile
            else:
                job.profile = self.audio_processor.detect_profile(job.audio_metadata)
        
        # Compute hashes
        job.hashes = self.audio_processor.compute_hashes(job.staging_path, job.profile)
        
        logger.debug(f"Computed hashes: {job.hashes}")
    
    def _check_duplicate(self, job: ProcessingJob) -> bool:
        """Check if content is a duplicate."""
        existing_entry = self.index_manager.check_duplicate(job.hashes)
        if existing_entry:
            logger.info(f"Found duplicate: {existing_entry.title} (PCM: {job.hashes.sha256_pcm[:8]})")
            return True
        return False
    
    def _process_audio(self, job: ProcessingJob):
        """Process audio file (transcoding, filtering)."""
        audio_dir = self.vault_path / "audio" / job.hashes.sha256_pcm[:8]
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        if job.context.split_channels and job.audio_metadata.channels >= 2:
            # Split-channel processing
            channel_files = self.audio_processor.process_split_channels(
                job.staging_path, audio_dir, job.profile
            )
            job.processed_audio_path = channel_files[0]  # Use first channel as primary
            # Store all channel files in context
            job.context.custom_metadata['channel_files'] = [str(f) for f in channel_files]
        else:
            # Standard processing
            processed_file = audio_dir / f"{job.hashes.sha256_pcm[:8]}.wav"
            job.processed_audio_path = self.audio_processor.convert_to_pcm(
                job.staging_path, processed_file, job.profile
            )
        
        logger.debug(f"Processed audio: {job.processed_audio_path}")
    
    def _transcribe_audio(self, job: ProcessingJob):
        """Transcribe the processed audio."""
        if job.context.split_channels and 'channel_files' in job.context.custom_metadata:
            # Transcribe split channels
            channel_files = [Path(f) for f in job.context.custom_metadata['channel_files']]
            channel_results = self.transcriber.transcribe_split_channels(channel_files, job.context)
            
            # Merge channel transcripts
            transcript = self.transcriber.merge_channel_transcripts(
                channel_results, job.context.speaker_labels
            )
        else:
            # Standard transcription
            use_diarization = len(job.context.participants) > 1 and not job.context.split_channels
            transcript = self.transcriber.transcribe(
                job.processed_audio_path, job.context, diarization=use_diarization
            )
        
        # Save transcript
        transcript_dir = self.vault_path / "transcripts" / job.hashes.sha256_pcm[:8]
        transcript_dir.mkdir(parents=True, exist_ok=True)
        
        transcript_file = transcript_dir / "transcript.json"
        with open(transcript_file, 'w') as f:
            import json
            json.dump(transcript.to_dict(), f, indent=2)
        
        job.transcript_path = transcript_file
        
        logger.debug(f"Generated transcript: {transcript_file}")
        return transcript
    
    def _generate_note(self, job: ProcessingJob, transcript):
        """Generate the structured note."""
        note_path = self.note_generator.generate_note(
            job, transcript, job.audio_metadata, job.hashes
        )
        return note_path
    
    def _update_index(self, job: ProcessingJob, transcript):
        """Update the master index."""
        # Extract title from note
        title = self._extract_title_from_note(job.note_path)
        
        # Create index entry
        entry = IndexEntry(
            id=job.id,
            sha256_file=job.hashes.sha256_file,
            sha256_pcm=job.hashes.sha256_pcm,
            original_filename=job.original_filename,
            processed_at=datetime.utcnow(),
            duration=job.audio_metadata.duration,
            file_size=job.audio_metadata.file_size,
            sample_rate=job.audio_metadata.sample_rate,
            channels=job.audio_metadata.channels,
            format=job.audio_metadata.format,
            profile=job.profile.value,
            tags=job.context.tags,
            participants=[p['name'] for p in job.context.participants],
            note_path=str(job.note_path.relative_to(self.vault_path)),
            audio_path=str(job.processed_audio_path.relative_to(self.vault_path)),
            transcript_path=str(job.transcript_path.relative_to(self.vault_path)),
            title=title
        )
        
        self.index_manager.add_entry(entry)
        logger.debug(f"Updated index: {entry.title}")
    
    def _finalize_processing(self, job: ProcessingJob):
        """Finalize processing - cleanup and move original file."""
        # Create done marker
        done_marker = job.staging_path.with_suffix('.done')
        done_marker.touch()
        
        # Optional: move original file to processed location
        # For now, we leave it in Downloads as specified
        
        # Cleanup staging
        self.state_manager.cleanup_staging(job)
        
        logger.debug(f"Finalized processing: {job.id}")
    
    def _cleanup_failed_job(self, job: ProcessingJob):
        """Clean up artifacts from failed processing."""
        try:
            # Remove any created files
            for path_attr in ['processed_audio_path', 'transcript_path', 'note_path']:
                path = getattr(job, path_attr)
                if path and path.exists():
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
            
            # Cleanup staging
            self.state_manager.cleanup_staging(job)
            
        except Exception as e:
            logger.warning(f"Error during cleanup of failed job {job.id}: {e}")
    
    def _extract_title_from_note(self, note_path: Path) -> str:
        """Extract title from generated note."""
        try:
            with open(note_path, 'r') as f:
                content = f.read()
            
            # Parse YAML frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 2:
                    import yaml
                    frontmatter = yaml.safe_load(parts[1])
                    return frontmatter.get('title', 'Untitled')
            
            # Fallback: extract from first heading
            lines = content.split('\n')
            for line in lines:
                if line.startswith('# '):
                    return line[2:].strip()
            
            return 'Untitled'
            
        except Exception:
            return 'Untitled'
    
    def _is_supported_format(self, file_path: Path) -> bool:
        """Check if file format is supported."""
        return file_path.suffix.lower() in self.config.supported_formats
    
    def _ensure_vault_structure(self):
        """Ensure all required vault directories exist."""
        required_dirs = [
            "audio", "transcripts", "notes", "logs", "state", "staging", "templates"
        ]
        
        for dir_name in required_dirs:
            dir_path = self.vault_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def validate_tools(self) -> bool:
        """Validate that all required tools are available."""
        return (
            self.audio_processor.validate_tools() and 
            self.transcriber.validate_whisper()
        )
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing pipeline statistics."""
        active_jobs = self.state_manager.get_active_jobs()
        index_stats = self.index_manager.get_stats()
        
        state_counts = {}
        for job in active_jobs:
            state = job.state.value
            state_counts[state] = state_counts.get(state, 0) + 1
        
        return {
            "active_jobs": len(active_jobs),
            "state_distribution": state_counts,
            "index_stats": index_stats,
            "vault_path": str(self.vault_path)
        }