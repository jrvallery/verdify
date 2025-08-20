"""
Configuration management for voice note ingestion pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
from pydantic import BaseModel, Field


class ProcessingProfile(BaseModel):
    """Audio processing profile configuration."""
    description: str
    filters: List[str]


class TranscriptionConfig(BaseModel):
    """Transcription settings."""
    model: str = "base.en"
    language: str = "en"
    fp16: bool = True
    threads: int = 4


class ProcessingConfig(BaseModel):
    """Audio processing configuration."""
    profiles: Dict[str, ProcessingProfile]
    default_profile: str = "auto"
    sample_rate: int = 16000
    channels: int = 1
    format: str = "wav"
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)


class VaultConfig(BaseModel):
    """Vault organization configuration."""
    base_path: str = "VoiceNotes"
    templates_path: str = "templates"


class WatcherConfig(BaseModel):
    """File watcher configuration."""
    watch_path: str = "~/Downloads"
    debounce_seconds: int = 2


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_max_bytes: int = 10485760  # 10MB
    file_backup_count: int = 5


class Config(BaseModel):
    """Main configuration class."""
    processing: ProcessingConfig
    vault: VaultConfig = Field(default_factory=VaultConfig)
    supported_formats: List[str] = Field(default_factory=lambda: [
        ".m4a", ".mp3", ".wav", ".aac", ".flac", ".caf", ".mp4", ".mov", ".opus"
    ])
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        # Default to VoiceNotes/config.yml
        config_path = Path("VoiceNotes/config.yml")
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config_data = yaml.safe_load(f)
    
    return Config(**config_data)


def get_vault_path(config: Config) -> Path:
    """Get the vault base path."""
    return Path(config.vault.base_path).expanduser().resolve()


def get_templates_path(config: Config) -> Path:
    """Get the templates path."""
    vault_path = get_vault_path(config)
    return vault_path / config.vault.templates_path


def get_watch_path(config: Config) -> Path:
    """Get the watch path."""
    return Path(config.watcher.watch_path).expanduser().resolve()