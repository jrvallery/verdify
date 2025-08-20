"""
File watcher for automatic voice note ingestion.
"""

import time
import threading
from pathlib import Path
from typing import Set, Optional
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from config import Config
from pipeline import VoiceNoteProcessor

logger = logging.getLogger(__name__)


class VoiceNoteHandler(FileSystemEventHandler):
    """Handles file system events for voice note ingestion."""
    
    def __init__(self, config: Config, processor: VoiceNoteProcessor):
        super().__init__()
        self.config = config
        self.processor = processor
        self.supported_formats = set(config.supported_formats)
        
        # Debouncing: track files that are being written
        self._pending_files: Set[str] = set()
        self._debounce_lock = threading.Lock()
    
    def on_created(self, event):
        """Handle file creation events."""
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            self._handle_file(Path(event.src_path))
    
    def on_moved(self, event):
        """Handle file move events (common when files are copied)."""
        if isinstance(event, FileMovedEvent) and not event.is_directory:
            self._handle_file(Path(event.dest_path))
    
    def _handle_file(self, file_path: Path):
        """Handle a potential voice note file."""
        
        # Check if file extension is supported
        if file_path.suffix.lower() not in self.supported_formats:
            logger.debug(f"Ignoring unsupported file: {file_path}")
            return
        
        # Skip hidden files and temporary files
        if file_path.name.startswith('.') or file_path.name.startswith('~'):
            logger.debug(f"Ignoring hidden/temp file: {file_path}")
            return
        
        # Skip files that are still being written (common with large files)
        if self._is_file_being_written(file_path):
            logger.debug(f"File still being written, will retry: {file_path}")
            # Schedule retry after debounce period
            threading.Timer(self.config.watcher.debounce_seconds, 
                          lambda: self._handle_file(file_path)).start()
            return
        
        logger.info(f"🎵 New voice note detected: {file_path}")
        
        try:
            # Process the file
            job = self.processor.process_file(file_path)
            
            if job:
                logger.info(f"✅ Auto-processed: {job.original_filename}")
            else:
                logger.warning(f"⚠️  Could not process: {file_path}")
                
        except Exception as e:
            logger.error(f"❌ Auto-processing failed for {file_path}: {e}")
    
    def _is_file_being_written(self, file_path: Path) -> bool:
        """Check if file is still being written by monitoring size changes."""
        
        if not file_path.exists():
            return True
        
        try:
            # Check file size twice with a small delay
            size1 = file_path.stat().st_size
            time.sleep(0.5)
            
            if not file_path.exists():
                return True
                
            size2 = file_path.stat().st_size
            
            # If size changed, file is still being written
            return size1 != size2
            
        except (OSError, FileNotFoundError):
            # File access issues suggest it's still being written
            return True


class FileWatcher:
    """Main file watcher service."""
    
    def __init__(self, config: Config, processor: VoiceNoteProcessor):
        self.config = config
        self.processor = processor
        self.watch_path = Path(config.watcher.watch_path).expanduser().resolve()
        
        if not self.watch_path.exists():
            raise FileNotFoundError(f"Watch path does not exist: {self.watch_path}")
        
        self.observer = Observer()
        self.handler = VoiceNoteHandler(config, processor)
        self._is_watching = False
    
    def start_watching(self, daemon: bool = False):
        """Start watching for file changes."""
        
        if self._is_watching:
            logger.warning("File watcher is already running")
            return
        
        logger.info(f"Starting file watcher on: {self.watch_path}")
        
        # Set up observer
        self.observer.schedule(self.handler, str(self.watch_path), recursive=False)
        self.observer.start()
        self._is_watching = True
        
        try:
            if daemon:
                # Run in daemon mode - keep process alive
                while self._is_watching:
                    time.sleep(1)
            else:
                # Interactive mode - wait for keyboard interrupt
                logger.info("Press Ctrl+C to stop watching...")
                while self._is_watching:
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop_watching()
    
    def stop_watching(self):
        """Stop the file watcher."""
        if self._is_watching:
            logger.info("Stopping file watcher...")
            self.observer.stop()
            self.observer.join()
            self._is_watching = False
            logger.info("File watcher stopped")
    
    def process_existing_files(self) -> int:
        """Process existing files in the watch directory."""
        logger.info(f"Scanning for existing files in: {self.watch_path}")
        
        processed_count = 0
        
        try:
            # Find all supported audio files
            for file_path in self.watch_path.iterdir():
                if (file_path.is_file() and 
                    file_path.suffix.lower() in self.config.supported_formats and
                    not file_path.name.startswith('.') and
                    not file_path.name.startswith('~')):
                    
                    try:
                        logger.info(f"Processing existing file: {file_path}")
                        job = self.processor.process_file(file_path)
                        
                        if job:
                            processed_count += 1
                            logger.info(f"✅ Processed: {job.original_filename}")
                        else:
                            logger.warning(f"⚠️  Skipped: {file_path}")
                            
                    except Exception as e:
                        logger.error(f"❌ Failed to process {file_path}: {e}")
        
        except Exception as e:
            logger.error(f"Error scanning directory {self.watch_path}: {e}")
        
        logger.info(f"Processed {processed_count} existing files")
        return processed_count
    
    def get_status(self) -> dict:
        """Get current watcher status."""
        return {
            "is_watching": self._is_watching,
            "watch_path": str(self.watch_path),
            "supported_formats": list(self.config.supported_formats),
            "debounce_seconds": self.config.watcher.debounce_seconds
        }