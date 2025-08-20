#!/usr/bin/env python3
"""
Basic tests for the voice note ingestion pipeline.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add the parent directories to the Python path
current_dir = Path(__file__).parent
scripts_dir = current_dir.parent.parent
project_dir = scripts_dir.parent
sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(scripts_dir))

from ingest.core import VoiceNoteProcessor, ProcessingState
from ingest.context import ContextManager
from ingest.index import MasterIndex


class TestContextManager(unittest.TestCase):
    """Test context management functionality."""
    
    def setUp(self):
        self.context_manager = ContextManager()
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_default_context(self):
        """Test default context values."""
        context = self.context_manager._get_default_context()
        
        self.assertEqual(context['audio_profile'], 'auto')
        self.assertFalse(context['force_split'])
        self.assertFalse(context['is_call'])
        self.assertEqual(context['tags'], [])
    
    def test_filename_flags_parsing(self):
        """Test parsing flags from filename."""
        test_file = self.temp_dir / "recording[CALL][TAGS:meeting,important].m4a"
        test_file.touch()
        
        context = self.context_manager._parse_filename_flags(test_file)
        
        self.assertTrue(context['is_call'])
        self.assertIn('meeting', context['tags'])
        self.assertIn('important', context['tags'])
    
    def test_sidecar_yaml_loading(self):
        """Test loading context from sidecar YAML file."""
        audio_file = self.temp_dir / "recording.m4a"
        sidecar_file = self.temp_dir / "recording.yml"
        
        audio_file.touch()
        
        sidecar_content = """
title: "Test Recording"
is_call: true
tags:
  - test
  - meeting
speaker_names:
  - Alice
  - Bob
"""
        
        with open(sidecar_file, 'w') as f:
            f.write(sidecar_content)
        
        context = self.context_manager._load_sidecar_yaml(audio_file)
        
        self.assertEqual(context['title'], 'Test Recording')
        self.assertTrue(context['is_call'])
        self.assertIn('test', context['tags'])
        self.assertIn('Alice', context['speaker_names'])


class TestMasterIndex(unittest.TestCase):
    """Test master index functionality."""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.index = MasterIndex(self.temp_dir)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_index_initialization(self):
        """Test index file creation."""
        self.assertTrue(self.index.index_file.exists())
        
        # Check initial content
        with open(self.index.index_file, 'r') as f:
            content = f.read()
        
        self.assertIn('Voice Notes Master Index', content)
        self.assertIn('total_recordings: 0', content)
    
    def test_entry_addition(self):
        """Test adding entries to the index."""
        # Create mock state data
        state_data = {
            'sha256_file': 'test123456789',
            'sha256_pcm': 'content123456789',
            'file_path': '/test/recording.m4a',
            'started_at': '2024-01-01T12:00:00Z',
            'context': {'tags': ['test']},
            'audio_result': {'duration': 60.0, 'profile': 'auto'},
            'transcription_result': {
                'meta_data': {
                    'language': 'en',
                    'word_count': 100,
                    'speaker_count': 1
                }
            },
            'note_result': {
                'note_metadata': {'title': 'Test Note'},
                'note_filename': 'test_note.md'
            }
        }
        
        # Add entry
        self.index.add_entry(state_data)
        
        # Verify entry exists
        self.assertTrue(self.index.is_processed('test123456789'))
        
        # Get entry and verify data
        entry = self.index.get_entry('test123456789')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['sha256_file'], 'test123456789')
        self.assertEqual(entry['duration'], 60.0)


class TestProcessingPipeline(unittest.TestCase):
    """Test core processing pipeline functionality."""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        # Note: This is a basic test setup - full pipeline tests would need
        # actual audio files and installed dependencies (FFmpeg, whisper.cpp)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_processing_states(self):
        """Test processing state enumeration."""
        states = list(ProcessingState)
        
        expected_states = [
            ProcessingState.QUEUED,
            ProcessingState.STAGING,
            ProcessingState.HASHING,
            ProcessingState.DONE,
            ProcessingState.ERROR
        ]
        
        for state in expected_states:
            self.assertIn(state, states)
    
    def test_supported_file_detection(self):
        """Test supported file type detection."""
        processor = VoiceNoteProcessor(self.temp_dir)
        
        # Test supported extensions
        supported_files = [
            Path('test.m4a'),
            Path('test.mp3'),
            Path('test.wav'),
            Path('test.mp4')
        ]
        
        for file_path in supported_files:
            self.assertTrue(processor._is_supported_audio_file(file_path))
        
        # Test unsupported extensions
        unsupported_files = [
            Path('test.txt'),
            Path('test.pdf'),
            Path('test.jpg')
        ]
        
        for file_path in unsupported_files:
            self.assertFalse(processor._is_supported_audio_file(file_path))


class TestUtilityFunctions(unittest.TestCase):
    """Test utility functions."""
    
    def test_duration_formatting(self):
        """Test duration formatting functions."""
        # This would test the _format_duration methods in various classes
        pass
    
    def test_hash_calculation(self):
        """Test file hash calculation."""
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # Create a test file
            test_file = temp_dir / "test.txt"
            test_content = b"Hello, World!"
            
            with open(test_file, 'wb') as f:
                f.write(test_content)
            
            # Calculate hash
            processor = VoiceNoteProcessor(temp_dir)
            file_hash = processor._calculate_file_hash(test_file)
            
            # Verify hash is correct length (SHA256 = 64 hex chars)
            self.assertEqual(len(file_hash), 64)
            self.assertTrue(all(c in '0123456789abcdef' for c in file_hash))
            
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)