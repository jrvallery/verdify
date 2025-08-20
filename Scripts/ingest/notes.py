#!/usr/bin/env python3
"""
Note generation module for voice note ingestion.
Creates structured Obsidian notes with comprehensive metadata and templating.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import yaml
import hashlib


class NoteGenerator:
    """Generates structured notes for processed voice recordings."""
    
    def __init__(self, vault_path: Path, verbose: bool = False):
        self.vault_path = Path(vault_path)
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        
        # Load note template
        self.template = self._load_template()
    
    def _load_template(self) -> str:
        """Load note template from templates directory."""
        template_file = self.vault_path / "templates" / "note.md"
        
        if template_file.exists():
            with open(template_file, 'r') as f:
                return f.read()
        else:
            # Use default template
            return self._get_default_template()
    
    def _get_default_template(self) -> str:
        """Get default note template."""
        return '''---
# Voice Note Metadata
id: "{note_id}"
title: "{title}"
created: "{created_at}"
updated: "{updated_at}"
tags: {tags}

# Audio Information  
duration: "{duration}"
file_hash: "{sha256_file}"
content_hash: "{sha256_pcm}"
original_file: "{original_filename}"
processing_profile: "{audio_profile}"

# Transcription
model: "{transcription_model}"
language: "{language}"
confidence: {confidence}
speaker_count: {speaker_count}
word_count: {word_count}

# Processing
processing_time: "{processing_time}"
device_info: "{device_info}"
location: "{location}"

# Links
audio_file: "[[{audio_link}]]"
transcript_file: "[[{transcript_link}]]"
---

# {title}

## Summary

*Brief summary of the recording content*

{summary_section}

## Key Points

{key_points_section}

## Transcript

{transcript_content}

## Decisions Made

{decisions_section}

## Action Items

{actions_section}

## People Mentioned

{people_section}

## Technical Details

- **Duration**: {duration}
- **Processing Profile**: {audio_profile}
- **Model**: {transcription_model}
- **Language**: {language}
- **Speakers**: {speaker_count}
- **Words**: {word_count}

## Files

- **Audio**: {audio_link}
- **Transcript**: {transcript_link}
- **SRT**: {srt_link}
- **VTT**: {vtt_link}
'''
    
    def generate_note(self, state_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a complete note from processing state data.
        
        Args:
            state_data: Complete processing state information
            
        Returns:
            Dictionary with note generation results
        """
        self.logger.info("Generating note")
        
        # Extract key information
        sha256_file = state_data['sha256_file']
        sha256_pcm = state_data['sha256_pcm']
        context = state_data['context']
        audio_result = state_data['audio_result']
        transcription_result = state_data['transcription_result']
        
        # Generate note metadata
        note_metadata = self._build_note_metadata(state_data)
        
        # Generate note filename and path
        note_filename = self._generate_note_filename(note_metadata)
        note_path = self.vault_path / "notes" / note_filename
        
        # Generate note content
        note_content = self._build_note_content(note_metadata, state_data)
        
        # Save note
        note_path.parent.mkdir(parents=True, exist_ok=True)
        with open(note_path, 'w') as f:
            f.write(note_content)
        
        self.logger.info(f"Generated note: {note_path}")
        
        return {
            'note_path': str(note_path),
            'note_filename': note_filename,
            'note_metadata': note_metadata
        }
    
    def _build_note_metadata(self, state_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build comprehensive note metadata."""
        sha256_file = state_data['sha256_file']
        sha256_pcm = state_data['sha256_pcm']
        context = state_data.get('context', {})
        audio_result = state_data.get('audio_result', {})
        transcription_result = state_data.get('transcription_result', {})
        
        # Extract original file info
        original_file_path = Path(state_data['file_path'])
        
        # Generate title
        title = self._generate_title(original_file_path, context, transcription_result)
        
        # Generate unique note ID
        note_id = self._generate_note_id(sha256_file, title)
        
        # Build metadata
        metadata = {
            'note_id': note_id,
            'title': title,
            'created_at': state_data.get('started_at', datetime.now(timezone.utc).isoformat()),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'sha256_file': sha256_file,
            'sha256_pcm': sha256_pcm,
            'original_filename': original_file_path.name,
            'duration': self._format_duration(audio_result.get('duration', 0)),
            'audio_profile': audio_result.get('profile', 'auto'),
            'transcription_model': transcription_result.get('meta_data', {}).get('model', 'unknown'),
            'language': transcription_result.get('meta_data', {}).get('language', 'unknown'),
            'confidence': transcription_result.get('meta_data', {}).get('confidence', 0.0),
            'speaker_count': transcription_result.get('meta_data', {}).get('speaker_count', 1),
            'word_count': transcription_result.get('meta_data', {}).get('word_count', 0),
            'processing_time': self._format_duration(
                transcription_result.get('meta_data', {}).get('processing_time', 0)
            ),
            'tags': self._build_tags(context, transcription_result),
            'device_info': self._extract_device_info(original_file_path),
            'location': context.get('location', ''),
            'audio_link': f"audio/{sha256_file}/normalized.wav",
            'transcript_link': f"transcripts/{sha256_file}/transcript.txt",
            'srt_link': f"transcripts/{sha256_file}/transcript.srt",
            'vtt_link': f"transcripts/{sha256_file}/transcript.vtt"
        }
        
        return metadata
    
    def _generate_title(self, original_file: Path, context: Dict[str, Any], 
                       transcription_result: Dict[str, Any]) -> str:
        """Generate a descriptive title for the note."""
        # Check for explicit title in context
        if 'title' in context:
            return context['title']
        
        # Extract from filename
        base_name = original_file.stem
        
        # Remove common patterns
        cleaned_name = base_name.replace('_', ' ').replace('-', ' ')
        
        # Check for timestamp patterns and remove them
        import re
        timestamp_patterns = [
            r'\\d{4}-\\d{2}-\\d{2}[_\\s]\\d{2}[_:]\\d{2}[_:]\\d{2}',
            r'\\d{8}[_\\s]\\d{6}',
            r'Recording[_\\s]\\d+',
            r'Voice[_\\s]\\d+'
        ]
        
        for pattern in timestamp_patterns:
            cleaned_name = re.sub(pattern, '', cleaned_name, flags=re.IGNORECASE)
        
        cleaned_name = ' '.join(cleaned_name.split())  # Normalize whitespace
        
        # If still generic, try to extract from transcript
        if not cleaned_name or len(cleaned_name) < 5:
            transcript_text = transcription_result.get('transcript_text', '')
            if transcript_text:
                # Take first meaningful phrase (up to 50 chars)
                words = transcript_text.split()[:10]
                title_candidate = ' '.join(words)
                if len(title_candidate) > 50:
                    title_candidate = title_candidate[:47] + '...'
                if title_candidate:
                    cleaned_name = title_candidate
        
        # Fallback to timestamp
        if not cleaned_name:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            cleaned_name = f"Voice Note {timestamp}"
        
        return cleaned_name.strip()
    
    def _generate_note_id(self, sha256_file: str, title: str) -> str:
        """Generate a unique note ID."""
        # Use first 8 characters of file hash + title hash
        title_hash = hashlib.sha256(title.encode()).hexdigest()[:8]
        return f"{sha256_file[:8]}_{title_hash}"
    
    def _generate_note_filename(self, metadata: Dict[str, Any]) -> str:
        """Generate note filename based on metadata."""
        created_dt = datetime.fromisoformat(metadata['created_at'].replace('Z', '+00:00'))
        date_str = created_dt.strftime('%Y-%m-%d_%H%M')
        
        # Create slug from title
        title = metadata['title']
        slug = self._slugify(title)
        
        # Truncate slug if too long
        if len(slug) > 50:
            slug = slug[:47] + '...'
        
        # Add short hash
        sha8 = metadata['sha256_file'][:8]
        
        return f"{date_str}__{slug}__{sha8}.md"
    
    def _slugify(self, text: str) -> str:
        """Convert text to URL-safe slug."""
        import re
        
        # Convert to lowercase and replace spaces with hyphens
        slug = text.lower().replace(' ', '-')
        
        # Remove non-alphanumeric characters except hyphens
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        
        # Remove multiple consecutive hyphens
        slug = re.sub(r'-+', '-', slug)
        
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        
        return slug
    
    def _build_note_content(self, metadata: Dict[str, Any], 
                           state_data: Dict[str, Any]) -> str:
        """Build the complete note content."""
        transcription_result = state_data.get('transcription_result', {})
        context = state_data.get('context', {})
        
        # Get transcript text
        transcript_text = transcription_result.get('transcript_text', '')
        
        # Generate content sections
        sections = {
            'summary_section': self._generate_summary_section(transcript_text, context),
            'key_points_section': self._generate_key_points_section(transcript_text, context),
            'transcript_content': self._format_transcript_content(transcript_text, transcription_result),
            'decisions_section': self._generate_decisions_section(transcript_text, context),
            'actions_section': self._generate_actions_section(transcript_text, context),
            'people_section': self._generate_people_section(transcript_text, context)
        }
        
        # Merge metadata and sections
        template_vars = {**metadata, **sections}
        
        # Format template
        try:
            return self.template.format(**template_vars)
        except KeyError as e:
            self.logger.warning(f"Template variable missing: {e}")
            # Fallback to safe substitution
            return self._safe_format_template(self.template, template_vars)
    
    def _safe_format_template(self, template: str, variables: Dict[str, Any]) -> str:
        """Safely format template, leaving unknown variables as-is."""
        import string
        
        class SafeFormatter(string.Formatter):
            def get_value(self, key, args, kwargs):
                if isinstance(key, str):
                    try:
                        return kwargs[key]
                    except KeyError:
                        return '{' + key + '}'
                else:
                    return string.Formatter.get_value(key, args, kwargs)
        
        formatter = SafeFormatter()
        return formatter.format(template, **variables)
    
    def _generate_summary_section(self, transcript_text: str, context: Dict[str, Any]) -> str:
        """Generate summary section."""
        if 'summary' in context:
            return context['summary']
        
        # Auto-generate basic summary
        if not transcript_text:
            return "*No transcript available*"
        
        # Take first few sentences
        sentences = transcript_text.split('.')[:3]
        summary = '. '.join(sentences).strip()
        if summary and not summary.endswith('.'):
            summary += '.'
        
        return summary or "*Summary to be added*"
    
    def _generate_key_points_section(self, transcript_text: str, context: Dict[str, Any]) -> str:
        """Generate key points section."""
        if 'key_points' in context:
            points = context['key_points']
            if isinstance(points, list):
                return '\\n'.join(f"- {point}" for point in points)
            return str(points)
        
        return "- *Key points to be identified*"
    
    def _format_transcript_content(self, transcript_text: str, 
                                  transcription_result: Dict[str, Any]) -> str:
        """Format transcript content for the note."""
        if not transcript_text:
            return "*No transcript available*"
        
        # Check if we have speaker information
        meta_data = transcription_result.get('meta_data', {})
        if meta_data.get('speaker_count', 1) > 1:
            # Multi-speaker transcript - preserve speaker labels
            return transcript_text
        else:
            # Single speaker - clean formatting
            return transcript_text.strip()
    
    def _generate_decisions_section(self, transcript_text: str, context: Dict[str, Any]) -> str:
        """Generate decisions section."""
        if 'decisions' in context:
            decisions = context['decisions']
            if isinstance(decisions, list):
                return '\\n'.join(f"- {decision}" for decision in decisions)
            return str(decisions)
        
        return "- *Decisions to be documented*"
    
    def _generate_actions_section(self, transcript_text: str, context: Dict[str, Any]) -> str:
        """Generate action items section."""
        if 'actions' in context:
            actions = context['actions']
            if isinstance(actions, list):
                return '\\n'.join(f"- [ ] {action}" for action in actions)
            return str(actions)
        
        return "- [ ] *Action items to be identified*"
    
    def _generate_people_section(self, transcript_text: str, context: Dict[str, Any]) -> str:
        """Generate people mentioned section."""
        people = set()
        
        # From context
        if 'people' in context:
            if isinstance(context['people'], list):
                people.update(context['people'])
            else:
                people.add(str(context['people']))
        
        # From speaker names
        speaker_names = context.get('speaker_names', [])
        if speaker_names:
            people.update(speaker_names)
        
        if people:
            return '\\n'.join(f"- [[{person}]]" for person in sorted(people))
        
        return "- *People to be identified*"
    
    def _build_tags(self, context: Dict[str, Any], transcription_result: Dict[str, Any]) -> List[str]:
        """Build tags for the note."""
        tags = ['voice-note']
        
        # Add context tags
        if 'tags' in context:
            if isinstance(context['tags'], list):
                tags.extend(context['tags'])
            else:
                tags.append(str(context['tags']))
        
        # Add automatic tags
        if context.get('is_call', False):
            tags.append('call')
        
        # Add language tag
        language = transcription_result.get('meta_data', {}).get('language', '')
        if language and language != 'unknown':
            tags.append(f'lang-{language}')
        
        # Remove duplicates and return
        return list(set(tags))
    
    def _extract_device_info(self, file_path: Path) -> str:
        """Extract device information from file metadata."""
        # This would integrate with macOS mdls command for metadata
        # For now, return basic info
        return f"File: {file_path.name}"
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"