# Voice Note Ingestion Pipeline

A production-ready voice note ingestion system that processes audio files into searchable, organized notes with comprehensive metadata and deduplication.

## Features

### 🎯 Core Capabilities
- **Deterministic Processing**: Same content always produces identical results
- **Dual-Hash Deduplication**: File hash + content hash for cross-format duplicate detection
- **Crash-Safe Pipeline**: Atomic operations with rollback on failure
- **Zero-Friction Workflow**: Drop file → complete note appears automatically
- **Multi-Speaker Support**: Split-channel processing and diarization
- **Rich Metadata**: Full provenance and technical details preserved

### 🎵 Audio Processing
- **Adaptive Profiles**: `auto`, `call`, `wind`, `wide` with specific filter chains
- **Format Support**: m4a, mp3, wav, aac, flac, caf, mp4, mov, opus
- **Auto-Detection**: Sample rate, channels, bitrate analysis
- **Filter Chain**: `highpass → lowpass → dynaudnorm → limiter`
- **Split-Channel**: L/R extraction for dual-mic recordings

### 📝 Note Generation
- **Structured Notes**: Template-based creation with comprehensive YAML frontmatter
- **Content Extraction**: Summary, key points, decisions, action items
- **Obsidian Compatible**: Native vault organization with proper linking
- **Searchable Index**: Master table with dual-hash deduplication

### 🔄 Pipeline States
`queued → staging → hashing → dedupe-check → transcode → transcribe → assemble-note → index-update → finalize → done`

## Quick Start

### 1. Prerequisites

Install required tools:
```bash
# macOS with Homebrew
brew install ffmpeg whisper-cpp

# Or compile whisper.cpp from source
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
make

# Download models
./models/download-ggml-model.sh base.en
```

### 2. Installation

```bash
# Clone the repository
cd Scripts/ingest

# Install the package
pip install -e .

# Or use uv (recommended)
uv pip install -e .
```

### 3. Configuration

The system uses `VoiceNotes/config.yml` for configuration. Default settings work for most users, but you can customize:

```yaml
processing:
  default_profile: "auto"
  sample_rate: 16000
  transcription:
    model: "base.en"
    language: "en"

watcher:
  watch_path: "~/Downloads"
  debounce_seconds: 2
```

### 4. First Run

```bash
# Process a single file
ingest process ~/Downloads/meeting.m4a

# Start watching Downloads folder
ingest watch

# Check system status
ingest status
```

## CLI Commands

### Core Commands

```bash
# Process single file
ingest process <file> [--profile auto|call|wind|wide] [--split-channels] [--tags "meeting,project"]

# Auto-watch Downloads folder
ingest watch [--daemon] [--once]

# Reprocess with different settings
ingest reprocess --sha <hash> [--profile call] [--split-channels]

# Verify processed artifacts
ingest verify --sha <hash> [--fix]

# Rebuild master index
ingest rebuild-index [--force]

# List processed notes
ingest list-notes [--tags "meeting"] [--participants "john"] [--limit 10]

# Show system status
ingest status
```

### Processing Options

- `--profile`: Audio processing profile (`auto`, `call`, `wind`, `wide`)
- `--split-channels`: Process L/R channels separately for dual-mic recordings
- `--is-call`: Mark as phone/video call for optimal processing
- `--tags`: Comma-separated tags for categorization
- `--participants`: Comma-separated participant names
- `--speaker-labels`: JSON mapping for speaker identification
- `--force`: Force reprocessing even if duplicate detected

## Context Injection

### Sidecar YAML Files

Create `filename.yml` alongside `filename.m4a`:

```yaml
participants:
  - name: "John Doe"
    role: "host"
  - name: "Jane Smith"
    role: "guest"

tags: ["meeting", "project-alpha", "strategy"]
profile: "call"
split_channels: false
is_call: true

speaker_labels:
  left: "John Doe"
  right: "Jane Smith"

title: "Project Alpha Strategy Meeting"
location: "Conference Room A"
project: "Alpha Initiative"
meeting_type: "planning"
```

### Filename Flags

Embed context in filenames:

```
[SPLIT][CALL][TAGS:#meeting,#project][PROFILE:call] Strategy Discussion.m4a
[SPEAKERS:John:host,Jane:guest] Team Standup.m4a
```

## Vault Structure

```
VoiceNotes/
├── _index.md              # Human-readable master index
├── _index.json            # Machine-readable index
├── config.yml             # Configuration
├── templates/
│   └── note.md            # Note template
├── audio/
│   └── <sha256>/          # Processed audio files (by PCM hash)
├── transcripts/
│   └── <sha256>/          # JSON transcripts
├── notes/                 # Generated markdown notes
├── logs/                  # Processing logs
├── state/                 # Job state and locks
└── staging/               # Temporary processing area
```

## LaunchAgent Setup (macOS)

For automatic background processing:

```bash
# Copy LaunchAgent plist
cp Scripts/com.jasonvallery.voicenote-ingest.plist ~/Library/LaunchAgents/

# Edit paths in the plist file to match your setup
nano ~/Library/LaunchAgents/com.jasonvallery.voicenote-ingest.plist

# Load the service
launchctl load ~/Library/LaunchAgents/com.jasonvallery.voicenote-ingest.plist

# Start the service
launchctl start com.jasonvallery.voicenote-ingest
```

## Advanced Features

### Deduplication System

The system uses dual-hash deduplication:

- **File Hash (`sha256_file`)**: Hash of raw file for exact file matching
- **Content Hash (`sha256_pcm`)**: Hash of decoded 16kHz mono PCM for content-based deduplication

Primary deduplication key is `sha256_pcm`, enabling cross-format duplicate detection.

### Split-Channel Processing

For dual-mic recordings:

```bash
# Process left/right channels separately
ingest process recording.m4a --split-channels

# With speaker labels
ingest process recording.m4a --split-channels --speaker-labels '{"left":"Host","right":"Guest"}'
```

### Multi-Speaker Diarization

For single-track multi-speaker content:

```bash
# Enable diarization (automatic with multiple participants)
ingest process meeting.m4a --participants "Alice,Bob,Charlie"
```

### Error Recovery

The system is crash-safe and can recover from interruptions:

```bash
# Clean up stale locks
ingest verify --sha <hash> --fix

# Reprocess interrupted jobs
ingest status  # Check for stuck jobs
ingest reprocess --sha <hash>
```

## Troubleshooting

### Common Issues

1. **Missing Tools**
   ```bash
   ingest status  # Check tool availability
   brew install ffmpeg whisper-cpp
   ```

2. **Permission Errors**
   ```bash
   chmod +x /usr/local/bin/ingest
   ```

3. **LaunchAgent Not Starting**
   ```bash
   # Check logs
   tail -f ~/VoiceNotes/logs/launchd.err
   
   # Reload service
   launchctl unload ~/Library/LaunchAgents/com.jasonvallery.voicenote-ingest.plist
   launchctl load ~/Library/LaunchAgents/com.jasonvallery.voicenote-ingest.plist
   ```

4. **Processing Stuck**
   ```bash
   # Check active jobs
   ingest status
   
   # Clean up stale locks
   rm ~/VoiceNotes/state/locks/*.lock
   ```

### Debug Mode

Enable verbose logging:

```bash
ingest --verbose process file.m4a
ingest --verbose watch
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

See LICENSE file for details.

## Roadmap

- [ ] Web dashboard for monitoring and management
- [ ] Real-time transcription with streaming
- [ ] AI-powered summary and insights
- [ ] Integration with calendar systems
- [ ] Mobile app for voice note capture
- [ ] Team collaboration features