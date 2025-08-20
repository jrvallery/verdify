"""
State management for voice note ingestion pipeline.
Handles job state persistence, locking, and crash recovery.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
import logging
import fcntl

from models import ProcessingJob, ProcessingState
from config import Config

logger = logging.getLogger(__name__)


class LockError(Exception):
    """Raised when lock operations fail."""
    pass


class ProcessingLock:
    """File-based lock for preventing concurrent processing of the same file."""
    
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.lock_fd = None
    
    def __enter__(self):
        """Acquire the lock."""
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write process info to lock file
            lock_info = {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "locked_at": datetime.utcnow().isoformat(),
                "command": " ".join(sys.argv)
            }
            json.dump(lock_info, self.lock_fd)
            self.lock_fd.flush()
            
            logger.debug(f"Acquired lock: {self.lock_file}")
            return self
            
        except (IOError, OSError) as e:
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            raise LockError(f"Failed to acquire lock {self.lock_file}: {e}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the lock."""
        if self.lock_fd:
            try:
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
                self.lock_file.unlink(missing_ok=True)
                logger.debug(f"Released lock: {self.lock_file}")
            except Exception as e:
                logger.warning(f"Error releasing lock {self.lock_file}: {e}")
            finally:
                self.lock_fd = None


class StateManager:
    """Manages processing job state and persistence."""
    
    def __init__(self, config: Config):
        self.config = config
        self.vault_path = Path(config.vault.base_path)
        self.state_dir = self.vault_path / "state"
        self.staging_dir = self.vault_path / "staging"
        self.locks_dir = self.state_dir / "locks"
        
        # Create directories
        for dir_path in [self.state_dir, self.staging_dir, self.locks_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        self._active_jobs: Dict[str, ProcessingJob] = {}
        self._job_lock = threading.Lock()
    
    def create_job(self, source_path: Path) -> ProcessingJob:
        """Create a new processing job."""
        job = ProcessingJob.create(source_path)
        
        with self._job_lock:
            self._active_jobs[job.id] = job
        
        self._save_job_state(job)
        logger.info(f"Created job {job.id} for {source_path}")
        return job
    
    def update_job(self, job: ProcessingJob, new_state: ProcessingState, error_message: Optional[str] = None):
        """Update job state."""
        job.update_state(new_state, error_message)
        
        with self._job_lock:
            self._active_jobs[job.id] = job
        
        self._save_job_state(job)
        logger.info(f"Job {job.id} state: {job.state.value}")
    
    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        """Get job by ID."""
        with self._job_lock:
            if job_id in self._active_jobs:
                return self._active_jobs[job_id]
        
        # Try to load from disk
        return self._load_job_state(job_id)
    
    def get_active_jobs(self) -> List[ProcessingJob]:
        """Get all active jobs."""
        with self._job_lock:
            return list(self._active_jobs.values())
    
    def acquire_lock(self, job: ProcessingJob) -> ProcessingLock:
        """Acquire processing lock for a job."""
        lock_file = self.locks_dir / f"{job.id}.lock"
        return ProcessingLock(lock_file)
    
    def cleanup_stale_locks(self, max_age_hours: int = 24):
        """Clean up stale lock files."""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        for lock_file in self.locks_dir.glob("*.lock"):
            try:
                # Try to read lock info
                with open(lock_file, 'r') as f:
                    lock_info = json.load(f)
                
                locked_at = datetime.fromisoformat(lock_info.get("locked_at", ""))
                
                if locked_at < cutoff_time:
                    logger.warning(f"Cleaning up stale lock: {lock_file}")
                    lock_file.unlink()
                    
            except (json.JSONDecodeError, KeyError, ValueError, FileNotFoundError):
                # Invalid or missing lock file
                logger.warning(f"Removing invalid lock file: {lock_file}")
                lock_file.unlink(missing_ok=True)
    
    def get_staging_path(self, job: ProcessingJob) -> Path:
        """Get staging path for a job."""
        staging_path = self.staging_dir / job.id
        staging_path.mkdir(exist_ok=True)
        return staging_path
    
    def cleanup_staging(self, job: ProcessingJob):
        """Clean up staging directory for a job."""
        staging_path = self.staging_dir / job.id
        if staging_path.exists():
            import shutil
            shutil.rmtree(staging_path)
            logger.debug(f"Cleaned up staging for job {job.id}")
    
    def recover_interrupted_jobs(self) -> List[ProcessingJob]:
        """Recover jobs that were interrupted."""
        recovered_jobs = []
        
        # Load all job state files
        for state_file in self.state_dir.glob("job_*.json"):
            try:
                job = self._load_job_from_file(state_file)
                if job and job.state not in [ProcessingState.DONE, ProcessingState.ERROR]:
                    # Check if source file still exists
                    if job.source_path.exists():
                        logger.info(f"Recovering interrupted job {job.id}")
                        job.update_state(ProcessingState.QUEUED)  # Reset to queued
                        recovered_jobs.append(job)
                        
                        with self._job_lock:
                            self._active_jobs[job.id] = job
                    else:
                        logger.warning(f"Source file missing for job {job.id}, marking as error")
                        job.update_state(ProcessingState.ERROR, "Source file no longer exists")
                        self._save_job_state(job)
                        
            except Exception as e:
                logger.error(f"Failed to recover job from {state_file}: {e}")
        
        return recovered_jobs
    
    def _save_job_state(self, job: ProcessingJob):
        """Save job state to disk."""
        state_file = self.state_dir / f"job_{job.id}.json"
        
        try:
            with open(state_file, 'w') as f:
                json.dump(job.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save job state {job.id}: {e}")
    
    def _load_job_state(self, job_id: str) -> Optional[ProcessingJob]:
        """Load job state from disk."""
        state_file = self.state_dir / f"job_{job_id}.json"
        return self._load_job_from_file(state_file)
    
    def _load_job_from_file(self, state_file: Path) -> Optional[ProcessingJob]:
        """Load job from state file."""
        if not state_file.exists():
            return None
        
        try:
            with open(state_file, 'r') as f:
                job_data = json.load(f)
            
            # Reconstruct ProcessingJob from dict
            job = ProcessingJob(
                id=job_data["id"],
                source_path=Path(job_data["source_path"]),
                state=ProcessingState(job_data["state"]),
                created_at=datetime.fromisoformat(job_data["created_at"]),
                updated_at=datetime.fromisoformat(job_data["updated_at"]),
                original_filename=job_data["original_filename"],
                file_size=job_data["file_size"]
            )
            
            # Set optional fields
            if job.profile:
                from models import AudioProfile
                job.profile = AudioProfile(job_data["profile"])
            
            if job_data.get("error_message"):
                job.error_message = job_data["error_message"]
            
            job.retry_count = job_data.get("retry_count", 0)
            
            # Set paths
            for path_field in ["staging_path", "processed_audio_path", "transcript_path", "note_path"]:
                if job_data.get(path_field):
                    setattr(job, path_field, Path(job_data[path_field]))
            
            return job
            
        except Exception as e:
            logger.error(f"Failed to load job from {state_file}: {e}")
            return None


# Add required imports at the top
import os
import socket
import sys