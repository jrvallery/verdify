# Voice Note Ingestion Pipeline

A production-ready voice note ingestion system that processes audio files from Downloads folder through a crash-safe pipeline to create structured notes in an Obsidian vault.

## Features

- **Crash-Safe Processing**: Lock files and atomic operations ensure no data loss
- **Dual-Hash Deduplication**: File hash + content hash for cross-format duplicate detection
- **Multi-Speaker Support**: Split-channel and diarization modes
- **Rich Note Generation**: Comprehensive metadata and structured templates
- **Auto File Monitoring**: LaunchAgent integration for zero-friction processing
- **Adaptive Audio Processing**: Profiles for different recording scenarios
- **Context Injection**: Sidecar YAML files and filename flags

## Quick Start

### 1. Installation

```bash
# Install Python dependencies
cd Scripts/ingest
pip3 install -r requirements.txt

# Install system dependencies (macOS)
brew install ffmpeg
brew install whisper-cpp

# Download whisper model
whisper-cpp-download-ggml-model large-v3
```

### 2. Basic Usage

```bash
# Process a single file
python3 -m ingest process ~/Downloads/recording.m4a

# Start file watcher
python3 -m ingest watch

# Check status
python3 -m ingest status
```

### 3. Configuration

Edit `VoiceNotes/config.yml` to customize:
- Audio processing profiles
- Transcription settings
- Note templates
- File monitoring options

## Architecture

### Vault Structure
```
VoiceNotes/
├── _index.md                      # Master ledger
├── config.yml                     # Configuration
├── templates/note.md               # Note template
├── audio/
│   └── <sha256>/
│       ├── original.m4a           # Original file
│       └── normalized.wav         # Processed audio
├── transcripts/
│   └── <sha256>/
│       ├── transcript.txt         # Plain text
│       ├── transcript.srt         # Subtitles
│       ├── transcript.vtt         # WebVTT
│       └── meta.json             # Metadata
├── notes/
│   └── 2024-01-15_1430__meeting__a1b2c3d4.md
├── logs/
├── state/                         # Lock files
└── staging/                       # Temp processing
```

### Processing Pipeline

States: `queued → staging → hashing → dedupe-check → transcode → transcribe → assemble-note → index-update → finalize → done`

1. **Staging**: Copy file to safe processing area
2. **Hashing**: Calculate file and content hashes
3. **Dedupe Check**: Compare against existing recordings
4. **Transcode**: Normalize audio with appropriate filters
5. **Transcribe**: Convert speech to text with timestamps
6. **Assemble Note**: Generate structured Obsidian note
7. **Index Update**: Add entry to master ledger
8. **Finalize**: Move artifacts to final locations

## CLI Commands

### Processing

```bash
# Process single file
ingest process <file> [options]

# Options:
--force                    # Reprocess even if already done
--profile auto|call|wind|wide  # Audio processing profile
--split                    # Force split-channel mode
--call                     # Mark as call recording
--tags "tag1,tag2"         # Add tags
--speaker-names "Alice,Bob"  # Speaker names
```

### File Watching

```bash
# Start watcher
ingest watch [options]

# Options:
--interval 5               # Check interval (seconds)
```

### Management

```bash
# Reprocess existing recording
ingest reprocess --sha <hash> [options]

# Verify artifacts
ingest verify --sha <hash>

# Rebuild index
ingest rebuild-index

# Show status
ingest status
```

## Audio Processing Profiles

### Auto (Default)
- Balanced processing for general recordings
- 60Hz highpass, 16kHz lowpass
- Moderate compression and limiting

### Call
- Optimized for telephony/calls
- 80Hz highpass, 8kHz lowpass (speech range)
- Strong compression for clarity

### Wind
- Outdoor recordings with wind noise
- 120Hz highpass for wind reduction
- Noise reduction filters

### Wide
- High-quality recordings
- Minimal processing, full spectrum
- Preserves audio fidelity

## Context Injection

### Filename Flags

```
recording[CALL][TAGS:meeting,important].m4a
recording[SPLIT][SPEAKERS:Alice,Bob].m4a
recording[PROFILE:wind].m4a
```

### Sidecar YAML Files

Create `recording.yml` alongside `recording.m4a`:

```yaml
title: "Project Meeting"
is_call: true
tags: [meeting, project-alpha]
speaker_names: [Alice, Bob]
location: "conference room"
summary: "Weekly project update"
key_points:
  - "Project on track"
  - "Budget approved"
actions:
  - "Update timeline"
  - "Send report"
```

## Multi-Speaker Support

### Split-Channel Mode
- Processes L/R channels separately
- Each channel = one speaker
- Merges transcripts with speaker labels

### Diarization Mode
- Uses whisper.cpp diarization
- Identifies speakers in mixed audio
- Timestamps speaker changes

## File Monitoring

### Automatic Processing
The file watcher monitors `~/Downloads` for supported audio files:
- `.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.caf`
- `.mp4`, `.mov`, `.opus`, `.ogg`, `.webm`

### LaunchAgent Setup (macOS)

```bash
# Copy plist file
cp examples/com.jasonvallery.voicenote-ingest.plist ~/Library/LaunchAgents/

# Edit paths in plist file
vi ~/Library/LaunchAgents/com.jasonvallery.voicenote-ingest.plist

# Load and start
launchctl load ~/Library/LaunchAgents/com.jasonvallery.voicenote-ingest.plist
launchctl start com.jasonvallery.voicenote-ingest
```

## Deduplication

The system uses dual-hash deduplication:

- **File Hash (SHA256)**: Raw file bytes
- **Content Hash (SHA256)**: Decoded 16kHz mono PCM

This detects duplicates even across different file formats (e.g., same audio in MP3 and M4A).

## Error Handling

### Crash Safety
- Lock files prevent concurrent processing
- Original files remain untouched until success
- Atomic operations for all file moves
- State machine allows resuming interrupted processing

### Recovery
```bash
# Check for stuck processing
ls VoiceNotes/state/*.lock

# Manual cleanup if needed
rm VoiceNotes/state/*.lock

# Verify and rebuild if necessary
ingest rebuild-index
```

## Dependencies

### Required
- Python 3.8+
- FFmpeg (audio processing)
- whisper.cpp (transcription)

### Python Packages
- click (CLI framework)
- PyYAML (configuration)
- watchdog (file monitoring)
- pydub (audio utilities)

### Optional
- macOS mdls (metadata extraction)

## Configuration

### Audio Settings
```yaml
audio:
  default_profile: "auto"
  normalization:
    target_level: -16    # dB LUFS
    sample_rate: 16000   # Hz
```

### Transcription Settings
```yaml
transcription:
  model: "large-v3"
  language: "auto"
  diarization:
    auto_enable_threshold: 120  # seconds
```

### Note Generation
```yaml
notes:
  template: "templates/note.md"
  filename_pattern: "{date}__{title_slug}__{hash8}.md"
```

## Examples

### Basic Voice Memo
```bash
# Just drop file in Downloads, or:
ingest process ~/Downloads/memo.m4a
```

### Conference Call
```bash
ingest process call.m4a --call --speakers "Me,Client" --tags "business,project-x"
```

### Meeting with Preparation
```yaml
# meeting.yml
title: "Sprint Planning"
tags: [meeting, sprint, planning]
speaker_names: [Alice, Bob, Charlie]
use_diarization: true
location: "conference room"
```

## Troubleshooting

### Audio Processing Issues
- Check FFmpeg installation: `ffmpeg -version`
- Verify supported formats: `ffmpeg -formats`
- Check audio file integrity: `ffmpeg -i file.m4a -f null -`

### Transcription Issues
- Check whisper.cpp: `whisper --help`
- Verify model: `ls ~/.whisper/ggml-*.bin`
- Test transcription: `whisper -f audio.wav`

### File Monitoring Issues
- Check Downloads path permissions
- Verify watchdog installation: `python3 -c "import watchdog"`
- Check LaunchAgent status: `launchctl list | grep voicenote`

## Performance

### Processing Times
- Audio normalization: ~0.1x realtime
- Transcription: ~0.3-0.5x realtime (depends on model/hardware)
- Note generation: ~1-2 seconds

### Storage Usage
- Original audio preserved
- Normalized WAV ~10-20% of original size
- Transcripts minimal (<1KB per minute)

### Optimization
- Use smaller whisper model for faster processing
- Enable compression for old files
- Archive completed recordings periodically

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review existing GitHub issues
3. Create a new issue with details and logs