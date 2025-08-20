"""
Note generation for voice note ingestion pipeline.
Creates structured Obsidian notes with comprehensive metadata.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from models import ProcessingJob, IndexEntry, AudioMetadata, HashInfo
from transcription import TranscriptionResult
from config import Config

logger = logging.getLogger(__name__)


class NoteGenerator:
    """Generates structured notes from processed voice recordings."""
    
    def __init__(self, config: Config):
        self.config = config
        self.vault_path = Path(config.vault.base_path)
        self.templates_path = self.vault_path / config.vault.templates_path
        self.notes_dir = self.vault_path / "notes"
        
        # Create notes directory
        self.notes_dir.mkdir(exist_ok=True)
    
    def generate_note(
        self,
        job: ProcessingJob,
        transcript: TranscriptionResult,
        audio_metadata: AudioMetadata,
        hashes: HashInfo
    ) -> Path:
        """Generate a complete note from processing job and results."""
        
        # Generate title
        title = self._generate_title(job, transcript)
        
        # Create note filename (safe for filesystem)
        safe_title = self._make_safe_filename(title)
        note_filename = f"{job.created_at.strftime('%Y%m%d_%H%M%S')}_{safe_title}.md"
        note_path = self.notes_dir / note_filename
        
        # Generate content sections
        frontmatter = self._generate_frontmatter(job, transcript, audio_metadata, hashes, title)
        summary = self._generate_summary(transcript)
        key_points = self._extract_key_points(transcript)
        decisions = self._extract_decisions(transcript)
        action_items = self._extract_action_items(transcript)
        
        # Build the complete note
        note_content = self._build_note_content(
            frontmatter=frontmatter,
            title=title,
            summary=summary,
            key_points=key_points,
            decisions=decisions,
            action_items=action_items,
            participants=job.context.participants,
            audio_metadata=audio_metadata,
            job=job,
            transcript=transcript
        )
        
        # Write the note
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(note_content)
        
        logger.info(f"Generated note: {note_path}")
        return note_path
    
    def _generate_title(self, job: ProcessingJob, transcript: TranscriptionResult) -> str:
        """Generate a meaningful title for the note."""
        
        # Check if title is provided in context
        if 'title' in job.context.custom_metadata:
            return job.context.custom_metadata['title']
        
        # Try to extract title from first few sentences
        if transcript.text:
            first_sentences = transcript.text[:200].strip()
            # Simple heuristic: use first sentence as title
            sentences = re.split(r'[.!?]+', first_sentences)
            if sentences and sentences[0].strip():
                potential_title = sentences[0].strip()
                # Clean up and limit length
                potential_title = re.sub(r'\s+', ' ', potential_title)
                if len(potential_title) > 80:
                    potential_title = potential_title[:77] + "..."
                return potential_title
        
        # Fallback: use filename and timestamp
        timestamp = job.created_at.strftime('%Y-%m-%d %H:%M')
        return f"Voice Note - {timestamp}"
    
    def _generate_frontmatter(
        self,
        job: ProcessingJob,
        transcript: TranscriptionResult,
        audio_metadata: AudioMetadata,
        hashes: HashInfo,
        title: str
    ) -> Dict[str, Any]:
        """Generate YAML frontmatter with comprehensive metadata."""
        
        # Get relative paths for links
        audio_rel_path = self._get_relative_audio_path(job)
        transcript_rel_path = self._get_relative_transcript_path(job)
        
        frontmatter = {
            'id': job.id,
            'title': title,
            'created': job.created_at.isoformat(),
            'processed': datetime.utcnow().isoformat(),
            'tags': job.context.tags,
            'audio_file': audio_rel_path,
            'transcript_file': transcript_rel_path,
            'duration': f"{int(audio_metadata.duration // 60):02d}:{int(audio_metadata.duration % 60):02d}",
            'file_size': self._format_file_size(audio_metadata.file_size),
            'sample_rate': audio_metadata.sample_rate,
            'channels': audio_metadata.channels,
            'format': audio_metadata.format,
            'profile': job.profile.value if job.profile else 'auto',
            'sha256_file': hashes.sha256_file,
            'sha256_pcm': hashes.sha256_pcm,
            'participants': [p['name'] for p in job.context.participants],
            'model_version': transcript.model,
            'filters_applied': self._get_applied_filters(job),
            'processing_version': '1.0.0',
            'original_filename': job.original_filename
        }
        
        # Add custom metadata
        for key, value in job.context.custom_metadata.items():
            if key not in frontmatter:
                frontmatter[key] = value
        
        return frontmatter
    
    def _generate_summary(self, transcript: TranscriptionResult) -> str:
        """Generate a summary from the transcript."""
        # Simple extractive summary - take first few sentences
        if not transcript.text:
            return "No transcript available."
        
        text = transcript.text.strip()
        sentences = re.split(r'[.!?]+', text)
        
        # Take first 2-3 sentences for summary
        summary_sentences = []
        char_count = 0
        for sentence in sentences[:3]:
            sentence = sentence.strip()
            if sentence and char_count + len(sentence) < 300:
                summary_sentences.append(sentence)
                char_count += len(sentence)
            else:
                break
        
        if summary_sentences:
            return '. '.join(summary_sentences) + '.'
        else:
            return text[:300] + '...' if len(text) > 300 else text
    
    def _extract_key_points(self, transcript: TranscriptionResult) -> List[str]:
        """Extract key points from the transcript."""
        # Simple keyword-based extraction
        if not transcript.text:
            return []
        
        key_phrases = []
        
        # Look for common key point indicators
        patterns = [
            r'(?:important|key|main|primary|crucial)(?:\s+\w+){0,3}\s+(?:point|issue|topic|concern)',
            r'(?:we need to|must|should|have to|important to)\s+\w+',
            r'(?:decision|conclusion|outcome|result|finding)',
            r'(?:problem|issue|challenge|concern|risk)',
            r'(?:solution|approach|strategy|plan|method)'
        ]
        
        text = transcript.text.lower()
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Extract surrounding context
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 100)
                context = transcript.text[start:end].strip()
                
                # Clean up context
                if context and len(context) > 20:
                    key_phrases.append(context)
        
        # Remove duplicates and limit
        unique_phrases = list(dict.fromkeys(key_phrases))[:5]
        return unique_phrases
    
    def _extract_decisions(self, transcript: TranscriptionResult) -> List[str]:
        """Extract decisions made during the conversation."""
        if not transcript.text:
            return []
        
        decision_phrases = []
        
        # Look for decision indicators
        patterns = [
            r'(?:we (?:decided|agreed|concluded|determined)|decision was|agreed (?:to|that)|settled on)',
            r'(?:final|ultimate|agreed) (?:decision|choice|plan)',
            r'(?:we\'ll|will|going to|plan to) (?:go with|use|implement|choose)'
        ]
        
        text = transcript.text.lower()
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Extract surrounding context
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 150)
                context = transcript.text[start:end].strip()
                
                if context and len(context) > 30:
                    decision_phrases.append(context)
        
        return list(dict.fromkeys(decision_phrases))[:3]
    
    def _extract_action_items(self, transcript: TranscriptionResult) -> List[str]:
        """Extract action items and tasks from the conversation."""
        if not transcript.text:
            return []
        
        action_phrases = []
        
        # Look for action indicators
        patterns = [
            r'(?:need to|have to|must|should|will|going to|plan to|action item)',
            r'(?:follow up|reach out|contact|call|email|send)',
            r'(?:schedule|arrange|organize|set up|coordinate)',
            r'(?:review|check|verify|confirm|validate)',
            r'(?:complete|finish|deliver|submit|prepare)'
        ]
        
        text = transcript.text.lower()
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Extract surrounding context
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 100)
                context = transcript.text[start:end].strip()
                
                if context and len(context) > 20:
                    action_phrases.append(context)
        
        return list(dict.fromkeys(action_phrases))[:5]
    
    def _build_note_content(
        self,
        frontmatter: Dict[str, Any],
        title: str,
        summary: str,
        key_points: List[str],
        decisions: List[str],
        action_items: List[str],
        participants: List[Dict[str, str]],
        audio_metadata: AudioMetadata,
        job: ProcessingJob,
        transcript: TranscriptionResult
    ) -> str:
        """Build the complete note content."""
        
        lines = []
        
        # YAML frontmatter
        lines.append("---")
        for key, value in frontmatter.items():
            if isinstance(value, list):
                if value:
                    lines.append(f"{key}:")
                    for item in value:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"{key}: []")
            elif isinstance(value, str) and ('\n' in value or ':' in value):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append("")
        
        # Title
        lines.append(f"# {title}")
        lines.append("")
        
        # Summary
        lines.append("## Summary")
        lines.append(summary)
        lines.append("")
        
        # Key Points
        if key_points:
            lines.append("## Key Points")
            for point in key_points:
                lines.append(f"- {point}")
            lines.append("")
        
        # Decisions
        if decisions:
            lines.append("## Decisions")
            for decision in decisions:
                lines.append(f"- {decision}")
            lines.append("")
        
        # Action Items
        if action_items:
            lines.append("## Action Items")
            for action in action_items:
                lines.append(f"- [ ] {action}")
            lines.append("")
        
        # People
        if participants:
            lines.append("## People")
            for participant in participants:
                name = participant.get('name', 'Unknown')
                role = participant.get('role', 'participant')
                lines.append(f"- **{name}**: {role}")
            lines.append("")
        
        # Technical Metadata
        lines.append("## Technical Metadata")
        lines.append(f"- **Duration**: {frontmatter['duration']}")
        lines.append(f"- **File Size**: {frontmatter['file_size']}")
        lines.append(f"- **Sample Rate**: {frontmatter['sample_rate']}Hz")
        lines.append(f"- **Channels**: {frontmatter['channels']}")
        lines.append(f"- **Format**: {frontmatter['format']}")
        lines.append(f"- **Profile**: {frontmatter['profile']}")
        lines.append(f"- **Model**: {frontmatter['model_version']}")
        lines.append(f"- **Processing**: {frontmatter['processing_version']}")
        lines.append("")
        
        # Links
        lines.append("## Links")
        lines.append(f"- [Audio File]({frontmatter['audio_file']})")
        lines.append(f"- [Transcript]({frontmatter['transcript_file']})")
        lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # Full Transcript
        lines.append("## Full Transcript")
        lines.append("")
        
        # Use formatted transcript with timestamps if available
        if transcript.segments:
            formatted_transcript = transcript.get_formatted_transcript(include_timestamps=True)
            lines.append(formatted_transcript)
        else:
            lines.append(transcript.text)
        
        return "\n".join(lines)
    
    def _get_relative_audio_path(self, job: ProcessingJob) -> str:
        """Get relative path to audio file."""
        if job.processed_audio_path:
            return str(job.processed_audio_path.relative_to(self.vault_path))
        return f"audio/{job.hashes.sha256_pcm[:8]}/{job.original_filename}"
    
    def _get_relative_transcript_path(self, job: ProcessingJob) -> str:
        """Get relative path to transcript file."""
        if job.transcript_path:
            return str(job.transcript_path.relative_to(self.vault_path))
        return f"transcripts/{job.hashes.sha256_pcm[:8]}/transcript.json"
    
    def _get_applied_filters(self, job: ProcessingJob) -> List[str]:
        """Get list of applied audio filters."""
        if job.profile:
            profile_config = self.config.processing.profiles.get(job.profile.value)
            if profile_config:
                return profile_config.filters
        return []
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"
    
    def _make_safe_filename(self, title: str, max_length: int = 50) -> str:
        """Make a filesystem-safe filename from title."""
        # Remove or replace unsafe characters
        safe_title = re.sub(r'[<>:"/\\|?*]', '-', title)
        safe_title = re.sub(r'\s+', '_', safe_title)
        safe_title = re.sub(r'_+', '_', safe_title)
        safe_title = safe_title.strip('_-')
        
        # Limit length
        if len(safe_title) > max_length:
            safe_title = safe_title[:max_length].rstrip('_-')
        
        return safe_title or "voice_note"