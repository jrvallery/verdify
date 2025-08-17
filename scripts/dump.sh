#!/usr/bin/env bash
set -euo pipefail

# dump.sh — Merge a set of text files into one shareable dump for code review.
# - Handles nested/parent Git repos (uses `git -C` and restricts to the given path).
# - Falls back to `find` when --no-git or when the path isn't inside a Git work tree.
# - Portable on macOS (BSD utils) and Linux (GNU utils).

usage() {
  cat <<'USAGE'
Usage: dump.sh [-p PATH] [-o OUTPUT] [--progress] [--no-git] [--max-bytes N] [--ext-exclude EXT ...]
Options:
  -p, --path PATH          Root path to scan (default: .)
  -o, --output FILE        Output file (default: project_dump_YYYYMMDD_HHMMSS.txt)
      --no-git             Do not use git; always use find-based scanning
      --progress           Print progress to stderr periodically
      --max-bytes N        Skip files larger than N bytes (0 = unlimited)
      --ext-exclude EXT    Exclude files with extension EXT (repeatable), e.g. --ext-exclude .md
  -h, --help               Show this help

Examples:
  ./dump.sh
  ./dump.sh -p backend/app --progress
  ./dump.sh -p backend/app --no-git --progress -o app_dump.txt
USAGE
}

# Defaults
PATH_ROOT="."
OUTPUT_FILE="project_dump_$(date +%Y%m%d_%H%M%S).txt"
USE_GIT=1
SHOW_PROGRESS=0
MAX_BYTES=0
EXCLUDE_EXTS=()

# Parse args
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -p|--path) PATH_ROOT="${2:-.}"; shift 2 ;;
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
  echo "Path: $PATH_ROOT"
  if [ "${#EXCLUDE_EXTS[@]}" -gt 0 ] 2>/dev/null; then
    echo "Excluded extensions: ${EXCLUDE_EXTS[*]}"
  else
    echo "Excluded extensions: (none)"
  fi
  if [ "$MAX_BYTES" -gt 0 ] 2>/dev/null; then
    echo "Max file size: ${MAX_BYTES} bytes"
  fi
  echo
} > "$OUTPUT_FILE"

# Text/binary detection (portable)
is_text_file() {
  local f="$1"
  # Heuristic: grep returns success for likely text; fails for binary (NULs)
  LC_ALL=C grep -Iq . "$f" 2>/dev/null
}

# Extension filter: returns 0 if has excluded ext
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

# Stat file size portable (macOS vs GNU)
file_size_bytes() {
  local f="$1"
  if stat -f%z "$f" >/dev/null 2>&1; then
    stat -f%z -- "$f"
  else
    stat -c%s -- "$f"
  fi
}

# Collect list to a temp file as NUL-delimited absolute paths
TMP_LIST="$(mktemp -t dump_list.XXXXXX)"
trap 'rm -f "$TMP_LIST"' EXIT

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

add_find_files() {
  local path="$1"
  # Exclude .git directories; write NUL-delimited absolute paths
  find "$path" -type d -name .git -prune -o -type f -print0 >> "$TMP_LIST"
}

# Choose collection strategy
if [ "$USE_GIT" -eq 1 ]; then
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
fi

echo "Dump complete: $OUTPUT_FILE (${files_included} files included, ${files_skipped} skipped)"
