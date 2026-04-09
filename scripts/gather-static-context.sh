#!/usr/bin/env bash
# gather-static-context.sh — Concatenate all verdify.ai static content into
# a single context file for the planner to read in one pass.
#
# Output: /srv/verdify/state/planner-static-context.md
# Excludes: plans/ (generated daily), dashboards/ (persona pages), static/
set -euo pipefail

CONTENT_DIR="/srv/verdify/verdify-site/content"
OUTPUT="/srv/verdify/state/planner-static-context.md"

mkdir -p "$(dirname "$OUTPUT")"

{
    echo "# Verdify Static Context"
    echo ""
    echo "Generated: $(date '+%Y-%m-%d %H:%M %Z')"
    echo "Source: ${CONTENT_DIR}/"
    echo "Files: $(find "$CONTENT_DIR" -name '*.md' \
        -not -path '*/plans/*' \
        -not -path '*/dashboards/*' \
        -not -path '*/static/*' | wc -l)"
    echo ""
    echo "---"
    echo ""

    # Process files in a logical order: index first, then alphabetical by directory
    find "$CONTENT_DIR" -name '*.md' \
        -not -path '*/plans/*' \
        -not -path '*/dashboards/*' \
        -not -path '*/static/*' \
        -not -path '*/node_modules/*' \
        | sort -t/ -k6,6 -k7,7 -k8,8 \
        | while read -r file; do
            # Relative path for the section header
            relpath="${file#${CONTENT_DIR}/}"
            echo "================================================================"
            echo "## ${relpath}"
            echo "================================================================"
            echo ""
            # Strip YAML frontmatter + HTML/iframe/Grafana markup (not useful for planning)
            awk 'BEGIN{fm=0} /^---$/{fm++; next} fm>=2||fm==0{print}' "$file" \
                | grep -v '<iframe\|<div\|</div>\|<link\|<script\|</script>\|grafana-controls\|frameborder' \
                | sed '/^$/N;/^\n$/d'
            echo ""
            echo ""
        done
} > "$OUTPUT"

SIZE=$(wc -c < "$OUTPUT")
LINES=$(wc -l < "$OUTPUT")
echo "Static context: ${LINES} lines, $(( SIZE / 1024 ))KB → ${OUTPUT}"
