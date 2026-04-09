#!/bin/bash
# Rebuild Quartz site from content and refresh the nginx container
set -e
cd /srv/verdify/verdify-site
npx quartz build 2>&1
cd /srv/verdify
docker compose up -d --force-recreate verdify-site 2>&1 | tail -3
echo "$(date '+%Y-%m-%d %H:%M:%S') Site rebuilt: $(find verdify-site/public -name '*.html' | wc -l) pages"
