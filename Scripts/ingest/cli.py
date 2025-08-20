"""
Command-line interface for voice note ingestion pipeline.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import click
from datetime import datetime

from config import load_config, Config
from pipeline import VoiceNoteProcessor, ProcessingError
from index import IndexManager
from watcher import FileWatcher
from models import ProcessingState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), help='Path to config file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--quiet', '-q', is_flag=True, help='Quiet mode (errors only)')
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool, quiet: bool):
    """Voice Note Ingestion Pipeline CLI"""
    
    # Set logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    # Load configuration
    try:
        config_path = Path(config) if config else None
        ctx.obj = load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--profile', type=click.Choice(['auto', 'call', 'wind', 'wide']), 
              help='Audio processing profile')
@click.option('--split-channels', is_flag=True, help='Process left/right channels separately')
@click.option('--is-call', is_flag=True, help='Mark as phone/video call')
@click.option('--tags', help='Comma-separated list of tags')
@click.option('--participants', help='Comma-separated list of participants')
@click.option('--speaker-labels', help='JSON string of speaker labels')
@click.option('--force', is_flag=True, help='Force reprocessing even if duplicate')
@click.pass_obj
def process(config: Config, file_path: str, profile: Optional[str], split_channels: bool,
           is_call: bool, tags: Optional[str], participants: Optional[str], 
           speaker_labels: Optional[str], force: bool):
    """Process a single voice note file."""
    
    processor = VoiceNoteProcessor(config)
    
    # Validate tools
    if not processor.validate_tools():
        click.echo("Required tools not available. Please install ffmpeg and whisper.cpp", err=True)
        sys.exit(1)
    
    # Build CLI overrides
    cli_overrides = {}
    if profile:
        cli_overrides['profile'] = profile
    if split_channels:
        cli_overrides['split_channels'] = True
    if is_call:
        cli_overrides['is_call'] = True
    if tags:
        cli_overrides['tags'] = [tag.strip() for tag in tags.split(',')]
    if participants:
        cli_overrides['participants'] = [p.strip() for p in participants.split(',')]
    if speaker_labels:
        import json
        try:
            cli_overrides['speaker_labels'] = json.loads(speaker_labels)
        except json.JSONDecodeError:
            click.echo("Invalid speaker labels JSON", err=True)
            sys.exit(1)
    
    # Process the file
    try:
        click.echo(f"Processing: {file_path}")
        job = processor.process_file(Path(file_path), cli_overrides, force)
        
        if job:
            if job.state == ProcessingState.DONE:
                click.echo(f"✅ Successfully processed: {job.note_path}")
            elif job.state == ProcessingState.ERROR:
                click.echo(f"❌ Processing failed: {job.error_message}", err=True)
            else:
                click.echo(f"🔄 Processing interrupted at: {job.state.value}")
        else:
            click.echo("⚠️  File is already being processed or was skipped")
            
    except ProcessingError as e:
        click.echo(f"❌ Processing error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--daemon', is_flag=True, help='Run as daemon (background service)')
@click.option('--once', is_flag=True, help='Process existing files once and exit')
@click.pass_obj
def watch(config: Config, daemon: bool, once: bool):
    """Watch Downloads folder for new voice note files."""
    
    processor = VoiceNoteProcessor(config)
    
    # Validate tools
    if not processor.validate_tools():
        click.echo("Required tools not available. Please install ffmpeg and whisper.cpp", err=True)
        sys.exit(1)
    
    try:
        watcher = FileWatcher(config, processor)
        
        if once:
            # Process existing files once
            click.echo("Processing existing files...")
            processed_count = watcher.process_existing_files()
            click.echo(f"Processed {processed_count} existing files")
        else:
            # Start watching
            click.echo(f"Watching: {watcher.watch_path}")
            if daemon:
                click.echo("Running in daemon mode...")
            
            watcher.start_watching(daemon=daemon)
            
    except KeyboardInterrupt:
        click.echo("\n🛑 Stopping file watcher...")
    except Exception as e:
        click.echo(f"❌ Watch error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--sha', required=True, help='SHA256 hash (file or PCM) of the content to reprocess')
@click.option('--profile', type=click.Choice(['auto', 'call', 'wind', 'wide']), 
              help='Audio processing profile')
@click.option('--split-channels', is_flag=True, help='Process left/right channels separately')
@click.option('--tags', help='Comma-separated list of tags to add')
@click.pass_obj
def reprocess(config: Config, sha: str, profile: Optional[str], split_channels: bool, tags: Optional[str]):
    """Reprocess an existing voice note with different settings."""
    
    processor = VoiceNoteProcessor(config)
    index_manager = IndexManager(config)
    
    # Find existing entry
    entry = index_manager.get_entry_by_pcm_hash(sha) or index_manager.get_entry_by_file_hash(sha)
    if not entry:
        click.echo(f"❌ No entry found for hash: {sha}", err=True)
        sys.exit(1)
    
    # Find original file
    audio_path = Path(config.vault.base_path) / entry.audio_path
    if not audio_path.exists():
        click.echo(f"❌ Audio file not found: {audio_path}", err=True)
        sys.exit(1)
    
    # Build CLI overrides
    cli_overrides = {}
    if profile:
        cli_overrides['profile'] = profile
    if split_channels:
        cli_overrides['split_channels'] = True
    if tags:
        existing_tags = entry.tags
        new_tags = [tag.strip() for tag in tags.split(',')]
        cli_overrides['tags'] = list(set(existing_tags + new_tags))
    
    try:
        click.echo(f"Reprocessing: {entry.title}")
        job = processor.process_file(audio_path, cli_overrides, force_reprocess=True)
        
        if job and job.state == ProcessingState.DONE:
            click.echo(f"✅ Successfully reprocessed: {job.note_path}")
        else:
            click.echo("❌ Reprocessing failed", err=True)
            
    except Exception as e:
        click.echo(f"❌ Reprocessing error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--sha', required=True, help='SHA256 hash to verify')
@click.option('--fix', is_flag=True, help='Attempt to fix any issues found')
@click.pass_obj
def verify(config: Config, sha: str, fix: bool):
    """Verify integrity of processed voice note artifacts."""
    
    index_manager = IndexManager(config)
    
    # Find entry
    entry = index_manager.get_entry_by_pcm_hash(sha) or index_manager.get_entry_by_file_hash(sha)
    if not entry:
        click.echo(f"❌ No entry found for hash: {sha}", err=True)
        sys.exit(1)
    
    vault_path = Path(config.vault.base_path)
    issues = []
    
    # Check files exist
    note_path = vault_path / entry.note_path
    audio_path = vault_path / entry.audio_path
    transcript_path = vault_path / entry.transcript_path
    
    if not note_path.exists():
        issues.append(f"Missing note file: {note_path}")
    if not audio_path.exists():
        issues.append(f"Missing audio file: {audio_path}")
    if not transcript_path.exists():
        issues.append(f"Missing transcript file: {transcript_path}")
    
    # Verify file sizes and basic integrity
    if audio_path.exists():
        try:
            from .audio import AudioProcessor
            processor = AudioProcessor(config)
            metadata = processor.probe_audio(audio_path)
            
            if abs(metadata.duration - entry.duration) > 1.0:  # Allow 1 second difference
                issues.append(f"Duration mismatch: expected {entry.duration}, got {metadata.duration}")
            
        except Exception as e:
            issues.append(f"Audio verification failed: {e}")
    
    # Report results
    if issues:
        click.echo(f"❌ Verification failed for {entry.title}:")
        for issue in issues:
            click.echo(f"  - {issue}")
        
        if fix:
            click.echo("🔧 Attempting to fix issues...")
            # TODO: Implement fix logic
            click.echo("Fix functionality not yet implemented")
    else:
        click.echo(f"✅ Verification passed for {entry.title}")


@cli.command()
@click.option('--force', is_flag=True, help='Force rebuild even if index exists')
@click.pass_obj
def rebuild_index(config: Config, force: bool):
    """Rebuild the master index by scanning note files."""
    
    index_manager = IndexManager(config)
    
    if not force:
        stats = index_manager.get_stats()
        if stats['total_entries'] > 0:
            if not click.confirm(f"Index has {stats['total_entries']} entries. Rebuild anyway?"):
                return
    
    try:
        click.echo("Rebuilding index from note files...")
        rebuilt_count = index_manager.rebuild_from_notes()
        click.echo(f"✅ Rebuilt index with {rebuilt_count} entries")
        
    except Exception as e:
        click.echo(f"❌ Index rebuild failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--tags', help='Filter by tags (comma-separated)')
@click.option('--participants', help='Filter by participants (comma-separated)')
@click.option('--limit', type=int, default=10, help='Limit number of results')
@click.pass_obj
def list_notes(config: Config, tags: Optional[str], participants: Optional[str], limit: int):
    """List processed voice notes."""
    
    index_manager = IndexManager(config)
    
    # Parse filters
    tag_filter = [tag.strip() for tag in tags.split(',')] if tags else None
    participant_filter = [p.strip() for p in participants.split(',')] if participants else None
    
    # Get entries
    entries = index_manager.list_entries(
        tags=tag_filter,
        participants=participant_filter
    )
    
    if not entries:
        click.echo("No voice notes found")
        return
    
    # Display results
    click.echo(f"Found {len(entries)} voice notes:")
    click.echo("")
    
    for i, entry in enumerate(entries[:limit]):
        date_str = entry.processed_at.strftime('%Y-%m-%d %H:%M')
        duration_str = f"{int(entry.duration // 60):02d}:{int(entry.duration % 60):02d}"
        
        click.echo(f"{i+1:2d}. {entry.title}")
        click.echo(f"    Date: {date_str}  Duration: {duration_str}")
        click.echo(f"    Tags: {', '.join(entry.tags) if entry.tags else 'None'}")
        click.echo(f"    Participants: {', '.join(entry.participants) if entry.participants else 'None'}")
        click.echo(f"    Hash: {entry.sha256_pcm[:8]}")
        click.echo("")
    
    if len(entries) > limit:
        click.echo(f"... and {len(entries) - limit} more")


@cli.command()
@click.pass_obj
def status(config: Config):
    """Show system status and statistics."""
    
    try:
        processor = VoiceNoteProcessor(config)
        index_manager = IndexManager(config)
        
        # Get statistics
        processing_stats = processor.get_processing_stats()
        index_stats = index_manager.get_stats()
        
        # Display status
        click.echo("📊 Voice Note Ingestion Pipeline Status")
        click.echo("")
        
        click.echo("Configuration:")
        click.echo(f"  Vault Path: {processing_stats['vault_path']}")
        click.echo(f"  Watch Path: {config.watcher.watch_path}")
        click.echo("")
        
        click.echo("Index Statistics:")
        click.echo(f"  Total Entries: {index_stats['total_entries']}")
        click.echo(f"  Total Duration: {index_stats['total_duration']:.1f} seconds")
        click.echo(f"  Total Size: {index_stats['total_size'] / (1024*1024):.1f} MB")
        click.echo(f"  Unique Participants: {index_stats['unique_participants']}")
        click.echo(f"  Unique Tags: {index_stats['unique_tags']}")
        
        if index_stats['date_range']:
            click.echo(f"  Date Range: {index_stats['date_range']['earliest']} to {index_stats['date_range']['latest']}")
        
        click.echo("")
        
        if processing_stats['active_jobs'] > 0:
            click.echo("Active Jobs:")
            for state, count in processing_stats['state_distribution'].items():
                click.echo(f"  {state}: {count}")
        else:
            click.echo("No active processing jobs")
        
        # Tool validation
        click.echo("")
        tools_ok = processor.validate_tools()
        click.echo(f"Tools Available: {'✅' if tools_ok else '❌'}")
        
    except Exception as e:
        click.echo(f"❌ Status check failed: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point for the CLI."""
    cli()