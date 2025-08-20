"""
Core models for voice note ingestion pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib
import json
import uuid


class ProcessingState(Enum):
    """Processing state machine states."""
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


class AudioProfile(Enum):
    """Audio processing profiles."""
    AUTO = "auto"
    CALL = "call"
    WIND = "wind"
    WIDE = "wide"


@dataclass
class AudioMetadata:
    """Audio file metadata."""
    duration: float
    sample_rate: int
    channels: int
    bitrate: Optional[int]
    format: str
    codec: Optional[str]
    file_size: int


@dataclass
class HashInfo:
    """Hash information for deduplication."""
    sha256_file: str  # Hash of raw file
    sha256_pcm: str   # Hash of decoded 16kHz mono PCM
    
    def __str__(self) -> str:
        return f"file:{self.sha256_file[:8]}, pcm:{self.sha256_pcm[:8]}"


@dataclass
class ContextInfo:
    """Context information from sidecar YAML or filename parsing."""
    participants: List[Dict[str, str]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    profile: Optional[AudioProfile] = None
    split_channels: bool = False
    is_call: bool = False
    speaker_labels: Optional[Dict[str, str]] = None
    custom_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingJob:
    """Represents a voice note processing job."""
    id: str
    source_path: Path
    state: ProcessingState
    created_at: datetime
    updated_at: datetime
    
    # File information
    original_filename: str
    file_size: int
    
    # Processing information
    profile: Optional[AudioProfile] = None
    context: ContextInfo = field(default_factory=ContextInfo)
    
    # Computed hashes
    hashes: Optional[HashInfo] = None
    
    # Audio metadata
    audio_metadata: Optional[AudioMetadata] = None
    
    # Processing artifacts
    staging_path: Optional[Path] = None
    processed_audio_path: Optional[Path] = None
    transcript_path: Optional[Path] = None
    note_path: Optional[Path] = None
    
    # Error information
    error_message: Optional[str] = None
    retry_count: int = 0
    
    @classmethod
    def create(cls, source_path: Path) -> "ProcessingJob":
        """Create a new processing job."""
        now = datetime.utcnow()
        return cls(
            id=str(uuid.uuid4()),
            source_path=source_path,
            state=ProcessingState.QUEUED,
            created_at=now,
            updated_at=now,
            original_filename=source_path.name,
            file_size=source_path.stat().st_size
        )
    
    def update_state(self, new_state: ProcessingState, error_message: Optional[str] = None):
        """Update the processing state."""
        self.state = new_state
        self.updated_at = datetime.utcnow()
        if error_message:
            self.error_message = error_message
            self.state = ProcessingState.ERROR
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "source_path": str(self.source_path),
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "profile": self.profile.value if self.profile else None,
            "context": {
                "participants": self.context.participants,
                "tags": self.context.tags,
                "profile": self.context.profile.value if self.context.profile else None,
                "split_channels": self.context.split_channels,
                "is_call": self.context.is_call,
                "speaker_labels": self.context.speaker_labels,
                "custom_metadata": self.context.custom_metadata
            },
            "hashes": {
                "sha256_file": self.hashes.sha256_file,
                "sha256_pcm": self.hashes.sha256_pcm
            } if self.hashes else None,
            "audio_metadata": {
                "duration": self.audio_metadata.duration,
                "sample_rate": self.audio_metadata.sample_rate,
                "channels": self.audio_metadata.channels,
                "bitrate": self.audio_metadata.bitrate,
                "format": self.audio_metadata.format,
                "codec": self.audio_metadata.codec,
                "file_size": self.audio_metadata.file_size
            } if self.audio_metadata else None,
            "staging_path": str(self.staging_path) if self.staging_path else None,
            "processed_audio_path": str(self.processed_audio_path) if self.processed_audio_path else None,
            "transcript_path": str(self.transcript_path) if self.transcript_path else None,
            "note_path": str(self.note_path) if self.note_path else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count
        }


@dataclass
class IndexEntry:
    """Master index entry for processed voice notes."""
    id: str
    sha256_file: str
    sha256_pcm: str  # Primary deduplication key
    original_filename: str
    processed_at: datetime
    duration: float
    file_size: int
    sample_rate: int
    channels: int
    format: str
    profile: str
    tags: List[str]
    participants: List[str]
    note_path: str
    audio_path: str
    transcript_path: str
    title: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "sha256_file": self.sha256_file,
            "sha256_pcm": self.sha256_pcm,
            "original_filename": self.original_filename,
            "processed_at": self.processed_at.isoformat(),
            "duration": self.duration,
            "file_size": self.file_size,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": self.format,
            "profile": self.profile,
            "tags": self.tags,
            "participants": self.participants,
            "note_path": self.note_path,
            "audio_path": self.audio_path,
            "transcript_path": self.transcript_path,
            "title": self.title
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            sha256_file=data["sha256_file"],
            sha256_pcm=data["sha256_pcm"],
            original_filename=data["original_filename"],
            processed_at=datetime.fromisoformat(data["processed_at"]),
            duration=data["duration"],
            file_size=data["file_size"],
            sample_rate=data["sample_rate"],
            channels=data["channels"],
            format=data["format"],
            profile=data["profile"],
            tags=data["tags"],
            participants=data["participants"],
            note_path=data["note_path"],
            audio_path=data["audio_path"],
            transcript_path=data["transcript_path"],
            title=data["title"]
        )


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()