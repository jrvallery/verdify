#!/usr/bin/env bash
# dump.sh v2.1 — LLM-ready project dumper (git-aware with filesystem fallback)
# Features:
# - Falls back to filesystem scan if PATH is outside any git repo
# - Respects .gitignore when inside a repo
# - Skips binaries; optional size/line truncation
# - Extension & glob excludes, include-only globs, common vendor dir excludes
# - Stable sorting (path|mtime|size)
# - Emits an LLM prompt + scope + optional tree + git metadata + delimited files
# - Dry-run mode; portable realpath/stat; optional context injection
#
# NOTE: Requires bash >= 4 for 'mapfile'. On macOS, consider installing newer bash or
#       replace the 'mapfile' section with a while-read loop reading from a file.

set -Eeuo pipefail
IFS=$'\n\t'

# -------------------------------
# Defaults
# -------------------------------
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTFILE="project_dump_${TIMESTAMP}.md"
MAX_BYTES=0          # 0 = unlimited
MAX_LINES=0          # 0 = unlimited
INCLUDE_TREE=0
INCLUDE_GIT_META=1
FOLLOW_SYMLINKS=0
DRY_RUN=0
SORT_MODE="path"     # path|mtime|size
PERSONA_PRESET="code_review"  # code_review|security|perf|bug_hunt
USE_VENDOR_EXCLUDES=1
# Common bulky dirs we usually don't want in an LLM context
DEFAULT_VENDOR_EXCLUDES=( ".git/" "node_modules/" "dist/" "build/" "target/" "__pycache__/" ".venv/" ".direnv/"
                          ".tox/" ".mypy_cache/" ".pytest_cache/" ".terraform/" ".gradle/" ".next/" ".cache/" "coverage/" "vendor/" )

# Collected filters
declare -a EXCL_EXTS=()    # .md .txt ...
declare -a EXCL_GLOBS=()   # '*/generated/*' '*/node_modules/*' ...
declare -a INCL_GLOBS=()   # optional whitelisting
declare -a EXTRA_CONTEXT_FILES=()
EXTRA_CONTEXT_TEXT=""

# -------------------------------
# Utilities (portable paths/stat)
# -------------------------------
warn() { echo "[$(date +%H:%M:%S)] WARN: $*" >&2; }
note() { echo "[$(date +%H:%M:%S)] $*" >&2; }
die()  { echo "[$(date +%H:%M:%S)] ERROR: $*" >&2; exit 1; }

realpath_portable() {
  # Works on macOS where readlink -f doesn't exist
  python3 - "$1" <<'PY' 2>/dev/null || echo "$1"
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
}

relpath_portable() {
  # $1=path $2=base
  python3 - "$1" "$2" <<'PY' 2>/dev/null || echo "$1"
import os, sys
print(os.path.relpath(os.path.realpath(sys.argv[1]), os.path.realpath(sys.argv[2])))
PY
}

tolower() {
  # Bash 3 compatible lower-casing
  printf %s "$1" | tr '[:upper:]' '[:lower:]'
}

get_file_size() {
  local f="$1"
  if stat -f %z "$f" >/dev/null 2>&1; then
    stat -f %z "$f"
  else
    stat -c %s "$f"
  fi
}

is_text_file() {
  local f="$1"
  # Prefer 'file' if available; fallback to grep -Iq
  if command -v file >/dev/null 2>&1; then
    file --mime "$f" 2>/dev/null | grep -qv 'charset=binary'
  else
    # grep -Iq: returns success if file seems text
    grep -Iq . "$f"
  fi
}

path_is_within() {
  local p="$1" base="$2"
  [[ -z "$base" ]] && return 1
  p="$(realpath_portable "$p")"
  base="$(realpath_portable "$base")"
  case "$p" in
    "$base"|"$base"/*) return 0 ;;
    *) return 1 ;;
  esac
}

git_root_for_path() {
  # Try resolving repo by the path itself, else by CWD
  local p="$1"
  if git -C "$p" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "$p" rev-parse --show-toplevel 2>/dev/null
    return 0
  fi
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    git rev-parse --show-toplevel 2>/dev/null
    return 0
  fi
  return 1
}

# -------------------------------
# CLI parsing
# -------------------------------
usage() {
  cat <<EOF
Usage: $0 [OPTIONS] [PATH] [excluded_extensions...]

Create a single Markdown file containing:
- An expert LLM prompt, metadata, optional tree, and
- All qualifying text files under PATH (default: .), respecting .gitignore if possible.

Key features:
- Falls back to plain filesystem scanning when PATH is outside any repo.
- Skips binaries; supports size/line truncation; stable sorting.
- Excludes common vendor/build dirs by default (override with --include-vendor).

Options:
  -o, --output FILE           Output file (default: ${OUTFILE})
  -m, --max-bytes N           Truncate any file over N bytes (0=unlimited)
  -n, --max-lines N           Truncate any file over N lines (0=unlimited)
  -x, --exclude-glob GLOB     Exclude glob (can repeat; quote globs)
  -E, --exclude-ext EXT       Exclude extension like .md (can repeat)
  -I, --include-glob GLOB     Only include files that match any of these globs (can repeat)
  -t, --tree                  Include a tree view (scoped to PATH)
  -G, --no-git-meta           Do not include git metadata
  -s, --sort MODE             Sort: path|mtime|size (default: path)
  -L, --follow-symlinks       Follow symlinks
  -V, --include-vendor        Include vendor/build caches (disable default excludes)
  -P, --persona NAME          Prompt preset: code_review|security|perf|bug_hunt
  -c, --context-file FILE     Add a context file (can repeat; included before code)
  -C, --context TEXT          Inline context text (quoted)
  -d, --dry-run               List which files would be included and exit
  -h, --help                  Show this help

Positional:
  PATH                        Directory or file to dump (default: .)
  excluded_extensions         Legacy support for .ext arguments

Examples:
  $0
  $0 src -E .md -x '*/generated/*' -m 200000 -n 2000 -t
  $0 /etc/nginx --no-git-meta               # outside a repo -> filesystem scan
EOF
}

PATH_ARG="."
while (( "$#" )); do
  case "$1" in
    -o|--output) OUTFILE="$2"; shift 2 ;;
    -m|--max-bytes) MAX_BYTES="${2:-0}"; shift 2 ;;
    -n|--max-lines) MAX_LINES="${2:-0}"; shift 2 ;;
    -x|--exclude-glob) EXCL_GLOBS+=("$2"); shift 2 ;;
    -E|--exclude-ext) EXCL_EXTS+=("$2"); shift 2 ;;
    -I|--include-glob) INCL_GLOBS+=("$2"); shift 2 ;;
    -t|--tree) INCLUDE_TREE=1; shift ;;
    -G|--no-git-meta) INCLUDE_GIT_META=0; shift ;;
    -s|--sort) SORT_MODE="$2"; shift 2 ;;
    -L|--follow-symlinks) FOLLOW_SYMLINKS=1; shift ;;
    -V|--include-vendor) USE_VENDOR_EXCLUDES=0; shift ;;
    -P|--persona) PERSONA_PRESET="$2"; shift 2 ;;
    -c|--context-file) EXTRA_CONTEXT_FILES+=("$2"); shift 2 ;;
    -C|--context) EXTRA_CONTEXT_TEXT="${EXTRA_CONTEXT_TEXT}"$'\n'"$2"; shift 2 ;;
    -d|--dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*)
      die "Unknown option: $1 (use --help)"
      ;;
    *)
      # First non-flag is PATH; others treated as legacy excluded extensions
      if [[ "$PATH_ARG" == "." && -e "$1" ]]; then
        PATH_ARG="$1"
      else
        EXCL_EXTS+=("$1")
      fi
      shift ;;
  esac
done

# Normalize extensions to start with dot & be case-insensitive checks
norm_ext() {
  local e="$1"
  [[ "$e" != .* ]] && e=".$e"
  echo "$e"
}
for i in "${!EXCL_EXTS[@]}"; do EXCL_EXTS[$i]="$(norm_ext "${EXCL_EXTS[$i]}")"; done

# Append default vendor excludes if enabled
if (( USE_VENDOR_EXCLUDES )); then
  for d in "${DEFAULT_VENDOR_EXCLUDES[@]}"; do EXCL_GLOBS+=("*${d}*"); done
fi

# -------------------------------
# File listing (git-aware)
# -------------------------------
ABS_PATH="$(realpath_portable "$PATH_ARG")"
LIST_TMP="$(mktemp)"
trap 'rm -f "$LIST_TMP"' EXIT

list_with_git() {
  local root="$1" sub="$2"
  pushd "$root" >/dev/null
  # Relative path for git ls-files
  local rel
  rel="$(relpath_portable "$sub" "$root")"
  # cached + others, obeying .gitignore
  git ls-files -c -o --exclude-standard -z -- "$rel"
  popd >/dev/null
}

list_with_find() {
  local p="$1"
  local fargs=(-type f)
  (( FOLLOW_SYMLINKS )) && fargs=(-L "${fargs[@]}")
  if [[ -f "$p" ]]; then
    printf '%s\0' "$p"
  else
    # shellcheck disable=SC2016
    find "$p" "${fargs[@]}" -print0
  fi
}

# Decide strategy: if PATH is inside some repo, use git; else filesystem
USE_GIT=0
if root="$(git_root_for_path "$ABS_PATH")"; then
  if path_is_within "$ABS_PATH" "$root"; then
    USE_GIT=1
  fi
fi

if (( USE_GIT )); then
  note "Using git-aware listing under: $root"
  list_with_git "$root" "$ABS_PATH" >"$LIST_TMP"
else
  note "Using filesystem listing (no repo or PATH outside repo)"
  list_with_find "$ABS_PATH" >"$LIST_TMP"
fi

# Materialize to array, respecting nulls
mapfile -d '' FILES <"$LIST_TMP" || true

# -------------------------------
# Filtering and sorting
# -------------------------------
matches_any_glob() {
  local f="$1"; shift
  local g
  for g in "$@"; do
    [[ -n "$g" ]] && [[ "$f" == $g ]] && return 0
  done
  return 1
}

has_excluded_ext() {
  local f="$1" ext
  local lower
  lower="$(tolower "$f")"
  for ext in "${EXCL_EXTS[@]}"; do
    local e
    e="$(tolower "$(norm_ext "$ext")")"
    [[ "$lower" == *"$e" ]] && [[ "$lower" == *"$e" ]] && [[ "$lower" == *"$e" ]] >/dev/null 2>&1
    # Match only if it ends with the extension
    [[ "$lower" == *"$e" ]] && [[ "$lower" == *"$e" ]] # no-op duplicate for readability
    [[ "$lower" == *"$e" ]] && [[ "$lower" == *"$e" ]] # keep simple end-with check
    [[ "$lower" == *"$e" ]] && return 0
  done
  return 1
}

# Apply include globs first (if present), then excludes & basic checks
QUALIFIED=()
for f in "${FILES[@]}"; do
  [[ ! -f "$f" ]] && continue
  # self-exclude (the output we are currently generating)
  [[ "$(realpath_portable "$f")" == "$(realpath_portable "$OUTFILE")" ]] && continue
  # include filter (if provided)
  if (( ${#INCL_GLOBS[@]} > 0 )); then
    matches_any_glob "$f" "${INCL_GLOBS[@]}" || continue
  fi
  # glob excludes
  matches_any_glob "$f" "${EXCL_GLOBS[@]}" && continue
  # extension excludes
  has_excluded_ext "$f" && continue
  # text check
  is_text_file "$f" || continue
  QUALIFIED+=("$f")
done

# Sorting
case "$SORT_MODE" in
  path)
    IFS=$'\n' QUALIFIED=($(printf '%s\n' "${QUALIFIED[@]}" | LC_ALL=C sort)) ;;
  mtime)
    sort_with_mtime() {
      for f in "${QUALIFIED[@]}"; do
        if stat -f %m "$f" >/dev/null 2>&1; then
          printf '%d\t%s\n' "$(stat -f %m "$f")" "$f"
        else
          printf '%d\t%s\n' "$(stat -c %Y "$f")" "$f"
        fi
      done | sort -n | cut -f2-
    }
    mapfile -t QUALIFIED < <(sort_with_mtime)
    ;;
  size)
    sort_with_size() {
      for f in "${QUALIFIED[@]}"; do
        printf '%d\t%s\n' "$(get_file_size "$f")" "$f"
      done | sort -n | cut -f2-
    }
    mapfile -t QUALIFIED < <(sort_with_size)
    ;;
  *)
    die "Unknown sort mode: $SORT_MODE"
    ;;
esac

if (( DRY_RUN )); then
  printf "Would include %d files:\n" "${#QUALIFIED[@]}"
  printf '  %s\n' "${QUALIFIED[@]}"
  exit 0
fi

# -------------------------------
# Prompt presets
# -------------------------------
emit_persona() {
  case "$PERSONA_PRESET" in
    code_review)
      cat <<'TXT'
You are an expert code reviewer with deep knowledge of software engineering, distributed systems, and DevOps best practices. Be meticulous, objective, and prioritize reliability, security, scalability, and maintainability. Analyze from an end‑to‑end systems perspective.
TXT
      ;;
    security)
      cat <<'TXT'
You are a senior application security engineer. Identify vulnerabilities (authN/Z, injection, XSS, deserialization, SSRF, RCE), secrets exposure, supply‑chain risks, misconfigurations, and insecure defaults. Propose least‑privilege and defense‑in‑depth mitigations.
TXT
      ;;
    perf)
      cat <<'TXT'
You are a performance and scalability analyst. Find latency, throughput, memory, allocation, and I/O hotspots; assess concurrency, caching, batching, and data structures. Recommend low‑risk, measurable optimizations.
TXT
      ;;
    bug_hunt)
      cat <<'TXT'
You are a senior debugging specialist. Trace code paths and failure modes, check edge cases and race conditions, validate assumptions, and propose minimal reproduction steps and targeted fixes.
TXT
      ;;
    *) ;;
  esac
}

emit_review_instructions() {
  cat <<'TXT'
Your task:
1) Systematically analyze all code paths and configs in the dump.
2) Identify bugs, risks, and edge cases.
3) Evaluate against best practices (architecture, security, reliability, performance).
4) Incorporate any provided context (infra, goals).
5) Output a prioritized task list in Markdown with:
   - Task Summary
   - What Needs to Change
   - Why (with references if applicable)
   - How to Implement (step‑by‑step, minimal diff)
   Group by category (Bugs, Security, Best Practices, Architecture) and label severity.
If no issues are found, say so and suggest proactive improvements. Avoid speculation beyond the provided code.
TXT
}

emit_tree() {
  local root="$1"
  {
    echo "### Project Tree (partial)"
    if command -v tree >/dev/null 2>&1; then
      (cd "$root" && tree -a -I '.git' -L 4)
    else
      echo "(Install 'tree' for a nicer view. Fallback shown.)"
      (cd "$root" && find . -maxdepth 4 -print | LC_ALL=C sort)
    fi
    echo
  } >>"$OUTFILE"
}

emit_git_meta() {
  local root="$1"
  [[ $INCLUDE_GIT_META -eq 1 ]] || return 0
  if [[ -d "$root/.git" ]]; then
    local branch head remote
    branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
    head="$(git -C "$root" rev-parse HEAD 2>/dev/null || echo 'unknown')"
    remote="$(git -C "$root" remote -v 2>/dev/null | awk 'NR==1{print $2}')"
    {
      echo "### Git Metadata"
      echo "- Repo root: \`$root\`"
      echo "- Branch: \`$branch\`"
      echo "- HEAD: \`$head\`"
      [[ -n "$remote" ]] && echo "- Remote: \`$remote\`"
      echo
    } >>"$OUTFILE"
  fi
}

# -------------------------------
# Emit header (LLM-ready)
# -------------------------------
{
  echo "# Project Dump — $(date)"
  echo
  echo "## LLM Instructions"
  echo
  emit_persona
  echo
  emit_review_instructions
  echo
  echo "## Scope"
  echo "- Requested path: \`$ABS_PATH\`"
  echo "- Files included: ${#QUALIFIED[@]}"
  echo "- Sort: $SORT_MODE"
  echo "- Max bytes per file: ${MAX_BYTES}"
  echo "- Max lines per file: ${MAX_LINES}"
  echo
  if (( ${#EXCL_EXTS[@]} )); then
    echo "- Excluded extensions: ${EXCL_EXTS[*]}"
  fi
  if (( ${#EXCL_GLOBS[@]} )); then
    echo "- Excluded globs: ${EXCL_GLOBS[*]}"
  fi
  if (( ${#INCL_GLOBS[@]} )); then
    echo "- Include‑only globs: ${INCL_GLOBS[*]}"
  fi
  echo
  if (( ${#EXTRA_CONTEXT_FILES[@]} )) || [[ -n "$EXTRA_CONTEXT_TEXT" ]]; then
    echo "## Additional Context"
    for cf in "${EXTRA_CONTEXT_FILES[@]}"; do
      if [[ -f "$cf" ]]; then
        echo ""
        echo "### Context File: \`$cf\`"
        echo '```text'
        cat "$cf"
        echo '```'
      fi
    done
    if [[ -n "$EXTRA_CONTEXT_TEXT" ]]; then
      echo ""
      echo "### Context Notes"
      echo '```text'
      printf "%s\n" "$EXTRA_CONTEXT_TEXT"
      echo '```'
    fi
    echo
  fi
} >"$OUTFILE"

# Tree (scoped to requested path) + git meta (repo root, if any)
ROOT_FOR_META="$ABS_PATH"
if (( USE_GIT )); then ROOT_FOR_META="$root"; fi
if (( INCLUDE_TREE )); then emit_tree "$ABS_PATH"; fi
emit_git_meta "$ROOT_FOR_META"

# -------------------------------
# Emit files
# -------------------------------
files_included=0
files_truncated=0
bytes_written=0

emit_file() {
  local f="$1"
  local sz lines
  sz="$(get_file_size "$f" || echo 0)"
  local truncated=0

  {
    echo
    echo "===== BEGIN FILE: $f ====="
    echo

    if (( MAX_BYTES > 0 )) && (( sz > MAX_BYTES )); then
      truncated=1
      echo "<!-- TRUNCATED: original ${sz} bytes; showing first ${MAX_BYTES} bytes -->"
      head -c "$MAX_BYTES" "$f" | sed 's/^/    /'
    elif (( MAX_LINES > 0 )); then
      # Count lines in a portable way
      lines="$(wc -l <"$f" | tr -d ' ')"
      if (( lines > MAX_LINES )); then
        truncated=1
        echo "<!-- TRUNCATED: original ${lines} lines; showing first ${MAX_LINES} lines -->"
        head -n "$MAX_LINES" "$f" | sed 's/^/    /'
      else
        sed 's/^/    /' "$f"
      fi
    else
      sed 's/^/    /' "$f"
    fi

    echo
    echo "===== END FILE: $f ====="
    echo
  } >>"$OUTFILE"

  # With `set -e`, avoid bare arithmetic as the last command (post-increment can return 1).
  : $((files_included+=1))
  if (( truncated )); then
    : $((files_truncated+=1))
  fi
  return 0
}

for f in "${QUALIFIED[@]}"; do
  emit_file "$f"
done

# Footer summary
{
  echo
  echo "---"
  echo "**Summary:** Included ${files_included} file(s)."
  (( files_truncated > 0 )) && echo "**Note:** ${files_truncated} file(s) were truncated by size/line limits."
  echo
  echo "_Generated by dump.sh v2.1_"
} >>"$OUTFILE"

echo "Dump complete: ${OUTFILE} (${files_included} files included)"
