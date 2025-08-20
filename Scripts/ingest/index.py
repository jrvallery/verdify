#!/usr/bin/env python3
"""
Master index management for voice note ingestion.
Maintains the authoritative ledger of all processed recordings.
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import csv
from collections import defaultdict


class MasterIndex:
    """Manages the master index of processed voice notes."""
    
    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)
        self.index_file = self.vault_path / "_index.md"
        self.logger = logging.getLogger(__name__)
        
        # Ensure vault directory exists
        self.vault_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize index if it doesn't exist
        if not self.index_file.exists():
            self._initialize_index()
    
    def _initialize_index(self):
        """Initialize a new master index file."""
        initial_content = """# Voice Notes Master Index

This file serves as the authoritative ledger of all processed voice recordings.

## Index Data

```yaml
version: 1
created: {created_at}
updated: {updated_at}
total_recordings: 0
total_duration: 0.0
entries: []
```

## Recordings

| Date | Title | Duration | Hash | Note |
|------|-------|----------|------|------|

## Statistics

- **Total Recordings**: 0
- **Total Duration**: 0m 0s
- **Storage Used**: 0 MB
- **Last Updated**: {updated_at}

""".format(
    created_at=datetime.now(timezone.utc).isoformat(),
    updated_at=datetime.now(timezone.utc).isoformat()
)
        
        with open(self.index_file, 'w') as f:
            f.write(initial_content)
        
        self.logger.info(f"Initialized master index: {self.index_file}")
    
    def add_entry(self, state_data: Dict[str, Any]):
        """Add a new entry to the master index."""
        self.logger.info(f"Adding entry to master index: {state_data['sha256_file']}")
        
        # Load current index
        index_data = self._load_index_data()
        
        # Create new entry
        entry = self._create_index_entry(state_data)
        
        # Check if entry already exists
        existing_index = self._find_entry_index(index_data, entry['sha256_file'])
        if existing_index is not None:
            # Update existing entry
            index_data['entries'][existing_index] = entry
            self.logger.info(f"Updated existing entry: {entry['sha256_file']}")
        else:
            # Add new entry
            index_data['entries'].append(entry)
            index_data['total_recordings'] += 1
            self.logger.info(f"Added new entry: {entry['sha256_file']}")
        
        # Update totals
        self._update_index_totals(index_data)
        
        # Save updated index
        self._save_index_data(index_data)
    
    def _create_index_entry(self, state_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an index entry from processing state data."""
        audio_result = state_data.get('audio_result', {})
        transcription_result = state_data.get('transcription_result', {})
        note_result = state_data.get('note_result', {})
        context = state_data.get('context', {})
        
        original_file_path = Path(state_data['file_path'])
        
        entry = {
            'sha256_file': state_data['sha256_file'],
            'sha256_pcm': state_data['sha256_pcm'],
            'created_at': state_data.get('started_at', datetime.now(timezone.utc).isoformat()),
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'title': note_result.get('note_metadata', {}).get('title', original_file_path.stem),
            'original_filename': original_file_path.name,
            'note_filename': note_result.get('note_filename', ''),
            'note_path': note_result.get('note_path', ''),
            'duration': audio_result.get('duration', 0.0),
            'file_size': self._get_file_size(original_file_path),
            'audio_profile': audio_result.get('profile', 'auto'),
            'processing_mode': audio_result.get('processing_mode', 'single_channel'),
            'language': transcription_result.get('meta_data', {}).get('language', 'unknown'),
            'speaker_count': transcription_result.get('meta_data', {}).get('speaker_count', 1),
            'word_count': transcription_result.get('meta_data', {}).get('word_count', 0),
            'tags': note_result.get('note_metadata', {}).get('tags', []),
            'device_info': context.get('device_info', ''),
            'location': context.get('location', ''),
            'processing_time': transcription_result.get('meta_data', {}).get('processing_time', 0),
            'artifacts': {
                'audio_dir': f"audio/{state_data['sha256_file']}",
                'transcript_dir': f"transcripts/{state_data['sha256_file']}",
                'note_file': note_result.get('note_filename', '')
            }
        }
        
        return entry
    
    def _get_file_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        try:
            if file_path.exists():
                return file_path.stat().st_size
        except:
            pass
        return 0
    
    def _load_index_data(self) -> Dict[str, Any]:
        """Load index data from the master index file."""
        try:
            with open(self.index_file, 'r') as f:
                content = f.read()
            
            # Extract YAML data block
            if '```yaml' in content and '```' in content:
                start = content.find('```yaml') + 7
                end = content.find('```', start)
                yaml_content = content[start:end].strip()
                
                try:
                    return yaml.safe_load(yaml_content)
                except yaml.YAMLError as e:
                    self.logger.error(f"Failed to parse YAML: {e}")
            
            # Fallback to empty structure
            return {
                'version': 1,
                'created': datetime.now(timezone.utc).isoformat(),
                'updated': datetime.now(timezone.utc).isoformat(),
                'total_recordings': 0,
                'total_duration': 0.0,
                'entries': []
            }
            
        except FileNotFoundError:
            self._initialize_index()
            return self._load_index_data()
    
    def _save_index_data(self, index_data: Dict[str, Any]):
        """Save index data back to the master index file."""
        # Update timestamp
        index_data['updated'] = datetime.now(timezone.utc).isoformat()
        
        # Generate content
        content = self._generate_index_content(index_data)
        
        # Save to file
        with open(self.index_file, 'w') as f:
            f.write(content)
        
        self.logger.debug(f"Saved index with {len(index_data['entries'])} entries")
    
    def _generate_index_content(self, index_data: Dict[str, Any]) -> str:
        """Generate the complete index file content."""
        # YAML header
        yaml_content = yaml.dump(index_data, default_flow_style=False, sort_keys=False)
        
        # Table header
        table_header = """
## Recordings

| Date | Title | Duration | Hash | Note |
|------|-------|----------|------|------|"""
        
        # Table rows
        table_rows = []
        for entry in sorted(index_data['entries'], key=lambda x: x['created_at'], reverse=True):
            date = self._format_date(entry['created_at'])
            title = entry['title'][:50] + '...' if len(entry['title']) > 50 else entry['title']
            duration = self._format_duration(entry['duration'])
            hash_short = entry['sha256_file'][:8]
            note_link = f"[[{entry['note_filename'].replace('.md', '')}]]" if entry['note_filename'] else ''
            
            table_rows.append(f"| {date} | {title} | {duration} | `{hash_short}` | {note_link} |")
        
        # Statistics
        stats = self._generate_stats_section(index_data)
        
        # Combine all parts
        content = f"""# Voice Notes Master Index

This file serves as the authoritative ledger of all processed voice recordings.

## Index Data

```yaml
{yaml_content}```
{table_header}
{chr(10).join(table_rows)}

{stats}
"""
        
        return content
    
    def _generate_stats_section(self, index_data: Dict[str, Any]) -> str:
        """Generate statistics section."""
        total_recordings = index_data['total_recordings']
        total_duration = index_data['total_duration']
        total_storage = sum(entry.get('file_size', 0) for entry in index_data['entries'])
        
        # Language breakdown
        languages = defaultdict(int)
        for entry in index_data['entries']:
            lang = entry.get('language', 'unknown')
            languages[lang] += 1
        
        # Tag breakdown
        tags = defaultdict(int)
        for entry in index_data['entries']:
            for tag in entry.get('tags', []):
                tags[tag] += 1
        
        stats = f"""## Statistics

- **Total Recordings**: {total_recordings}
- **Total Duration**: {self._format_duration(total_duration)}
- **Storage Used**: {self._format_bytes(total_storage)}
- **Last Updated**: {index_data['updated'][:19]}Z

### Languages
{chr(10).join(f'- **{lang.title()}**: {count}' for lang, count in sorted(languages.items()))}

### Top Tags
{chr(10).join(f'- **{tag}**: {count}' for tag, count in sorted(tags.items(), key=lambda x: x[1], reverse=True)[:10])}
"""
        
        return stats
    
    def _update_index_totals(self, index_data: Dict[str, Any]):
        """Update totals in index data."""
        index_data['total_recordings'] = len(index_data['entries'])
        index_data['total_duration'] = sum(entry.get('duration', 0) for entry in index_data['entries'])
    
    def _find_entry_index(self, index_data: Dict[str, Any], sha256_file: str) -> Optional[int]:
        """Find the index of an entry by file hash."""
        for i, entry in enumerate(index_data['entries']):
            if entry['sha256_file'] == sha256_file:
                return i
        return None
    
    def is_processed(self, sha256_file: str) -> bool:
        """Check if a file hash is already processed."""
        index_data = self._load_index_data()
        return self._find_entry_index(index_data, sha256_file) is not None
    
    def get_entry(self, sha256_file: str) -> Optional[Dict[str, Any]]:
        """Get entry by file hash."""
        index_data = self._load_index_data()
        entry_index = self._find_entry_index(index_data, sha256_file)
        if entry_index is not None:
            return index_data['entries'][entry_index]
        return None
    
    def find_by_content_hash(self, sha256_pcm: str) -> Optional[Dict[str, Any]]:
        """Find entry by content hash."""
        index_data = self._load_index_data()
        for entry in index_data['entries']:
            if entry.get('sha256_pcm') == sha256_pcm:
                return entry
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        index_data = self._load_index_data()
        
        total_storage = sum(entry.get('file_size', 0) for entry in index_data['entries'])
        
        # Find last processed
        last_processed = 'never'
        if index_data['entries']:
            latest_entry = max(index_data['entries'], key=lambda x: x.get('processed_at', ''))
            last_processed = latest_entry.get('processed_at', 'unknown')
        
        return {
            'total_recordings': index_data['total_recordings'],
            'total_duration': self._format_duration(index_data['total_duration']),
            'storage_used': self._format_bytes(total_storage),
            'last_processed': last_processed[:19] if last_processed != 'never' else 'never'
        }
    
    def rebuild_from_notes(self) -> int:
        """Rebuild index from existing notes in the vault."""
        self.logger.info("Rebuilding index from existing notes")
        
        notes_dir = self.vault_path / "notes"
        if not notes_dir.exists():
            return 0
        
        # Initialize new index
        index_data = {
            'version': 1,
            'created': datetime.now(timezone.utc).isoformat(),
            'updated': datetime.now(timezone.utc).isoformat(),
            'total_recordings': 0,
            'total_duration': 0.0,
            'entries': []
        }
        
        # Process each note file
        count = 0
        for note_file in notes_dir.glob("*.md"):
            try:
                entry = self._extract_entry_from_note(note_file)
                if entry:
                    index_data['entries'].append(entry)
                    count += 1
            except Exception as e:
                self.logger.warning(f"Failed to process note {note_file}: {e}")
        
        # Update totals
        self._update_index_totals(index_data)
        
        # Save rebuilt index
        self._save_index_data(index_data)
        
        self.logger.info(f"Rebuilt index with {count} entries")
        return count
    
    def _extract_entry_from_note(self, note_file: Path) -> Optional[Dict[str, Any]]:
        """Extract index entry data from a note file."""
        try:
            with open(note_file, 'r') as f:
                content = f.read()
            
            # Extract YAML frontmatter
            if not content.startswith('---'):
                return None
            
            end_pos = content.find('---', 3)
            if end_pos == -1:
                return None
            
            yaml_content = content[3:end_pos].strip()
            metadata = yaml.safe_load(yaml_content)
            
            if not metadata:
                return None
            
            # Build entry from metadata
            entry = {
                'sha256_file': metadata.get('file_hash', ''),
                'sha256_pcm': metadata.get('content_hash', ''),
                'created_at': metadata.get('created', ''),
                'processed_at': metadata.get('updated', ''),
                'title': metadata.get('title', note_file.stem),
                'original_filename': metadata.get('original_file', ''),
                'note_filename': note_file.name,
                'note_path': str(note_file),
                'duration': self._parse_duration(metadata.get('duration', '0s')),
                'file_size': 0,  # Not available from note
                'audio_profile': metadata.get('processing_profile', 'auto'),
                'processing_mode': 'unknown',
                'language': metadata.get('language', 'unknown'),
                'speaker_count': metadata.get('speaker_count', 1),
                'word_count': metadata.get('word_count', 0),
                'tags': metadata.get('tags', []),
                'device_info': metadata.get('device_info', ''),
                'location': metadata.get('location', ''),
                'processing_time': self._parse_duration(metadata.get('processing_time', '0s')),
                'artifacts': {
                    'audio_dir': f"audio/{metadata.get('file_hash', '')}",
                    'transcript_dir': f"transcripts/{metadata.get('file_hash', '')}",
                    'note_file': note_file.name
                }
            }
            
            return entry
            
        except Exception as e:
            self.logger.warning(f"Failed to parse note {note_file}: {e}")
            return None
    
    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string to seconds."""
        if not duration_str:
            return 0.0
        
        # Parse formats like "1m 30s", "45s", "1h 5m"
        import re
        
        total_seconds = 0.0
        
        # Hours
        hours_match = re.search(r'(\\d+)h', duration_str)
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600
        
        # Minutes
        minutes_match = re.search(r'(\\d+)m', duration_str)
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60
        
        # Seconds
        seconds_match = re.search(r'([\\d.]+)s', duration_str)
        if seconds_match:
            total_seconds += float(seconds_match.group(1))
        
        return total_seconds
    
    def _format_date(self, iso_date: str) -> str:
        """Format ISO date for display."""
        try:
            dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except:
            return iso_date[:10]
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    def _format_bytes(self, bytes_count: int) -> str:
        """Format bytes in human-readable format."""
        if bytes_count < 1024:
            return f"{bytes_count} B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.1f} GB"