#!/usr/bin/env bash
set -euo pipefail

# review_bundle.sh — One-shot generator for multi-turn code review bundles
# Version: 1.0  (Aug 21, 2025)
# Location: $REPO_ROOT/scripts/review_bundle.sh
#
# Produces a sequence of copy/paste-ready text files:
#   00_PROMPT_1_REVIEW_CONTEXT.txt    (small intro + instructions + paste order)
#   01_PROMPT_2_CONTEXT_DOCS.txt      (architecture.md, charter.md, mvp.md, requirements.md, vision.md)
#   02_PROMPT_3_MANIFEST.txt          (name-status, numstat totals, concise commit list)
#   03+  PROMPT_4..N_BUNDLE_*.txt     (bundled code/logs, grouped by directory, split by size)
#   ZZ_PROMPT_FINALIZER.txt           (final request for structured review output)
#
# Requirements: bash, git, awk, sed, grep, find, stat
# Optional: script(1) for faithful terminal transcripts
#
# Defaults are safe; override with flags shown in usage().

usage() {
  cat <<'USAGE'
Usage:
  scripts/review_bundle.sh [options]

Options:
  -n, --name NAME           Review name (used in output folder). Default: auto timestamp
  -b, --base REF            Base ref/commit/tag for diff. Default: origin/main
  -t, --head REF            Head ref/commit/tag for diff. Default: HEAD
      --max-bytes N         Max bytes per BUNDLE file (approx). Default: 1000000 (1 MiB)
      --grouping MODE       Grouping: by_dir | manual. Default: by_dir
      --groups-file FILE    When --grouping=manual, a text file:
                            group_name: glob1 glob2 ...
      --include-logs        Attempt to collect test/lint/build logs automatically
      --log-cmd "NAME::CMD" Add a custom command to record into logs/NAME.log (repeatable)
      --exclude-ext EXT     Exclude files by extension (repeatable). Defaults include
                            .map .min.js .wasm .lock .png .jpg .jpeg .svg .pdf .zip .gz .7z
                            .pem .key .p12 .sqlite .db .env
      --output-dir DIR      Output directory. Default: .review_bundles/<NAME>/
      --no-color            Disable ANSI color in console messages
  -h, --help                Show help

Examples:
  scripts/review_bundle.sh -n "Q3-sprint2" -b origin/main -t HEAD --include-logs
  scripts/review_bundle.sh --max-bytes 1500000 --exclude-ext .mp4 --exclude-ext .csv
  scripts/review_bundle.sh --grouping manual --groups-file scripts/review_groups.txt
USAGE
}

# ----- Defaults -----
REVIEW_NAME=""
BASE_REF="origin/main"
HEAD_REF="HEAD"
MAX_BYTES=1000000
GROUPING_MODE="by_dir"
GROUPS_FILE=""
INCLUDE_LOGS=0
NO_COLOR=0
OUTPUT_DIR=""
# Default excludes (extensions, case-insensitive compare via lower-casing basename)
EXCLUDE_EXTS=(.map .min.js .wasm .lock .png .jpg .jpeg .svg .pdf .zip .gz .7z .pem .key .p12 .sqlite .db .env)

# Required docs context (always included if present)
REQUIRED_DOCS=(docs/architecture.md docs/charter.md docs/mvp.md docs/requirements.md docs/vision.md)

# Custom log commands
declare -a LOG_CMDS=()

# ----- Parse args -----
while [ $# -gt 0 ]; do
  case "$1" in
    -n|--name) REVIEW_NAME="${2:-}"; shift 2;;
    -b|--base) BASE_REF="${2:-}"; shift 2;;
    -t|--head) HEAD_REF="${2:-}"; shift 2;;
    --max-bytes) MAX_BYTES="${2:-1000000}"; shift 2;;
    --grouping) GROUPING_MODE="${2:-by_dir}"; shift 2;;
    --groups-file) GROUPS_FILE="${2:-}"; shift 2;;
    --include-logs) INCLUDE_LOGS=1; shift;;
    --log-cmd) LOG_CMDS+=("${2:-}"); shift 2;;
    --exclude-ext) EXCLUDE_EXTS+=("${2:-}"); shift 2;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2;;
    --no-color) NO_COLOR=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 2;;
  esac
done

# ----- Color helpers -----
if [ "$NO_COLOR" -eq 0 ] && [ -t 2 ]; then
  BOLD=$'\e[1m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; BLUE=$'\e[34m'; DIM=$'\e[2m'; RESET=$'\e[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; BLUE=""; DIM=""; RESET=""
fi

# ----- Resolve repo root -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

# ----- Utilities -----
abs_path() {
  local target="$1"
  if [ -d "$target" ]; then (cd "$target" && pwd -P); else (cd "$(dirname "$target")" && printf '%s/%s\n' "$(pwd -P)" "$(basename "$target")"); fi
}
file_size_bytes() {
  local f="$1"
  if stat -f%z "$f" >/dev/null 2>&1; then stat -f%z -- "$f"; else stat -c%s -- "$f"; fi
}
# 0=text, 1=binary (heuristic)
is_text_file() { LC_ALL=C grep -Iq . "$1" 2>/dev/null; }
# normalize .ext (lowercase, ensure leading dot)
norm_ext() { local e="$1"; e="$(printf '%s' "$e" | tr '[:upper:]' '[:lower:]')"; case "$e" in .*) printf '%s' "$e";; *) printf '.%s' "$e";; esac; }
# check extension exclusion (basename, lowercase contains ext at end)
# Extension filter: returns 0 if file has an excluded extension (case-insensitive)
has_excluded_ext() {
  local f="$1"           # <-- assign from the first arg
  local name lc ext
  name="$(basename -- "$f" 2>/dev/null || basename "$f")"
  lc="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
  if [ "${#EXCLUDE_EXTS[@]}" -gt 0 ] 2>/dev/null; then
    for ext in "${EXCLUDE_EXTS[@]}"; do
      ext="$(norm_ext "$ext")"
      case "$lc" in
        *"$ext") return 0 ;;
      esac
    done
  fi
  return 1
}

ensure_dir() { mkdir -p "$1"; }

# record a command to a log file; prefer script(1); fallback to redirection
record_cmd() {
  local name="$1" cmd="$2" logfile="$3"
  if command -v script >/dev/null 2>&1; then
    script --quiet --command "$cmd" "$logfile" >/dev/null 2>&1 || true
  else
    # Fallback: capture stdout+stderr
    bash -lc "$cmd" >"$logfile" 2>&1 || true
  fi
}

# append a file to a bundle with BEGIN/END and 4-space indentation.
# returns via echo the number of bytes appended.
append_file_block() {
  local f="$1" out="$2"
  local tmp="$(mktemp -t rb_append.XXXXXX)"
  {
    printf '===== BEGIN FILE: %s =====\n' "$f"
    sed 's/^/    /' "$f"
    printf '\n===== END FILE: %s =====\n\n' "$f"
  } > "$tmp"
  cat "$tmp" >> "$out"
  local sz
  sz="$(file_size_bytes "$tmp" 2>/dev/null || echo 0)"
  rm -f "$tmp"
  echo "$sz"
}

# ----- Initialize -----
if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: $REPO_ROOT is not a git repository." >&2; exit 3
fi
git -C "$REPO_ROOT" rev-parse --verify "$BASE_REF" >/dev/null 2>&1 || { echo "Error: base ref '$BASE_REF' not found"; exit 3; }
git -C "$REPO_ROOT" rev-parse --verify "$HEAD_REF" >/dev/null 2>&1 || { echo "Error: head ref '$HEAD_REF' not found"; exit 3; }

if [ -z "$REVIEW_NAME" ]; then REVIEW_NAME="$(date +%Y%m%d_%H%M%S)"; fi
if [ -z "$OUTPUT_DIR" ]; then OUTPUT_DIR="$REPO_ROOT/.review_bundles/$REVIEW_NAME"; fi
ensure_dir "$OUTPUT_DIR"

# normalize excludes
for i in "${!EXCLUDE_EXTS[@]}"; do EXCLUDE_EXTS[$i]="$(norm_ext "${EXCLUDE_EXTS[$i]}")"; done

echo "${BOLD}review_bundle.sh${RESET} — generating bundle into ${BLUE}$OUTPUT_DIR${RESET}"
echo "Range: ${GREEN}${BASE_REF}${RESET}..${GREEN}${HEAD_REF}${RESET}   Grouping: ${GREEN}${GROUPING_MODE}${RESET}   Max per bundle: ${GREEN}${MAX_BYTES} bytes${RESET}"

# ----- Collect facts -----
MANIFEST_NS="$OUTPUT_DIR/_manifest_name_status.txt"
MANIFEST_NUM="$OUTPUT_DIR/_manifest_numstat.txt"
COMMITS_TXT="$OUTPUT_DIR/_commits.txt"

# name-status with rename detection; see git-diff docs
git -C "$REPO_ROOT" diff --name-status --find-renames --diff-filter=ACDMRTUXB "$BASE_REF..$HEAD_REF" > "$MANIFEST_NS"
# line deltas
git -C "$REPO_ROOT" diff --numstat --find-renames "$BASE_REF..$HEAD_REF" > "$MANIFEST_NUM"
# concise commit one-liners
git -C "$REPO_ROOT" log --pretty=format:'%h %ad %an %s' --date=iso "$BASE_REF..$HEAD_REF" > "$COMMITS_TXT" || true

# derive changed file list (final path column from name-status; handle renames)
CHANGED_LIST="$OUTPUT_DIR/_changed_files.txt"
awk '{print $NF}' "$MANIFEST_NS" | sort -u > "$CHANGED_LIST"

# filter to text, exclude by extension, and ensure existence
FILTERED_LIST="$OUTPUT_DIR/_filtered_files.txt"
: > "$FILTERED_LIST"
while IFS= read -r rel; do
  [ -z "$rel" ] && continue
  f="$REPO_ROOT/$rel"
  [ -f "$f" ] || continue
  if has_excluded_ext "$f"; then continue; fi
  if ! is_text_file "$f"; then continue; fi
  printf '%s\n' "$rel" >> "$FILTERED_LIST"
done < "$CHANGED_LIST"

# Include required docs context (always) if present & text
CONTEXT_DOCS=()
for d in "${REQUIRED_DOCS[@]}"; do
  if [ -f "$REPO_ROOT/$d" ] && is_text_file "$REPO_ROOT/$d"; then
    CONTEXT_DOCS+=("$d")
  else
    echo "${YELLOW}Warning:${RESET} missing or non-text doc: $d" >&2
  fi
done

# ----- Optional logs collection -----
LOG_DIR="$OUTPUT_DIR/logs"
if [ "$INCLUDE_LOGS" -eq 1 ]; then
  ensure_dir "$LOG_DIR"
  # Heuristics: run common tasks if config files exist
  if [ -f "$REPO_ROOT/package.json" ]; then
    record_cmd "npm:lint" "npm run lint -s" "$LOG_DIR/lint.log"
    record_cmd "npm:build" "npm run build -s" "$LOG_DIR/build.log"
    record_cmd "npm:test" "npm test -s" "$LOG_DIR/test.log"
  fi
  if [ -f "$REPO_ROOT/pyproject.toml" ] || [ -f "$REPO_ROOT/requirements.txt" ]; then
    record_cmd "pytest" "pytest -q" "$LOG_DIR/pytest.log"
  fi
  if command -v go >/dev/null 2>&1 && [ -f "$REPO_ROOT/go.mod" ]; then
    record_cmd "go:test" "go test ./... -v" "$LOG_DIR/go_test.log"
  fi
  if command -v mvn >/dev/null 2>&1 && [ -f "$REPO_ROOT/pom.xml" ]; then
    record_cmd "mvn:test" "mvn -q -DskipTests=false test" "$LOG_DIR/mvn_test.log"
  fi
  # Custom commands
  for spec in "${LOG_CMDS[@]}"; do
    name="${spec%%::*}"; cmd="${spec#*::}"
    [ -z "$name" ] && name="custom"
    record_cmd "$name" "$cmd" "$LOG_DIR/${name}.log"
  done
fi

# Build collected logs listing (if any)
LOGS_LIST="$OUTPUT_DIR/_logs_index.txt"
if [ -d "$LOG_DIR" ]; then
  ls -1 "$LOG_DIR"/*.log 2>/dev/null | sed 's#.*/##' > "$LOGS_LIST" || true
fi

# ----- Grouping -----
declare -A GROUP_TO_FILES
declare -a GROUP_ORDER

if [ "$GROUPING_MODE" = "manual" ] && [ -n "$GROUPS_FILE" ] && [ -f "$GROUPS_FILE" ]; then
  # Format: group: glob1 glob2 ...
  while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^# ]] && continue
    group="${line%%:*}"
    globs="${line#*:}"
    group="$(echo "$group" | xargs)"
    [ -z "$group" ] && continue
    GROUP_ORDER+=("$group")
    # Expand globs relative to repo root
    # shellcheck disable=SC2086
    files=$(cd "$REPO_ROOT" && eval "printf '%s\n' $globs" 2>/dev/null | sed 's#^./##' || true)
    # Intersect with FILTERED_LIST
    while IFS= read -r rel; do
      grep -qxF "$rel" "$FILTERED_LIST" || continue
      GROUP_TO_FILES["$group"]+="$rel"$'\n'
    done <<< "$files"
  done < "$GROUPS_FILE"
else
  # by_dir: top-level directory; files at repo root -> group "root"
  while IFS= read -r rel; do
    top="${rel%%/*}"
    if [[ "$rel" != */* ]]; then top="root"; fi
    if [ -z "${GROUP_TO_FILES[$top]+set}" ]; then GROUP_ORDER+=("$top"); fi
    GROUP_TO_FILES["$top"]+="$rel"$'\n'
  done < "$FILTERED_LIST"
fi

# ----- Emit helper: next prompt index -----
PROMPT_IDX=1
next_prefix() {
  local p
  printf -v p "%02d" $((PROMPT_IDX-1))
  echo "$p"
}
inc_prompt() { PROMPT_IDX=$((PROMPT_IDX+1)); }

PASTE_ORDER="$OUTPUT_DIR/PASTE_ORDER.txt"
: > "$PASTE_ORDER"

# ----- PROMPT 1: Review context (small) -----
P1="$OUTPUT_DIR/00_PROMPT_1_REVIEW_CONTEXT.txt"
{
  echo "# PROMPT 1 — Review Context & Instructions"
  echo ""
  echo "You will receive this review as a multi-part sequence of messages."
  echo "Please read this message fully, then wait for subsequent parts."
  echo ""
  echo "## Scope"
  echo "- Repo root: $REPO_ROOT"
  echo "- Range: $BASE_REF .. $HEAD_REF"
  echo "- Generated: $(date -Iseconds)"
  echo ""
  echo "## What you'll receive next"
  echo "2) Context docs (architecture/charter/mvp/requirements/vision)"
  echo "3) Manifest (file status, line deltas) + concise commit list"
  echo "4..N) Bundles of code/logs grouped by locality, each under a size cap"
  echo "N+1) Finalizer prompt with the requested structured output format"
  echo ""
  echo "## Please acknowledge each part with 'ACK n/N'."
  echo "Do not produce the final review until the FINALIZER prompt arrives."
  echo ""
  echo "## Notes"
  echo "- Renames are detected to avoid miscounting (git --find-renames)."
  echo "- Bundles may repeat a tiny shared context to reduce context thrash."
  echo ""
} > "$P1"
echo "$(basename "$P1")" >> "$PASTE_ORDER"
inc_prompt

# ----- PROMPT 2: Context docs -----
P2="$OUTPUT_DIR/01_PROMPT_2_CONTEXT_DOCS.txt"
{
  echo "# PROMPT 2 — Context Docs"
  if [ "${#CONTEXT_DOCS[@]}" -eq 0 ]; then
    echo "_No context docs found in docs/ (architecture.md, charter.md, mvp.md, requirements.md, vision.md)._"
  else
    for rel in "${CONTEXT_DOCS[@]}"; do
      f="$REPO_ROOT/$rel"
      [ -f "$f" ] || continue
      append_file_block "$f" "/dev/stdout" >/dev/null
    done
  fi
} > "$P2"
echo "$(basename "$P2")" >> "$PASTE_ORDER"
inc_prompt

# ----- PROMPT 3: Manifest & commits -----
P3="$OUTPUT_DIR/02_PROMPT_3_MANIFEST.txt"
{
  echo "# PROMPT 3 — Manifest & Commits"
  echo ""
  echo "## File status (A=added, M=modified, D=deleted, R=renamed, C=copied, T=type, U=unmerged)"
  echo '```txt'
  cat "$MANIFEST_NS"
  echo '```'
  echo ""
  echo "## Per-file line deltas (insertions, deletions, path)"
  echo '```txt'
  cat "$MANIFEST_NUM"
  echo '```'
  echo ""
  echo "## Concise commit list"
  echo '```txt'
  cat "$COMMITS_TXT"
  echo '```'
} > "$P3"
echo "$(basename "$P3")" >> "$PASTE_ORDER"
inc_prompt

# ----- PROMPT 4..N: Bundles -----
# Helper to create a new bundle with size cap
make_bundle_from_list() {
  local title="$1" list_file="$2" start_idx="$3"
  local seq="$start_idx" out="" cur_bytes=0 rel fpath sz
  local prefix idxlabel
  while : ; do
    # if no items remain, break
    if ! IFS= read -r rel <&3; then break; fi
    # start new bundle if needed
    if [ -z "${out:-}" ]; then
      printf -v idxlabel "%02d" "$((PROMPT_IDX-1))"
      out="$OUTPUT_DIR/${idxlabel}_PROMPT_${PROMPT_IDX}_BUNDLE_${title}_$(printf '%02d' "$seq").txt"
      {
        printf "# PROMPT %d — Bundle: %s (%02d)\n\n" "$PROMPT_IDX" "$title" "$seq"
      } > "$out"
      echo "$(basename "$out")" >> "$PASTE_ORDER"
      inc_prompt
      cur_bytes="$(file_size_bytes "$out")"
    fi
    fpath="$REPO_ROOT/$rel"
    [ -f "$fpath" ] || continue
    if has_excluded_ext "$fpath"; then continue; fi
    if ! is_text_file "$fpath"; then continue; fi

    # write into tmp to size-check overhead
    local tmp="$(mktemp -t rb_chunk.XXXXXX)"
    {
      printf '===== BEGIN FILE: %s =====\n' "$fpath"
      sed 's/^/    /' "$fpath"
      printf '\n===== END FILE: %s =====\n\n' "$fpath"
    } > "$tmp"
    sz="$(file_size_bytes "$tmp" 2>/dev/null || echo 0)"

    if [ $((cur_bytes + sz)) -le "$MAX_BYTES" ]; then
      cat "$tmp" >> "$out"
      cur_bytes=$((cur_bytes + sz))
      rm -f "$tmp"
    else
      # close current and start a new bundle
      rm -f "$tmp"
      out="" ; seq=$((seq+1))
      # rewind this path (push back)
      printf '%s\n' "$rel" >> "$OUTPUT_DIR/_pushback.tmp"
    fi
  done 3< <(awk 'NF{print}' "$list_file")

  # handle pushback items recursively if any
  if [ -s "$OUTPUT_DIR/_pushback.tmp" ]; then
    mv "$OUTPUT_DIR/_pushback.tmp" "$list_file.__rest"
    make_bundle_from_list "$title" "$list_file.__rest" "$seq"
    rm -f "$list_file.__rest"
  else
    rm -f "$OUTPUT_DIR/_pushback.tmp" 2>/dev/null || true
  fi
}

# Build and output bundles per group
for grp in "${GROUP_ORDER[@]}"; do
  LIST="$OUTPUT_DIR/_list_${grp}.txt"
  # unique, sorted
  printf '%s' "${GROUP_TO_FILES[$grp]-}" | awk 'NF{print}' | sort -u > "$LIST"
  if [ -s "$LIST" ]; then
    make_bundle_from_list "$grp" "$LIST" 1
  fi
done

# ----- Optional LOGS bundle (after code) -----
if [ -s "$LOGS_LIST" ]; then
  idxlabel="$(printf '%02d' "$((PROMPT_IDX-1))")"
  LOUT="$OUTPUT_DIR/${idxlabel}_PROMPT_${PROMPT_IDX}_BUNDLE_logs_01.txt"
  {
    printf "# PROMPT %d — Bundle: logs (01)\n\n" "$PROMPT_IDX"
    while IFS= read -r name; do
      f="$LOG_DIR/$name"
      [ -f "$f" ] || continue
      append_file_block "$f" "/dev/stdout" >/dev/null
    done < "$LOGS_LIST"
  } > "$LOUT"
  echo "$(basename "$LOUT")" >> "$PASTE_ORDER"
  inc_prompt
fi

# ----- FINALIZER -----
PF="$OUTPUT_DIR/ZZ_PROMPT_FINALIZER.txt"
{
  echo "# FINALIZER — Please produce the structured review now"
  echo ""
  echo "When you have received all prior parts and replied with 'ACK n/N' each time,"
  echo "use the full context to produce a structured review with the following sections:"
  echo ""
  echo "1) Executive Summary (bullet points)"
  echo "2) Correctness & Design (APIs, invariants, error handling; call out risky areas)"
  echo "3) Security & Secrets (hardcoded credentials, auth flows, dependency risks)"
  echo "4) Performance (hot paths, memory/disk I/O, N+1 queries, caching opportunities)"
  echo "5) Testing & Verification (coverage gaps, flaky areas, missing cases)"
  echo "6) Maintainability (readability, modularity, dead code, naming, comments)"
  echo "7) Observability (logging, metrics, tracing, feature flags, config)"
  echo "8) Migration/Rollback (DB/schema changes, compat, flags)"
  echo "9) Changelist Risks (large deltas, renames, cross-cutting refactors)"
  echo "10) Actionable Next Steps (prioritized checklist with owners if known)"
  echo ""
  echo "If critical context seems missing, list explicit follow-up questions."
} > "$PF"
echo "$(basename "$PF")" >> "$PASTE_ORDER"

# ----- Index & console summary -----
echo ""
echo "${BOLD}Paste order:${RESET}"
nl -w2 -s'. ' "$PASTE_ORDER" | sed "s#^#  #"
echo ""
echo "${DIM}(Files are in $OUTPUT_DIR. Paste each file's content as a separate message in order.)${RESET}"

exit 0
