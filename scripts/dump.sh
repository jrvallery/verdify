#!/usr/bin/env bash
set -euo pipefail

# dump2.sh — Enhanced file bundling tool for code review and sharing
# Version: 2.0
# Author: Enhanced for home-infra project
# Last Modified: August 17, 2025
#
# DESCRIPTION:
#   Merges multiple text files into a single structured dump file for easy sharing,
#   code review, or backup purposes. Supports both directory scanning and explicit
#   file list modes with intelligent filtering and progress tracking.
#
# KEY FEATURES:
#   - Directory scanning with Git-aware file discovery
#   - Explicit file list mode for targeted bundling
#   - Automatic binary file detection and exclusion
#   - File size limits and extension filtering
#   - Progress reporting for large operations
#   - Portable across macOS (BSD) and Linux (GNU) systems
#
# MODES OF OPERATION:
#   1. Directory Mode (-p): Scans a directory tree using Git or find
#   2. File List Mode (-f): Processes an explicit list of files
#   3. Auto Mode (default): Scans current directory with Git awareness
#
# OUTPUT FORMAT:
#   Creates a structured text file with:
#   - Header with timestamp, path/source, and filtering info
#   - Each file delimited with clear BEGIN/END markers
#   - 4-space indentation for all file content
#   - Summary of files included/skipped
#
# ENHANCED FEATURES (v2):
#   - File list support for targeted bundling
#   - Improved error handling and validation
#   - Better progress reporting
#   - Enhanced documentation and examples

usage() {
  cat <<'USAGE'
Usage: dump2.sh [-p PATH] [-f FILE_LIST] [-o OUTPUT] [--progress] [--no-git] [--max-bytes N] [--ext-exclude EXT ...]

MODES:
  Directory Mode:  Scans directory tree for files (default: current directory)
  File List Mode:  Processes explicit list of files from a text file

OPTIONS:
  -p, --path PATH          Root path to scan for files (default: current directory)
                          Ignored when using --file-list mode

  -f, --file-list FILE     Text file containing list of files to bundle (one per line)
                          Lines starting with # are treated as comments
                          Relative paths are resolved from current working directory
                          Takes precedence over --path option

  -o, --output FILE        Output bundle file (default: project_dump_YYYYMMDD_HHMMSS.txt)
                          Will be excluded from bundling to prevent recursion

      --no-git             Force use of find instead of git for file discovery
                          Useful for non-git directories or when git is unavailable

      --progress           Display progress counter during processing
                          Shows: Processed: N | Included: N | Skipped: N

      --max-bytes N        Skip files larger than N bytes (0 = unlimited)
                          Useful for avoiding large binary or generated files

      --ext-exclude EXT    Exclude files with extension EXT (case-insensitive)
                          Can be specified multiple times
                          Example: --ext-exclude .jpg --ext-exclude .png

  -h, --help               Show this help text and exit

EXAMPLES:
  # Bundle current directory using git file discovery
  ./dump2.sh

  # Bundle specific directory with progress tracking
  ./dump2.sh -p backend/app --progress

  # Bundle from explicit file list (recommended for targeted bundling)
  ./dump2.sh -f my_project_files.txt -o project_bundle.txt

  # Bundle with size limits and exclusions
  ./dump2.sh -p src --max-bytes 1000000 --ext-exclude .min.js --ext-exclude .map

  # Force find-based scanning (no git)
  ./dump2.sh -p legacy_code --no-git --progress

FILE LIST FORMAT:
  When using --file-list mode, create a text file with one file path per line:

  # Project core files
  src/main.py
  src/utils.py
  config/settings.yaml
  docs/README.md

  # Lines starting with # are comments (ignored)
  # Relative paths are resolved from current working directory
  # Missing files generate warnings but don't stop processing

OUTPUT FORMAT:
  The bundle file contains:
  - Header with timestamp and configuration
  - Each file wrapped in clear delimiters:
    ===== BEGIN FILE: /absolute/path/to/file =====
        [file contents with 4-space indentation]
    ===== END FILE: /absolute/path/to/file =====
  - Summary of processing results

FILTERING RULES:
  Files are automatically excluded if they:
  - Are binary (contain null bytes)
  - Exceed --max-bytes limit
  - Have excluded extensions
  - Are the output file itself
  - Don't exist (file list mode only)
USAGE
}

# Defaults
PATH_ROOT="."
OUTPUT_FILE="project_dump_$(date +%Y%m%d_%H%M%S).txt"
USE_GIT=1
SHOW_PROGRESS=0
MAX_BYTES=0
EXCLUDE_EXTS=()
FILE_LIST=""

# Parse args
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -p|--path) PATH_ROOT="${2:-.}"; shift 2 ;;
    -f|--file-list) FILE_LIST="${2:-}"; shift 2 ;;
    -o|--output) OUTPUT_FILE="${2:-}"; shift 2 ;;
    --no-git) USE_GIT=0; shift ;;
    --progress) SHOW_PROGRESS=1; shift ;;
    --max-bytes) MAX_BYTES="${2:-0}"; shift 2 ;;
    --ext-exclude) EXCLUDE_EXTS+=("${2:-}"); shift 2 ;;
    --) shift; break ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *)
      # If a bare positional is given and path is default, treat it as path; otherwise as ext
      if [ "$PATH_ROOT" = "." ]; then PATH_ROOT="$1"; else EXCLUDE_EXTS+=("$1"); fi
      shift
      ;;
  esac
done

# Normalize path (strip trailing slash)
PATH_ROOT="${PATH_ROOT%/}"

# Normalize extensions: lowercase + leading dot
norm_ext() {
  ext="$1"
  ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"
  case "$ext" in
    .*) printf '%s' "$ext" ;;
    *)  printf '.%s' "$ext" ;;
  esac
}
if [ "${#EXCLUDE_EXTS[@]}" -gt 0 ] 2>/dev/null; then
  i=0
  for e in "${EXCLUDE_EXTS[@]}"; do
    EXCLUDE_EXTS[$i]="$(norm_ext "$e")"
    i=$((i+1))
  done
fi

# Resolve absolute path for PATH_ROOT
abs_path() {
  local target="$1"
  if [ -d "$target" ]; then
    (cd "$target" && pwd -P)
  else
    (cd "$(dirname "$target")" && printf '%s/%s\n' "$(pwd -P)" "$(basename "$target")")
  fi
}
ABS_PATH_ROOT="$(abs_path "$PATH_ROOT")"

# Output header
{
  echo "Project Dump - $(date)"
  if [ -n "$FILE_LIST" ]; then
    echo "Source: File list ($FILE_LIST)"
  else
    echo "Path: $PATH_ROOT"
  fi
  if [ "${#EXCLUDE_EXTS[@]}" -gt 0 ] 2>/dev/null; then
    echo "Excluded extensions: ${EXCLUDE_EXTS[*]}"
  else
    echo "Excluded extensions: (none)"
  fi
  if [ "$MAX_BYTES" -gt 0 ] 2>/dev/null; then
    echo "Max file size: ${MAX_BYTES} bytes"
  fi
  echo "Generated by: dump2.sh v2.0 (enhanced with file list support)"
  echo
} > "$OUTPUT_FILE"

# Text/binary detection (portable across macOS/Linux)
# Returns 0 for text files, 1 for binary files
is_text_file() {
  local f="$1"
  # Heuristic: grep returns success for likely text; fails for binary (NULs)
  LC_ALL=C grep -Iq . "$f" 2>/dev/null
}

# Extension filter: returns 0 if file has an excluded extension
has_excluded_ext() {
  local f="$1"
  local name lc
  name="$(basename -- "$f" 2>/dev/null || basename "$f")"
  lc="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
  if [ "${#EXCLUDE_EXTS[@]}" -gt 0 ] 2>/dev/null; then
    for ext in "${EXCLUDE_EXTS[@]}"; do
      case "$lc" in
        *"$ext") return 0 ;;
      esac
    done
  fi
  return 1
}

# Get file size in bytes (portable across macOS BSD stat and Linux GNU stat)
file_size_bytes() {
  local f="$1"
  if stat -f%z "$f" >/dev/null 2>&1; then
    # macOS/BSD stat
    stat -f%z -- "$f"
  else
    # Linux/GNU stat
    stat -c%s -- "$f"
  fi
}

# Collect list to a temp file as NUL-delimited absolute paths
TMP_LIST="$(mktemp -t dump_list.XXXXXX)"
trap 'rm -f "$TMP_LIST"' EXIT

# Git-based file discovery: finds files tracked by git within a specific path
add_git_files() {
  local path="$1"  # absolute path to requested root
  # Check if within a git work tree (at or under)
  if ! git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 1
  fi
  local top abs rel
  top="$(git -C "$path" rev-parse --show-toplevel 2>/dev/null)" || return 1
  abs="$(abs_path "$path")"
  case "$abs" in
    "$top") rel="" ;;
    *)      rel="${abs#"$top"/}" ;;
  esac

  if [ -n "$rel" ]; then
    # Limit to subpath `rel` within repo; NUL-safe while loop (no awk RS hacks)
    git -C "$top" ls-files -c -o --exclude-standard -z -- "$rel" \
      | while IFS= read -r -d '' p; do
          printf '%s\0' "$top/$p"
        done >> "$TMP_LIST"
  else
    git -C "$top" ls-files -c -o --exclude-standard -z \
      | while IFS= read -r -d '' p; do
          printf '%s\0' "$top/$p"
        done >> "$TMP_LIST"
  fi
  return 0
}

# Find-based file discovery: recursively finds all files, excluding .git directories
add_find_files() {
  local path="$1"
  # Exclude .git directories; write NUL-delimited absolute paths
  find "$path" -type d -name .git -prune -o -type f -print0 >> "$TMP_LIST"
}

# File list processing: reads explicit file list and validates each entry
add_file_list() {
  local file_list="$1"
  if [ ! -f "$file_list" ]; then
    echo "Error: File list '$file_list' not found" >&2
    return 1
  fi

  echo "Processing file list: $file_list" >&2
  local line_count=0
  local found_count=0

  # Read each line from the file list and convert to absolute path
  while IFS= read -r line || [ -n "$line" ]; do
    line_count=$((line_count + 1))

    # Skip empty lines and comments
    case "$line" in
      ''|'#'*) continue ;;
    esac

    # Convert to absolute path if it exists
    if [ -f "$line" ]; then
      abs_file="$(abs_path "$line")"
      printf '%s\0' "$abs_file" >> "$TMP_LIST"
      found_count=$((found_count + 1))
    else
      echo "Warning: File not found (line $line_count): $line" >&2
    fi
  done < "$file_list"

  echo "File list processed: $found_count files found from $line_count lines" >&2
}

# Choose collection strategy
if [ -n "$FILE_LIST" ]; then
  add_file_list "$FILE_LIST"
elif [ "$USE_GIT" -eq 1 ]; then
  if ! add_git_files "$ABS_PATH_ROOT"; then
    add_find_files "$ABS_PATH_ROOT"
  fi
else
  add_find_files "$ABS_PATH_ROOT"
fi

# Process the list
files_included=0
files_skipped=0
processed=0

# Absolute path of the output file to avoid self-inclusion
ABS_OUTPUT="$(abs_path "$OUTPUT_FILE")"

# Read NUL-delimited absolute paths from TMP_LIST
while IFS= read -r -d '' f; do
  processed=$((processed+1))

  # Basic guards
  if [ ! -f "$f" ]; then
    files_skipped=$((files_skipped+1))
    continue
  fi
  if [ "$f" = "$ABS_OUTPUT" ]; then
    files_skipped=$((files_skipped+1))
    continue
  fi

  # Extension excludes
  if has_excluded_ext "$f"; then
    files_skipped=$((files_skipped+1))
    continue
  fi

  # Size cap
  if [ "$MAX_BYTES" -gt 0 ]; then
    sz="$(file_size_bytes "$f" 2>/dev/null || echo 0)"
    if [ "$sz" -gt "$MAX_BYTES" ]; then
      files_skipped=$((files_skipped+1))
      continue
    fi
  fi

  # Text/binary check
  if ! is_text_file "$f"; then
    files_skipped=$((files_skipped+1))
    continue
  fi

  # Append to output (BSD sed doesn't support `--`)
  {
    printf '===== BEGIN FILE: %s =====\n' "$f"
    sed 's/^/    /' "$f"
    printf '\n===== END FILE: %s =====\n\n' "$f"
  } >> "$OUTPUT_FILE"

  files_included=$((files_included+1))

  if [ "$SHOW_PROGRESS" -eq 1 ] && [ $((processed % 50)) -eq 0 ]; then
    printf '\rProcessed: %d | Included: %d | Skipped: %d' "$processed" "$files_included" "$files_skipped" >&2
  fi
done < "$TMP_LIST"

if [ "$SHOW_PROGRESS" -eq 1 ]; then
  printf '\rProcessed: %d | Included: %d | Skipped: %d\n' "$processed" "$files_included" "$files_skipped" >&2
fi

# If no files, note it in the output (so you know the script ran)
if [ "$files_included" -eq 0 ]; then
  echo "No qualifying files found." >> "$OUTPUT_FILE"
  echo
  echo "===== PROCESSING SUMMARY ====="
  echo "No files were included in the bundle."
  if [ -n "$FILE_LIST" ]; then
    echo "Check that the file list '$FILE_LIST' contains valid file paths."
  else
    echo "Check the path '$PATH_ROOT' and filtering options."
  fi
else
  # Add summary to output file
  {
    echo
    echo "===== BUNDLE SUMMARY ====="
    echo "Files included: $files_included"
    echo "Files skipped: $files_skipped"
    echo "Total processed: $processed"
    if [ -n "$FILE_LIST" ]; then
      echo "Source: File list ($FILE_LIST)"
    else
      echo "Source: Directory scan ($PATH_ROOT)"
    fi
    echo "Bundle generated: $(date)"
  } >> "$OUTPUT_FILE"
fi

echo "Dump complete: $OUTPUT_FILE (${files_included} files included, ${files_skipped} skipped)"

# Provide helpful next steps
if [ "$files_included" -gt 0 ]; then
  echo
  echo "Next steps:"
  echo "  - Review: cat $OUTPUT_FILE | head -50"
  echo "  - Size: wc -l $OUTPUT_FILE"
  if [ -n "$FILE_LIST" ]; then
    echo "  - Files: grep 'BEGIN FILE:' $OUTPUT_FILE | wc -l"
  fi
fi
