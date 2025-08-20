"""
Context injection and parsing for voice note ingestion pipeline.
Handles sidecar YAML files and filename flag parsing.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
import logging

from models import ContextInfo, AudioProfile

logger = logging.getLogger(__name__)


class ContextParser:
    """Parses context information from various sources."""
    
    def __init__(self):
        # Regex patterns for filename parsing
        self.flag_patterns = {
            'split': re.compile(r'\[SPLIT\]', re.IGNORECASE),
            'call': re.compile(r'\[CALL\]', re.IGNORECASE),
            'tags': re.compile(r'\[TAGS?:([^\]]+)\]', re.IGNORECASE),
            'profile': re.compile(r'\[PROFILE:([^\]]+)\]', re.IGNORECASE),
            'speakers': re.compile(r'\[SPEAKERS?:([^\]]+)\]', re.IGNORECASE),
        }
    
    def parse_context(self, audio_file: Path, cli_overrides: Optional[Dict[str, Any]] = None) -> ContextInfo:
        """Parse context from all available sources."""
        context = ContextInfo()
        
        # 1. Parse sidecar YAML file
        sidecar_context = self._parse_sidecar_yaml(audio_file)
        if sidecar_context:
            context = self._merge_context(context, sidecar_context)
        
        # 2. Parse filename flags
        filename_context = self._parse_filename_flags(audio_file)
        if filename_context:
            context = self._merge_context(context, filename_context)
        
        # 3. Apply CLI overrides
        if cli_overrides:
            context = self._apply_cli_overrides(context, cli_overrides)
        
        return context
    
    def _parse_sidecar_yaml(self, audio_file: Path) -> Optional[ContextInfo]:
        """Parse sidecar YAML file (e.g., file.m4a + file.yml)."""
        yaml_file = audio_file.with_suffix('.yml')
        if not yaml_file.exists():
            yaml_file = audio_file.with_suffix('.yaml')
        
        if not yaml_file.exists():
            return None
        
        try:
            with open(yaml_file, 'r') as f:
                yaml_data = yaml.safe_load(f)
            
            if not yaml_data:
                return None
            
            context = ContextInfo()
            
            # Parse participants
            if 'participants' in yaml_data:
                participants = yaml_data['participants']
                if isinstance(participants, list):
                    context.participants = [
                        self._normalize_participant(p) for p in participants
                    ]
                elif isinstance(participants, dict):
                    context.participants = [
                        {"name": name, "role": role} 
                        for name, role in participants.items()
                    ]
            
            # Parse tags
            if 'tags' in yaml_data:
                tags = yaml_data['tags']
                if isinstance(tags, list):
                    context.tags = [str(tag).strip() for tag in tags]
                elif isinstance(tags, str):
                    context.tags = [tag.strip() for tag in tags.split(',')]
            
            # Parse profile
            if 'profile' in yaml_data:
                try:
                    context.profile = AudioProfile(yaml_data['profile'].lower())
                except ValueError:
                    logger.warning(f"Unknown profile in YAML: {yaml_data['profile']}")
            
            # Parse processing flags
            context.split_channels = yaml_data.get('split_channels', False)
            context.is_call = yaml_data.get('is_call', False)
            
            # Parse speaker labels
            if 'speaker_labels' in yaml_data:
                context.speaker_labels = yaml_data['speaker_labels']
            
            # Store custom metadata
            custom_fields = ['title', 'location', 'project', 'meeting_type', 'summary']
            for field in custom_fields:
                if field in yaml_data:
                    context.custom_metadata[field] = yaml_data[field]
            
            logger.debug(f"Parsed sidecar YAML: {yaml_file}")
            return context
            
        except Exception as e:
            logger.error(f"Failed to parse sidecar YAML {yaml_file}: {e}")
            return None
    
    def _parse_filename_flags(self, audio_file: Path) -> Optional[ContextInfo]:
        """Parse flags from filename (e.g., [SPLIT][CALL][TAGS:#verify,#strategy])."""
        filename = audio_file.name
        context = ContextInfo()
        
        # Check for split flag
        if self.flag_patterns['split'].search(filename):
            context.split_channels = True
            logger.debug(f"Found SPLIT flag in filename: {filename}")
        
        # Check for call flag
        if self.flag_patterns['call'].search(filename):
            context.is_call = True
            logger.debug(f"Found CALL flag in filename: {filename}")
        
        # Parse tags
        tags_match = self.flag_patterns['tags'].search(filename)
        if tags_match:
            tags_str = tags_match.group(1)
            # Split by comma and clean up
            tags = [tag.strip().lstrip('#') for tag in tags_str.split(',')]
            context.tags = [tag for tag in tags if tag]
            logger.debug(f"Found tags in filename: {context.tags}")
        
        # Parse profile
        profile_match = self.flag_patterns['profile'].search(filename)
        if profile_match:
            profile_str = profile_match.group(1).lower()
            try:
                context.profile = AudioProfile(profile_str)
                logger.debug(f"Found profile in filename: {profile_str}")
            except ValueError:
                logger.warning(f"Unknown profile in filename: {profile_str}")
        
        # Parse speaker labels
        speakers_match = self.flag_patterns['speakers'].search(filename)
        if speakers_match:
            speakers_str = speakers_match.group(1)
            # Parse as comma-separated name:role pairs
            speaker_pairs = [s.strip() for s in speakers_str.split(',')]
            participants = []
            
            for pair in speaker_pairs:
                if ':' in pair:
                    name, role = pair.split(':', 1)
                    participants.append({"name": name.strip(), "role": role.strip()})
                else:
                    participants.append({"name": pair.strip(), "role": "participant"})
            
            context.participants = participants
            logger.debug(f"Found speakers in filename: {participants}")
        
        # Return context only if we found any flags
        if (context.split_channels or context.is_call or context.tags or 
            context.profile or context.participants):
            return context
        
        return None
    
    def _merge_context(self, base: ContextInfo, overlay: ContextInfo) -> ContextInfo:
        """Merge two context objects, with overlay taking precedence."""
        merged = ContextInfo()
        
        # Merge participants (combine, don't override)
        merged.participants = base.participants + overlay.participants
        
        # Merge tags (combine, deduplicate)
        all_tags = base.tags + overlay.tags
        merged.tags = list(dict.fromkeys(all_tags))  # Preserve order, remove duplicates
        
        # Use overlay values for simple fields, fall back to base
        merged.profile = overlay.profile or base.profile
        merged.split_channels = overlay.split_channels or base.split_channels
        merged.is_call = overlay.is_call or base.is_call
        
        # Merge speaker labels
        merged.speaker_labels = {**(base.speaker_labels or {}), **(overlay.speaker_labels or {})}
        
        # Merge custom metadata
        merged.custom_metadata = {**base.custom_metadata, **overlay.custom_metadata}
        
        return merged
    
    def _apply_cli_overrides(self, context: ContextInfo, overrides: Dict[str, Any]) -> ContextInfo:
        """Apply CLI overrides to context."""
        if 'profile' in overrides:
            try:
                context.profile = AudioProfile(overrides['profile'].lower())
            except ValueError:
                logger.warning(f"Unknown profile override: {overrides['profile']}")
        
        if 'split_channels' in overrides:
            context.split_channels = bool(overrides['split_channels'])
        
        if 'is_call' in overrides:
            context.is_call = bool(overrides['is_call'])
        
        if 'tags' in overrides:
            if isinstance(overrides['tags'], list):
                context.tags.extend(overrides['tags'])
            elif isinstance(overrides['tags'], str):
                context.tags.extend(tag.strip() for tag in overrides['tags'].split(','))
        
        if 'participants' in overrides:
            if isinstance(overrides['participants'], list):
                context.participants.extend([
                    self._normalize_participant(p) for p in overrides['participants']
                ])
        
        if 'speaker_labels' in overrides:
            context.speaker_labels = context.speaker_labels or {}
            context.speaker_labels.update(overrides['speaker_labels'])
        
        return context
    
    def _normalize_participant(self, participant: Any) -> Dict[str, str]:
        """Normalize participant to standard format."""
        if isinstance(participant, str):
            return {"name": participant, "role": "participant"}
        elif isinstance(participant, dict):
            return {
                "name": participant.get("name", "Unknown"),
                "role": participant.get("role", "participant")
            }
        else:
            return {"name": str(participant), "role": "participant"}
    
    def create_sidecar_template(self, audio_file: Path) -> Path:
        """Create a template sidecar YAML file."""
        yaml_file = audio_file.with_suffix('.yml')
        
        template = {
            'participants': [
                {'name': 'Speaker 1', 'role': 'host'},
                {'name': 'Speaker 2', 'role': 'guest'}
            ],
            'tags': ['meeting', 'project'],
            'profile': 'auto',
            'split_channels': False,
            'is_call': False,
            'speaker_labels': {
                'left': 'Speaker 1',
                'right': 'Speaker 2'
            },
            'title': audio_file.stem,
            'location': '',
            'project': '',
            'meeting_type': '',
            'summary': ''
        }
        
        with open(yaml_file, 'w') as f:
            yaml.dump(template, f, default_flow_style=False, indent=2)
        
        logger.info(f"Created sidecar template: {yaml_file}")
        return yaml_file