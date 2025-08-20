"""
Index management for voice note ingestion pipeline.
Maintains master index with dual-hash deduplication.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import logging

from models import IndexEntry, HashInfo
from config import Config

logger = logging.getLogger(__name__)


class IndexManager:
    """Manages the master index for processed voice notes."""
    
    def __init__(self, config: Config):
        self.config = config
        self.vault_path = Path(config.vault.base_path)
        self.index_md_path = self.vault_path / "_index.md"
        self.index_json_path = self.vault_path / "_index.json"
        
        # In-memory index for fast lookups
        self._index_cache: Dict[str, IndexEntry] = {}
        self._pcm_hash_map: Dict[str, str] = {}  # pcm_hash -> entry_id
        self._file_hash_map: Dict[str, str] = {}  # file_hash -> entry_id
        
        self._load_index()
    
    def check_duplicate(self, hashes: HashInfo) -> Optional[IndexEntry]:
        """Check if content already exists (primary key: sha256_pcm)."""
        entry_id = self._pcm_hash_map.get(hashes.sha256_pcm)
        if entry_id:
            return self._index_cache.get(entry_id)
        return None
    
    def add_entry(self, entry: IndexEntry) -> bool:
        """Add new entry to index. Returns False if duplicate exists."""
        # Check for duplicate
        if entry.sha256_pcm in self._pcm_hash_map:
            logger.warning(f"Duplicate content detected: {entry.sha256_pcm[:8]}")
            return False
        
        # Add to cache
        self._index_cache[entry.id] = entry
        self._pcm_hash_map[entry.sha256_pcm] = entry.id
        self._file_hash_map[entry.sha256_file] = entry.id
        
        # Update persistent index
        self._save_index()
        
        logger.info(f"Added index entry: {entry.id} ({entry.title})")
        return True
    
    def update_entry(self, entry: IndexEntry):
        """Update existing entry."""
        if entry.id in self._index_cache:
            old_entry = self._index_cache[entry.id]
            
            # Update hash maps if hashes changed
            if old_entry.sha256_pcm != entry.sha256_pcm:
                del self._pcm_hash_map[old_entry.sha256_pcm]
                self._pcm_hash_map[entry.sha256_pcm] = entry.id
            
            if old_entry.sha256_file != entry.sha256_file:
                del self._file_hash_map[old_entry.sha256_file]
                self._file_hash_map[entry.sha256_file] = entry.id
        
        self._index_cache[entry.id] = entry
        self._save_index()
        
        logger.info(f"Updated index entry: {entry.id}")
    
    def remove_entry(self, entry_id: str) -> bool:
        """Remove entry from index."""
        if entry_id not in self._index_cache:
            return False
        
        entry = self._index_cache[entry_id]
        
        # Remove from maps
        self._pcm_hash_map.pop(entry.sha256_pcm, None)
        self._file_hash_map.pop(entry.sha256_file, None)
        del self._index_cache[entry_id]
        
        # Update persistent index
        self._save_index()
        
        logger.info(f"Removed index entry: {entry_id}")
        return True
    
    def get_entry(self, entry_id: str) -> Optional[IndexEntry]:
        """Get entry by ID."""
        return self._index_cache.get(entry_id)
    
    def get_entry_by_pcm_hash(self, pcm_hash: str) -> Optional[IndexEntry]:
        """Get entry by PCM hash."""
        entry_id = self._pcm_hash_map.get(pcm_hash)
        if entry_id:
            return self._index_cache.get(entry_id)
        return None
    
    def get_entry_by_file_hash(self, file_hash: str) -> Optional[IndexEntry]:
        """Get entry by file hash."""
        entry_id = self._file_hash_map.get(file_hash)
        if entry_id:
            return self._index_cache.get(entry_id)
        return None
    
    def list_entries(self, 
                    tags: Optional[List[str]] = None,
                    participants: Optional[List[str]] = None,
                    date_from: Optional[datetime] = None,
                    date_to: Optional[datetime] = None) -> List[IndexEntry]:
        """List entries with optional filtering."""
        entries = list(self._index_cache.values())
        
        # Filter by tags
        if tags:
            entries = [e for e in entries if any(tag in e.tags for tag in tags)]
        
        # Filter by participants
        if participants:
            entries = [e for e in entries if any(p in e.participants for p in participants)]
        
        # Filter by date range
        if date_from:
            entries = [e for e in entries if e.processed_at >= date_from]
        
        if date_to:
            entries = [e for e in entries if e.processed_at <= date_to]
        
        # Sort by processed date (newest first)
        entries.sort(key=lambda x: x.processed_at, reverse=True)
        
        return entries
    
    def get_stats(self) -> Dict[str, any]:
        """Get index statistics."""
        entries = list(self._index_cache.values())
        
        if not entries:
            return {
                "total_entries": 0,
                "total_duration": 0,
                "total_size": 0,
                "unique_participants": 0,
                "unique_tags": 0,
                "date_range": None
            }
        
        total_duration = sum(e.duration for e in entries)
        total_size = sum(e.file_size for e in entries)
        
        all_participants = set()
        all_tags = set()
        for entry in entries:
            all_participants.update(entry.participants)
            all_tags.update(entry.tags)
        
        dates = [e.processed_at for e in entries]
        date_range = {
            "earliest": min(dates).isoformat(),
            "latest": max(dates).isoformat()
        }
        
        return {
            "total_entries": len(entries),
            "total_duration": total_duration,
            "total_size": total_size,
            "unique_participants": len(all_participants),
            "unique_tags": len(all_tags),
            "date_range": date_range
        }
    
    def rebuild_from_notes(self) -> int:
        """Rebuild index by scanning note files. Returns number of entries rebuilt."""
        logger.info("Rebuilding index from note files...")
        
        # Clear current index
        self._index_cache.clear()
        self._pcm_hash_map.clear()
        self._file_hash_map.clear()
        
        notes_dir = self.vault_path / "notes"
        if not notes_dir.exists():
            logger.warning("Notes directory does not exist")
            return 0
        
        rebuilt_count = 0
        
        for note_file in notes_dir.glob("**/*.md"):
            try:
                entry = self._extract_entry_from_note(note_file)
                if entry:
                    self._index_cache[entry.id] = entry
                    self._pcm_hash_map[entry.sha256_pcm] = entry.id
                    self._file_hash_map[entry.sha256_file] = entry.id
                    rebuilt_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to process note {note_file}: {e}")
        
        # Save rebuilt index
        self._save_index()
        
        logger.info(f"Rebuilt index with {rebuilt_count} entries")
        return rebuilt_count
    
    def _load_index(self):
        """Load index from JSON file."""
        if not self.index_json_path.exists():
            logger.info("No existing index found, starting fresh")
            return
        
        try:
            with open(self.index_json_path, 'r') as f:
                index_data = json.load(f)
            
            for entry_data in index_data.get("entries", []):
                entry = IndexEntry.from_dict(entry_data)
                self._index_cache[entry.id] = entry
                self._pcm_hash_map[entry.sha256_pcm] = entry.id
                self._file_hash_map[entry.sha256_file] = entry.id
            
            logger.info(f"Loaded {len(self._index_cache)} entries from index")
            
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            # Continue with empty index
    
    def _save_index(self):
        """Save index to both JSON and Markdown files."""
        try:
            # Save JSON index (machine-readable)
            index_data = {
                "updated_at": datetime.utcnow().isoformat(),
                "version": "1.0",
                "total_entries": len(self._index_cache),
                "entries": [entry.to_dict() for entry in self._index_cache.values()]
            }
            
            with open(self.index_json_path, 'w') as f:
                json.dump(index_data, f, indent=2)
            
            # Save Markdown index (human-readable)
            self._save_markdown_index()
            
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def _save_markdown_index(self):
        """Save human-readable Markdown index."""
        entries = sorted(self._index_cache.values(), key=lambda x: x.processed_at, reverse=True)
        
        lines = [
            "# Voice Notes Index",
            "",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total Entries: {len(entries)}",
            "",
            "| Date | Title | Duration | Participants | Tags | Note |",
            "|------|-------|----------|--------------|------|------|"
        ]
        
        for entry in entries:
            date_str = entry.processed_at.strftime('%Y-%m-%d')
            duration_str = f"{int(entry.duration // 60):02d}:{int(entry.duration % 60):02d}"
            participants_str = ", ".join(entry.participants[:3])  # Limit for readability
            if len(entry.participants) > 3:
                participants_str += "..."
            tags_str = ", ".join(entry.tags[:3])
            if len(entry.tags) > 3:
                tags_str += "..."
            
            note_link = f"[{entry.title}]({entry.note_path})"
            
            lines.append(
                f"| {date_str} | {entry.title[:30]} | {duration_str} | {participants_str} | {tags_str} | {note_link} |"
            )
        
        with open(self.index_md_path, 'w') as f:
            f.write("\n".join(lines))
    
    def _extract_entry_from_note(self, note_file: Path) -> Optional[IndexEntry]:
        """Extract index entry from note file frontmatter."""
        try:
            with open(note_file, 'r') as f:
                content = f.read()
            
            # Parse YAML frontmatter
            if not content.startswith('---'):
                return None
            
            parts = content.split('---', 2)
            if len(parts) < 3:
                return None
            
            import yaml
            frontmatter = yaml.safe_load(parts[1])
            
            # Extract required fields
            entry = IndexEntry(
                id=frontmatter.get('id', str(uuid.uuid4())),
                sha256_file=frontmatter['sha256_file'],
                sha256_pcm=frontmatter['sha256_pcm'],
                original_filename=frontmatter.get('original_filename', note_file.stem),
                processed_at=datetime.fromisoformat(frontmatter['processed']),
                duration=float(frontmatter['duration']),
                file_size=int(frontmatter['file_size']),
                sample_rate=int(frontmatter['sample_rate']),
                channels=int(frontmatter['channels']),
                format=frontmatter['format'],
                profile=frontmatter['profile'],
                tags=frontmatter.get('tags', []),
                participants=frontmatter.get('participants', []),
                note_path=str(note_file.relative_to(self.vault_path)),
                audio_path=frontmatter['audio_file'],
                transcript_path=frontmatter['transcript_file'],
                title=frontmatter['title']
            )
            
            return entry
            
        except Exception as e:
            logger.error(f"Failed to parse note {note_file}: {e}")
            return None


# Add required import
import uuid