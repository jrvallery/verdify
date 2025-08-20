#!/usr/bin/env python3
"""
Context management for voice note ingestion.
Handles sidecar YAML files, filename parsing, and CLI context merging.
"""

import os
import yaml
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import subprocess


class ContextManager:
    """Manages context loading from various sources."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
    
    def load_context(self, file_path: Path, cli_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load and merge context from all sources.
        
        Priority order (highest to lowest):
        1. CLI overrides
        2. Sidecar YAML file
        3. Filename flags
        4. Default values
        
        Args:
            file_path: Path to the audio file
            cli_context: Context provided via CLI
            
        Returns:
            Merged context dictionary
        """
        self.logger.debug(f"Loading context for: {file_path}")
        
        # Start with defaults
        context = self._get_default_context()
        
        # Load from filename flags
        filename_context = self._parse_filename_flags(file_path)
        context.update(filename_context)
        
        # Load from sidecar YAML
        sidecar_context = self._load_sidecar_yaml(file_path)
        context.update(sidecar_context)
        
        # Load from macOS metadata (if available)
        metadata_context = self._load_macos_metadata(file_path)
        context.update(metadata_context)
        
        # Apply CLI overrides (highest priority)
        context.update(cli_context)
        
        self.logger.debug(f"Final context: {context}")
        return context
    
    def _get_default_context(self) -> Dict[str, Any]:
        """Get default context values."""
        return {
            'audio_profile': 'auto',
            'force_split': False,
            'is_call': False,
            'use_diarization': False,
            'tags': [],
            'speaker_names': [],
            'location': '',
            'device_info': '',
            'title': '',
            'summary': '',
            'key_points': [],
            'decisions': [],
            'actions': [],
            'people': []
        }
    
    def _parse_filename_flags(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse filename for embedded flags and metadata.
        
        Supported patterns:
        - [SPLIT] - Force split-channel processing
        - [CALL] - Mark as call recording
        - [TAGS:tag1,tag2] - Add tags
        - [PROFILE:wind] - Set audio profile
        - [SPEAKERS:Alice,Bob] - Set speaker names
        """
        filename = file_path.stem
        context = {}
        
        # Pattern for bracketed flags
        flag_pattern = r'\[([A-Z]+)(?::([^\]]+))?\]'
        
        for match in re.finditer(flag_pattern, filename, re.IGNORECASE):
            flag = match.group(1).upper()
            value = match.group(2) if match.group(2) else None
            
            if flag == 'SPLIT':
                context['force_split'] = True
                self.logger.debug("Found SPLIT flag in filename")
                
            elif flag == 'CALL':
                context['is_call'] = True
                self.logger.debug("Found CALL flag in filename")
                
            elif flag == 'TAGS' and value:
                tags = [tag.strip() for tag in value.split(',')]
                context['tags'] = tags
                self.logger.debug(f"Found TAGS flag in filename: {tags}")
                
            elif flag == 'PROFILE' and value:
                profile = value.lower().strip()
                if profile in ['auto', 'call', 'wind', 'wide']:
                    context['audio_profile'] = profile
                    self.logger.debug(f"Found PROFILE flag in filename: {profile}")
                    
            elif flag == 'SPEAKERS' and value:
                speakers = [name.strip() for name in value.split(',')]
                context['speaker_names'] = speakers
                self.logger.debug(f"Found SPEAKERS flag in filename: {speakers}")
        
        # Check for common naming patterns
        filename_lower = filename.lower()
        
        # Auto-detect call recordings
        call_indicators = ['call', 'phone', 'meeting', 'interview', 'conversation']
        if any(indicator in filename_lower for indicator in call_indicators):
            if 'is_call' not in context:
                context['is_call'] = True
                self.logger.debug("Auto-detected call recording from filename")
        
        # Auto-detect location indicators
        location_indicators = {
            'office': 'office',
            'home': 'home',
            'car': 'car',
            'outdoor': 'outdoor',
            'meeting': 'meeting room',
            'conference': 'conference room'
        }
        
        for indicator, location in location_indicators.items():
            if indicator in filename_lower:
                if 'location' not in context or not context['location']:
                    context['location'] = location
                    self.logger.debug(f"Auto-detected location from filename: {location}")
                break
        
        return context
    
    def _load_sidecar_yaml(self, file_path: Path) -> Dict[str, Any]:
        """
        Load context from sidecar YAML file.
        
        Looks for files like:
        - recording.m4a + recording.yml
        - recording.m4a + recording.yaml
        - recording.m4a + recording.m4a.yml
        """
        possible_sidecar_files = [
            file_path.with_suffix('.yml'),
            file_path.with_suffix('.yaml'),
            Path(str(file_path) + '.yml'),
            Path(str(file_path) + '.yaml')
        ]
        
        for sidecar_file in possible_sidecar_files:
            if sidecar_file.exists():
                self.logger.debug(f"Found sidecar file: {sidecar_file}")
                try:
                    with open(sidecar_file, 'r') as f:
                        sidecar_data = yaml.safe_load(f)
                    
                    if isinstance(sidecar_data, dict):
                        # Normalize keys to match our context format
                        normalized_data = self._normalize_sidecar_data(sidecar_data)
                        self.logger.debug(f"Loaded sidecar context: {normalized_data}")
                        return normalized_data
                        
                except Exception as e:
                    self.logger.warning(f"Failed to load sidecar file {sidecar_file}: {e}")
        
        return {}
    
    def _normalize_sidecar_data(self, sidecar_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize sidecar YAML data to match our context format."""
        normalized = {}
        
        # Direct mappings
        direct_mappings = {
            'audio_profile': 'audio_profile',
            'profile': 'audio_profile',
            'force_split': 'force_split',
            'split': 'force_split',
            'is_call': 'is_call',
            'call': 'is_call',
            'use_diarization': 'use_diarization',
            'diarization': 'use_diarization',
            'tags': 'tags',
            'speaker_names': 'speaker_names',
            'speakers': 'speaker_names',
            'location': 'location',
            'device_info': 'device_info',
            'device': 'device_info',
            'title': 'title',
            'summary': 'summary',
            'key_points': 'key_points',
            'decisions': 'decisions',
            'actions': 'actions',
            'people': 'people'
        }
        
        for sidecar_key, context_key in direct_mappings.items():
            if sidecar_key in sidecar_data:
                value = sidecar_data[sidecar_key]
                
                # Type conversions
                if context_key in ['force_split', 'is_call', 'use_diarization']:
                    normalized[context_key] = bool(value)
                elif context_key in ['tags', 'speaker_names', 'key_points', 'decisions', 'actions', 'people']:
                    if isinstance(value, str):
                        normalized[context_key] = [item.strip() for item in value.split(',')]
                    elif isinstance(value, list):
                        normalized[context_key] = value
                else:
                    normalized[context_key] = value
        
        # Handle nested structures
        if 'metadata' in sidecar_data:
            metadata = sidecar_data['metadata']
            if isinstance(metadata, dict):
                normalized.update(self._normalize_sidecar_data(metadata))
        
        if 'recording' in sidecar_data:
            recording = sidecar_data['recording']
            if isinstance(recording, dict):
                normalized.update(self._normalize_sidecar_data(recording))
        
        return normalized
    
    def _load_macos_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Load metadata using macOS mdls command (if available)."""
        if not self._is_macos():
            return {}
        
        try:
            # Use mdls to get file metadata
            cmd = ['mdls', '-plist', '-', str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return {}
            
            # Parse plist output
            import plistlib
            metadata = plistlib.loads(result.stdout.encode())
            
            context = {}
            
            # Extract useful metadata
            if 'kMDItemCreationDate' in metadata:
                context['creation_date'] = str(metadata['kMDItemCreationDate'])
            
            if 'kMDItemAudioBitRate' in metadata:
                context['bitrate'] = metadata['kMDItemAudioBitRate']
            
            if 'kMDItemDurationSeconds' in metadata:
                context['duration_metadata'] = metadata['kMDItemDurationSeconds']
            
            if 'kMDItemWhereFroms' in metadata:
                # Source information (e.g., downloaded from where)
                sources = metadata['kMDItemWhereFroms']
                if sources and isinstance(sources, list) and len(sources) > 0:
                    context['source'] = sources[0]
            
            # Extract device info from various metadata fields
            device_parts = []
            
            if 'kMDItemAudioChannelCount' in metadata:
                channels = metadata['kMDItemAudioChannelCount']
                device_parts.append(f"{channels} channels")
            
            if 'kMDItemAudioSampleRate' in metadata:
                sample_rate = metadata['kMDItemAudioSampleRate']
                device_parts.append(f"{sample_rate}Hz")
            
            if 'kMDItemCodecs' in metadata:
                codecs = metadata['kMDItemCodecs']
                if codecs and isinstance(codecs, list):
                    device_parts.extend(codecs)
            
            if device_parts:
                context['device_info'] = ', '.join(device_parts)
            
            self.logger.debug(f"Loaded macOS metadata: {context}")
            return context
            
        except Exception as e:
            self.logger.debug(f"Failed to load macOS metadata: {e}")
            return {}
    
    def _is_macos(self) -> bool:
        """Check if running on macOS."""
        import platform
        return platform.system() == 'Darwin'
    
    def create_example_sidecar(self, file_path: Path, example_type: str = 'basic') -> Path:
        """
        Create an example sidecar YAML file.
        
        Args:
            file_path: Path to the audio file
            example_type: Type of example ('basic', 'call', 'meeting')
            
        Returns:
            Path to the created sidecar file
        """
        sidecar_path = file_path.with_suffix('.yml')
        
        examples = {
            'basic': {
                'title': 'Voice Note Title',
                'tags': ['voice-note', 'personal'],
                'location': 'home',
                'summary': 'Brief summary of the recording content',
                'key_points': [
                    'First key point',
                    'Second key point'
                ],
                'actions': [
                    'Action item 1',
                    'Action item 2'
                ]
            },
            'call': {
                'title': 'Phone Call with [Person]',
                'is_call': True,
                'audio_profile': 'call',
                'tags': ['call', 'business'],
                'speaker_names': ['Me', 'Other Person'],
                'location': 'office',
                'summary': 'Call summary',
                'people': ['Other Person'],
                'decisions': [
                    'Decision made during call'
                ],
                'actions': [
                    'Follow up on topic X',
                    'Send document Y'
                ]
            },
            'meeting': {
                'title': 'Meeting: [Topic]',
                'tags': ['meeting', 'work'],
                'speaker_names': ['Alice', 'Bob', 'Charlie'],
                'use_diarization': True,
                'location': 'conference room',
                'summary': 'Meeting summary',
                'people': ['Alice', 'Bob', 'Charlie'],
                'key_points': [
                    'Point discussed in meeting'
                ],
                'decisions': [
                    'Decision made in meeting'
                ],
                'actions': [
                    'Action assigned to person'
                ]
            }
        }
        
        example_data = examples.get(example_type, examples['basic'])
        
        with open(sidecar_path, 'w') as f:
            yaml.dump(example_data, f, default_flow_style=False, sort_keys=False)
        
        self.logger.info(f"Created example sidecar file: {sidecar_path}")
        return sidecar_path