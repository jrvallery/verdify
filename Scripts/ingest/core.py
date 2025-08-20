#!/usr/bin/env python3
"""
Core processing pipeline for voice note ingestion.
Implements the state machine: queued → staging → hashing → dedupe-check → 
transcode → transcribe → assemble-note → index-update → finalize → done
"""

import os
import hashlib
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum

from .audio import AudioProcessor
from .transcription import TranscriptionEngine
from .notes import NoteGenerator
from .index import MasterIndex
from .context import ContextManager


class ProcessingState(Enum):
    """Processing states for the voice note pipeline."""
    QUEUED = "queued"
    STAGING = "staging"
    HASHING = "hashing"
    DEDUPE_CHECK = "dedupe-check"
    TRANSCODE = "transcode"
    TRANSCRIBE = "transcribe"
    ASSEMBLE_NOTE = "assemble-note"
    INDEX_UPDATE = "index-update"
    FINALIZE = "finalize"
    DONE = "done"
    ERROR = "error"


class VoiceNoteProcessor:
    """Main processor for voice note ingestion pipeline."""
    
    def __init__(self, vault_path: Path, verbose: bool = False):
        self.vault_path = Path(vault_path)
        self.verbose = verbose
        
        # Set up logging
        logging.basicConfig(
            level=logging.DEBUG if verbose else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.audio_processor = AudioProcessor(verbose=verbose)
        self.transcription_engine = TranscriptionEngine(verbose=verbose)
        self.note_generator = NoteGenerator(vault_path, verbose=verbose)
        self.master_index = MasterIndex(vault_path)
        self.context_manager = ContextManager(verbose=verbose)
        
        # Ensure vault structure exists
        self._ensure_vault_structure()
    
    def _ensure_vault_structure(self):
        """Ensure the VoiceNotes vault directory structure exists."""
        directories = [
            self.vault_path,
            self.vault_path / "audio",
            self.vault_path / "transcripts", 
            self.vault_path / "notes",
            self.vault_path / "logs",
            self.vault_path / "state",
            self.vault_path / "staging",
            self.vault_path / "templates"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            
        self.logger.info(f"Vault structure ensured at: {self.vault_path}")
    
    def process_file(self, file_path: Path, context: Optional[Dict[str, Any]] = None, 
                    force: bool = False) -> Optional[Dict[str, Any]]:
        """
        Process a single audio file through the complete pipeline.
        
        Args:
            file_path: Path to the audio file to process
            context: Additional context (tags, speaker names, etc.)
            force: Force reprocessing even if already processed
            
        Returns:
            Dictionary with processing results or None if failed
        """
        file_path = Path(file_path).resolve()
        
        if not file_path.exists():
            self.logger.error(f"File does not exist: {file_path}")
            return None
            
        if not self._is_supported_audio_file(file_path):
            self.logger.error(f"Unsupported file type: {file_path}")
            return None
        
        # Generate initial file hash for tracking
        sha256_file = self._calculate_file_hash(file_path)
        
        # Check if already processed (unless force)
        if not force and self.master_index.is_processed(sha256_file):
            self.logger.info(f"File already processed: {file_path} (SHA: {sha256_file})")
            return self.master_index.get_entry(sha256_file)
        
        # Start processing pipeline
        self.logger.info(f"Starting processing pipeline for: {file_path}")
        
        try:
            # Load context (sidecar YAML, filename flags, CLI overrides)
            full_context = self.context_manager.load_context(file_path, context or {})
            
            # Initialize processing state
            state_data = {
                'file_path': str(file_path),
                'sha256_file': sha256_file,
                'started_at': datetime.now(timezone.utc).isoformat(),
                'context': full_context,
                'state': ProcessingState.QUEUED.value
            }
            
            # Process through state machine
            result = self._run_pipeline(state_data)
            
            if result and result.get('state') == ProcessingState.DONE.value:
                self.logger.info(f"Successfully processed: {file_path}")
                return result
            else:
                self.logger.error(f"Processing failed for: {file_path}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error processing {file_path}: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None
    
    def _run_pipeline(self, state_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run the complete processing pipeline through all states."""
        current_state = ProcessingState.QUEUED
        
        state_handlers = {
            ProcessingState.QUEUED: self._state_queued,
            ProcessingState.STAGING: self._state_staging,
            ProcessingState.HASHING: self._state_hashing,
            ProcessingState.DEDUPE_CHECK: self._state_dedupe_check,
            ProcessingState.TRANSCODE: self._state_transcode,
            ProcessingState.TRANSCRIBE: self._state_transcribe,
            ProcessingState.ASSEMBLE_NOTE: self._state_assemble_note,
            ProcessingState.INDEX_UPDATE: self._state_index_update,
            ProcessingState.FINALIZE: self._state_finalize,
        }
        
        while current_state != ProcessingState.DONE and current_state != ProcessingState.ERROR:
            self.logger.debug(f"Processing state: {current_state.value}")
            
            # Create lock file for crash safety
            lock_file = self._create_lock_file(state_data['sha256_file'], current_state)
            
            try:
                # Call state handler
                handler = state_handlers.get(current_state)
                if not handler:
                    self.logger.error(f"No handler for state: {current_state}")
                    current_state = ProcessingState.ERROR
                    break
                    
                next_state, updated_data = handler(state_data)
                
                if updated_data:
                    state_data.update(updated_data)
                
                state_data['state'] = next_state.value
                current_state = next_state
                
                # Remove lock file after successful state transition
                self._remove_lock_file(lock_file)
                
            except Exception as e:
                self.logger.error(f"Error in state {current_state.value}: {e}")
                current_state = ProcessingState.ERROR
                # Keep lock file for debugging
                break
        
        # Final state
        state_data['state'] = current_state.value
        state_data['completed_at'] = datetime.now(timezone.utc).isoformat()
        
        return state_data if current_state == ProcessingState.DONE else None
    
    def _state_queued(self, state_data: Dict[str, Any]) -> tuple:
        """Initial state - validate file and prepare for staging."""
        file_path = Path(state_data['file_path'])
        
        if not file_path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")
            
        return ProcessingState.STAGING, {}
    
    def _state_staging(self, state_data: Dict[str, Any]) -> tuple:
        """Copy file to staging area for safe processing."""
        file_path = Path(state_data['file_path'])
        sha256_file = state_data['sha256_file']
        
        # Create staging directory
        staging_dir = self.vault_path / "staging" / sha256_file
        staging_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy original file to staging
        staging_file = staging_dir / f"original{file_path.suffix}"
        shutil.copy2(file_path, staging_file)
        
        return ProcessingState.HASHING, {
            'staging_dir': str(staging_dir),
            'staging_file': str(staging_file)
        }
    
    def _state_hashing(self, state_data: Dict[str, Any]) -> tuple:
        """Calculate both file hash and content hash."""
        staging_file = Path(state_data['staging_file'])
        
        # File hash already calculated, now get content hash
        sha256_pcm = self.audio_processor.calculate_content_hash(staging_file)
        
        return ProcessingState.DEDUPE_CHECK, {
            'sha256_pcm': sha256_pcm
        }
    
    def _state_dedupe_check(self, state_data: Dict[str, Any]) -> tuple:
        """Check for duplicates using content hash."""
        sha256_pcm = state_data['sha256_pcm']
        
        # Check if content already exists
        existing = self.master_index.find_by_content_hash(sha256_pcm)
        if existing:
            self.logger.info(f"Duplicate content found: {existing['sha256_file']}")
            # Could link to existing or skip - for now continue processing
        
        return ProcessingState.TRANSCODE, {}
    
    def _state_transcode(self, state_data: Dict[str, Any]) -> tuple:
        """Transcode audio to normalized format."""
        staging_file = Path(state_data['staging_file'])
        staging_dir = Path(state_data['staging_dir'])
        context = state_data['context']
        
        # Process audio
        audio_result = self.audio_processor.process_audio(
            staging_file, staging_dir, context
        )
        
        return ProcessingState.TRANSCRIBE, {
            'audio_result': audio_result
        }
    
    def _state_transcribe(self, state_data: Dict[str, Any]) -> tuple:
        """Transcribe audio to text."""
        audio_result = state_data['audio_result']
        staging_dir = Path(state_data['staging_dir'])
        context = state_data['context']
        
        # Transcribe audio
        transcription_result = self.transcription_engine.transcribe(
            audio_result, staging_dir, context
        )
        
        return ProcessingState.ASSEMBLE_NOTE, {
            'transcription_result': transcription_result
        }
    
    def _state_assemble_note(self, state_data: Dict[str, Any]) -> tuple:
        """Generate the final note from transcription and metadata."""
        # Generate note
        note_result = self.note_generator.generate_note(state_data)
        
        return ProcessingState.INDEX_UPDATE, {
            'note_result': note_result
        }
    
    def _state_index_update(self, state_data: Dict[str, Any]) -> tuple:
        """Update the master index with the new entry."""
        # Add to master index
        self.master_index.add_entry(state_data)
        
        return ProcessingState.FINALIZE, {}
    
    def _state_finalize(self, state_data: Dict[str, Any]) -> tuple:
        """Move artifacts to final locations and cleanup."""
        sha256_file = state_data['sha256_file']
        staging_dir = Path(state_data['staging_dir'])
        
        # Move audio artifacts
        audio_dir = self.vault_path / "audio" / sha256_file
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        # Move transcription artifacts
        transcript_dir = self.vault_path / "transcripts" / sha256_file
        transcript_dir.mkdir(parents=True, exist_ok=True)
        
        # Move files from staging to final locations
        for item in staging_dir.iterdir():
            if item.is_file():
                if item.name.startswith('original.') or item.name == 'normalized.wav':
                    shutil.move(str(item), audio_dir / item.name)
                elif item.suffix in ['.txt', '.srt', '.vtt', '.json']:
                    shutil.move(str(item), transcript_dir / item.name)
        
        # Remove staging directory
        shutil.rmtree(staging_dir, ignore_errors=True)
        
        return ProcessingState.DONE, {}
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def _is_supported_audio_file(self, file_path: Path) -> bool:
        """Check if file is a supported audio/video format."""
        supported_extensions = {
            '.m4a', '.mp3', '.wav', '.aac', '.flac', '.caf', 
            '.mp4', '.mov', '.opus', '.ogg', '.webm'
        }
        return file_path.suffix.lower() in supported_extensions
    
    def _create_lock_file(self, sha256: str, state: ProcessingState) -> Path:
        """Create a lock file for crash safety."""
        lock_file = self.vault_path / "state" / f"{sha256}.{state.value}.lock"
        lock_file.touch()
        return lock_file
    
    def _remove_lock_file(self, lock_file: Path):
        """Remove a lock file."""
        try:
            lock_file.unlink()
        except FileNotFoundError:
            pass
    
    def reprocess_by_sha(self, sha256_file: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Reprocess an existing file by its SHA256 hash."""
        # Find existing entry
        entry = self.master_index.get_entry(sha256_file)
        if not entry:
            self.logger.error(f"No entry found for SHA: {sha256_file}")
            return None
            
        # Get original file path from audio directory
        audio_dir = self.vault_path / "audio" / sha256_file
        original_files = list(audio_dir.glob("original.*"))
        if not original_files:
            self.logger.error(f"Original file not found for SHA: {sha256_file}")
            return None
            
        # Reprocess with new context
        return self.process_file(original_files[0], context=context, force=True)
    
    def verify_artifacts(self, sha256_file: str) -> bool:
        """Verify all artifacts exist for a processed recording."""
        audio_dir = self.vault_path / "audio" / sha256_file
        transcript_dir = self.vault_path / "transcripts" / sha256_file
        
        # Check required artifacts
        required_files = [
            audio_dir / "normalized.wav",
            transcript_dir / "transcript.txt",
            transcript_dir / "meta.json"
        ]
        
        for file_path in required_files:
            if not file_path.exists():
                self.logger.error(f"Missing artifact: {file_path}")
                return False
                
        return True