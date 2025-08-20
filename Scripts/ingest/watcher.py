#!/usr/bin/env python3
"""
File watcher for voice note ingestion.
Monitors Downloads folder for new audio files and processes them automatically.
"""

import os
import time
import logging
import threading
from pathlib import Path
from typing import Set, Dict, Any, Optional
from datetime import datetime, timedelta

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    
    # Create dummy base class if watchdog not available
    class FileSystemEventHandler:
        pass


class VoiceNoteFileHandler(FileSystemEventHandler):
    """File system event handler for voice note files."""
    
    def __init__(self, processor, debounce_seconds: int = 5, verbose: bool = False):
        super().__init__()
        self.processor = processor
        self.debounce_seconds = debounce_seconds
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        
        # Track files to debounce rapid changes
        self.pending_files: Dict[str, datetime] = {}
        self.processing_files: Set[str] = set()
        
        # Supported extensions
        self.supported_extensions = {
            '.m4a', '.mp3', '.wav', '.aac', '.flac', '.caf',
            '.mp4', '.mov', '.opus', '.ogg', '.webm'
        }
        
        # Start debounce processing thread
        self.running = True
        self.debounce_thread = threading.Thread(target=self._debounce_worker, daemon=True)
        self.debounce_thread.start()
    
    def stop(self):
        """Stop the file handler."""
        self.running = False
        if self.debounce_thread.is_alive():
            self.debounce_thread.join(timeout=5)
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            self._handle_file_event(event.src_path, 'created')
    
    def on_moved(self, event):
        """Handle file move events."""
        if not event.is_directory:
            self._handle_file_event(event.dest_path, 'moved')
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory:
            self._handle_file_event(event.src_path, 'modified')
    
    def _handle_file_event(self, file_path: str, event_type: str):
        """Handle a file system event."""
        file_path = Path(file_path).resolve()
        
        # Check if it's a supported audio file
        if not self._is_supported_file(file_path):
            return
        
        # Skip if already processing
        if str(file_path) in self.processing_files:
            return
        
        # Add to pending files with current timestamp
        self.pending_files[str(file_path)] = datetime.now()
        
        self.logger.debug(f"File {event_type}: {file_path} (debouncing)")
    
    def _is_supported_file(self, file_path: Path) -> bool:
        """Check if file is a supported audio/video format."""
        return file_path.suffix.lower() in self.supported_extensions
    
    def _debounce_worker(self):
        """Worker thread to process debounced files."""
        while self.running:
            try:
                current_time = datetime.now()
                files_to_process = []
                
                # Find files that have been stable for debounce period
                for file_path, last_event_time in list(self.pending_files.items()):
                    if current_time - last_event_time >= timedelta(seconds=self.debounce_seconds):
                        files_to_process.append(file_path)
                        del self.pending_files[file_path]
                
                # Process stable files
                for file_path in files_to_process:
                    self._process_file(Path(file_path))
                
                # Sleep before next check
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error in debounce worker: {e}")
                time.sleep(5)  # Longer sleep on error
    
    def _process_file(self, file_path: Path):
        """Process a single file."""
        file_path_str = str(file_path)
        
        try:
            # Mark as processing
            self.processing_files.add(file_path_str)
            
            # Verify file still exists and is readable
            if not file_path.exists():
                self.logger.debug(f"File no longer exists: {file_path}")
                return
            
            # Check if file is still being written (size changing)
            if self._is_file_being_written(file_path):
                # Put back in pending queue
                self.pending_files[file_path_str] = datetime.now()
                self.logger.debug(f"File still being written: {file_path}")
                return
            
            self.logger.info(f"Processing detected file: {file_path}")
            
            # Process the file
            result = self.processor.process_file(file_path, force=False)
            
            if result:
                self.logger.info(f"✅ Successfully processed: {file_path}")
                self.logger.info(f"   Note: {result.get('note_path', 'unknown')}")
            else:
                self.logger.warning(f"❌ Failed to process: {file_path}")
                
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
        finally:
            # Remove from processing set
            self.processing_files.discard(file_path_str)
    
    def _is_file_being_written(self, file_path: Path) -> bool:
        """Check if file is still being written by comparing size over time."""
        try:
            size1 = file_path.stat().st_size
            time.sleep(1)
            size2 = file_path.stat().st_size
            return size1 != size2
        except:
            return True  # Assume still being written if we can't check


class FileWatcher:
    """Main file watcher for voice note ingestion."""
    
    def __init__(self, downloads_path: Path, processor, check_interval: int = 5, 
                 debounce_seconds: int = 5, verbose: bool = False):
        self.downloads_path = Path(downloads_path)
        self.processor = processor
        self.check_interval = check_interval
        self.debounce_seconds = debounce_seconds
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        
        self.running = False
        self.observer = None
        self.handler = None
        
        # Track processed files in this session
        self.session_processed: Set[str] = set()
        
        # Fallback polling thread
        self.polling_thread = None
    
    def start(self):
        """Start the file watcher."""
        if self.running:
            self.logger.warning("File watcher is already running")
            return
        
        self.running = True
        
        if not self.downloads_path.exists():
            self.logger.error(f"Downloads path does not exist: {self.downloads_path}")
            return
        
        self.logger.info(f"Starting file watcher on: {self.downloads_path}")
        
        # Try to use watchdog if available
        if WATCHDOG_AVAILABLE:
            try:
                self._start_watchdog()
                self.logger.info("Using watchdog for file monitoring")
                return
            except Exception as e:
                self.logger.warning(f"Failed to start watchdog: {e}")
        
        # Fallback to polling
        self._start_polling()
        self.logger.info("Using polling for file monitoring")
    
    def stop(self):
        """Stop the file watcher."""
        if not self.running:
            return
        
        self.logger.info("Stopping file watcher")
        self.running = False
        
        # Stop watchdog observer
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        
        # Stop handler
        if self.handler:
            self.handler.stop()
            self.handler = None
        
        # Stop polling thread
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=10)
    
    def _start_watchdog(self):
        """Start watchdog-based monitoring."""
        self.handler = VoiceNoteFileHandler(
            processor=self.processor,
            debounce_seconds=self.debounce_seconds,
            verbose=self.verbose
        )
        
        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.downloads_path), recursive=False)
        self.observer.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    
    def _start_polling(self):
        """Start polling-based monitoring."""
        self.polling_thread = threading.Thread(target=self._polling_worker, daemon=True)
        self.polling_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    
    def _polling_worker(self):
        """Worker thread for polling-based file monitoring."""
        known_files: Dict[str, float] = {}  # file_path -> modification_time
        
        while self.running:
            try:
                current_files = {}
                
                # Scan downloads directory
                for file_path in self.downloads_path.iterdir():
                    if file_path.is_file() and self._is_supported_file(file_path):
                        try:
                            mtime = file_path.stat().st_mtime
                            current_files[str(file_path)] = mtime
                        except:
                            continue
                
                # Find new or modified files
                for file_path_str, mtime in current_files.items():
                    file_path = Path(file_path_str)
                    
                    # Skip if already processed in this session
                    if file_path_str in self.session_processed:
                        continue
                    
                    # Check if new or modified
                    if (file_path_str not in known_files or 
                        mtime > known_files[file_path_str]):
                        
                        # Wait for file to be stable
                        if self._wait_for_stable_file(file_path):
                            self._process_file_polling(file_path)
                
                # Update known files
                known_files = current_files
                
                # Sleep until next scan
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in polling worker: {e}")
                time.sleep(10)  # Longer sleep on error
    
    def _wait_for_stable_file(self, file_path: Path, max_wait: int = 30) -> bool:
        """Wait for file to be stable (not being written)."""
        stable_count = 0
        required_stable = 3  # Number of consecutive stable checks
        
        for _ in range(max_wait):
            try:
                size1 = file_path.stat().st_size
                time.sleep(1)
                size2 = file_path.stat().st_size
                
                if size1 == size2:
                    stable_count += 1
                    if stable_count >= required_stable:
                        return True
                else:
                    stable_count = 0
                    
            except:
                return False
        
        return False
    
    def _process_file_polling(self, file_path: Path):
        """Process a file detected via polling."""
        file_path_str = str(file_path)
        
        try:
            self.logger.info(f"Processing detected file: {file_path}")
            
            # Process the file
            result = self.processor.process_file(file_path, force=False)
            
            if result:
                self.logger.info(f"✅ Successfully processed: {file_path}")
                self.logger.info(f"   Note: {result.get('note_path', 'unknown')}")
                self.session_processed.add(file_path_str)
            else:
                self.logger.warning(f"❌ Failed to process: {file_path}")
                
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
    
    def _is_supported_file(self, file_path: Path) -> bool:
        """Check if file is a supported audio/video format."""
        supported_extensions = {
            '.m4a', '.mp3', '.wav', '.aac', '.flac', '.caf',
            '.mp4', '.mov', '.opus', '.ogg', '.webm'
        }
        return file_path.suffix.lower() in supported_extensions
    
    def get_status(self) -> Dict[str, Any]:
        """Get watcher status information."""
        return {
            'running': self.running,
            'downloads_path': str(self.downloads_path),
            'check_interval': self.check_interval,
            'debounce_seconds': self.debounce_seconds,
            'using_watchdog': self.observer is not None,
            'session_processed': len(self.session_processed),
            'pending_files': len(getattr(self.handler, 'pending_files', {})),
            'processing_files': len(getattr(self.handler, 'processing_files', set()))
        }