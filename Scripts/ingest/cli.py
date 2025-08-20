#!/usr/bin/env python3
"""
Command-line interface for the voice note ingestion pipeline.
"""

import os
import sys
import click
from pathlib import Path
from typing import Optional

from .core import VoiceNoteProcessor
from .watcher import FileWatcher
from .index import MasterIndex
from .context import ContextManager


@click.group()
@click.version_option(version="1.0.0")
@click.option("--vault-path", type=click.Path(exists=True, file_okay=False, dir_okay=True),
              default="~/VoiceNotes", help="Path to VoiceNotes vault")
@click.option("--downloads-path", type=click.Path(exists=True, file_okay=False, dir_okay=True),
              default="~/Downloads", help="Path to Downloads folder to monitor")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, vault_path: str, downloads_path: str, verbose: bool):
    """Voice Note Ingestion Pipeline - Process audio files into structured Obsidian notes."""
    # Ensure the context object exists
    ctx.ensure_object(dict)
    
    # Store configuration in context
    ctx.obj['vault_path'] = Path(vault_path).expanduser().resolve()
    ctx.obj['downloads_path'] = Path(downloads_path).expanduser().resolve()
    ctx.obj['verbose'] = verbose
    
    # Initialize processor
    ctx.obj['processor'] = VoiceNoteProcessor(
        vault_path=ctx.obj['vault_path'],
        verbose=verbose
    )


@cli.command()
@click.option("--interval", default=5, help="Check interval in seconds")
@click.pass_context
def watch(ctx, interval: int):
    """Watch Downloads folder for new audio files and process them automatically."""
    vault_path = ctx.obj['vault_path']
    downloads_path = ctx.obj['downloads_path']
    processor = ctx.obj['processor']
    verbose = ctx.obj['verbose']
    
    click.echo(f"Starting file watcher...")
    click.echo(f"  Monitoring: {downloads_path}")
    click.echo(f"  Vault: {vault_path}")
    click.echo(f"  Check interval: {interval}s")
    
    watcher = FileWatcher(
        downloads_path=downloads_path,
        processor=processor,
        check_interval=interval,
        verbose=verbose
    )
    
    try:
        watcher.start()
    except KeyboardInterrupt:
        click.echo("\\nShutting down file watcher...")
        watcher.stop()


@cli.command()
@click.argument("file_path", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.option("--force", is_flag=True, help="Force reprocessing even if already processed")
@click.option("--profile", default="auto", 
              type=click.Choice(['auto', 'call', 'wind', 'wide']),
              help="Audio processing profile")
@click.option("--split", is_flag=True, help="Force split-channel mode")
@click.option("--call", is_flag=True, help="Mark as call recording")
@click.option("--tags", help="Comma-separated tags to add")
@click.option("--speaker-names", help="Comma-separated speaker names for multi-speaker content")
@click.pass_context
def process(ctx, file_path: str, force: bool, profile: str, split: bool, 
           call: bool, tags: Optional[str], speaker_names: Optional[str]):
    """Process a single audio file through the ingestion pipeline."""
    processor = ctx.obj['processor']
    
    file_path = Path(file_path).resolve()
    
    # Build context from CLI flags
    context = {}
    if profile != "auto":
        context['audio_profile'] = profile
    if split:
        context['force_split'] = True
    if call:
        context['is_call'] = True
    if tags:
        context['tags'] = [tag.strip() for tag in tags.split(',')]
    if speaker_names:
        context['speaker_names'] = [name.strip() for name in speaker_names.split(',')]
    
    click.echo(f"Processing: {file_path}")
    
    try:
        result = processor.process_file(file_path, context=context, force=force)
        if result:
            click.echo(f"✅ Successfully processed: {result['note_path']}")
            click.echo(f"   SHA256: {result['sha256_file']}")
            click.echo(f"   Duration: {result.get('duration', 'unknown')}")
        else:
            click.echo("❌ Processing failed")
    except Exception as e:
        click.echo(f"❌ Error processing file: {e}")
        if ctx.obj['verbose']:
            import traceback
            traceback.print_exc()


@cli.command()
@click.option("--sha", required=True, help="SHA256 hash of the file to reprocess")
@click.option("--profile", default="auto",
              type=click.Choice(['auto', 'call', 'wind', 'wide']),
              help="Audio processing profile")
@click.option("--tags", help="Comma-separated tags to add")
@click.pass_context
def reprocess(ctx, sha: str, profile: str, tags: Optional[str]):
    """Reprocess an existing recording with different settings."""
    processor = ctx.obj['processor']
    
    click.echo(f"Reprocessing SHA: {sha}")
    
    # Build new context
    context = {}
    if profile != "auto":
        context['audio_profile'] = profile
    if tags:
        context['tags'] = [tag.strip() for tag in tags.split(',')]
    
    try:
        result = processor.reprocess_by_sha(sha, context=context)
        if result:
            click.echo(f"✅ Successfully reprocessed: {result['note_path']}")
        else:
            click.echo("❌ Reprocessing failed")
    except Exception as e:
        click.echo(f"❌ Error reprocessing: {e}")
        if ctx.obj['verbose']:
            import traceback
            traceback.print_exc()


@cli.command()
@click.option("--sha", required=True, help="SHA256 hash of the file to verify")
@click.pass_context
def verify(ctx, sha: str):
    """Verify artifacts for a processed recording."""
    processor = ctx.obj['processor']
    
    click.echo(f"Verifying SHA: {sha}")
    
    try:
        is_valid = processor.verify_artifacts(sha)
        if is_valid:
            click.echo("✅ All artifacts are valid")
        else:
            click.echo("❌ Some artifacts are missing or invalid")
    except Exception as e:
        click.echo(f"❌ Error during verification: {e}")


@cli.command("rebuild-index")
@click.pass_context
def rebuild_index(ctx):
    """Rebuild the master index from existing notes."""
    vault_path = ctx.obj['vault_path']
    
    click.echo("Rebuilding master index...")
    
    try:
        index = MasterIndex(vault_path)
        count = index.rebuild_from_notes()
        click.echo(f"✅ Rebuilt index with {count} entries")
    except Exception as e:
        click.echo(f"❌ Error rebuilding index: {e}")


@cli.command()
@click.pass_context
def status(ctx):
    """Show status of the voice notes system."""
    vault_path = ctx.obj['vault_path']
    
    try:
        index = MasterIndex(vault_path)
        stats = index.get_stats()
        
        click.echo("📊 Voice Notes Status")
        click.echo("=" * 30)
        click.echo(f"Vault path: {vault_path}")
        click.echo(f"Total recordings: {stats.get('total_recordings', 0)}")
        click.echo(f"Total duration: {stats.get('total_duration', 'unknown')}")
        click.echo(f"Last processed: {stats.get('last_processed', 'never')}")
        click.echo(f"Storage used: {stats.get('storage_used', 'unknown')}")
    except Exception as e:
        click.echo(f"❌ Error getting status: {e}")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()