#!/usr/bin/env bash
set -euo pipefail

input="${1:-/mnt/iris/Verdify Launch.mp4}"
output="${2:-/mnt/iris/verdify-vault/website/static/video/launch}"

if [[ ! -f "$input" ]]; then
  echo "Input video not found: $input" >&2
  exit 1
fi

for tool in ffmpeg ffprobe; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 1
  fi
done

parent="$(dirname "$output")"
mkdir -p "$parent"
# Keep work-in-progress media outside the website tree so the polling rebuild
# service cannot publish partial segments while a long transcode is running.
tmp="$(mktemp -d /mnt/iris/.verdify-launch-video.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp"/{1080p,720p,480p}

ffmpeg -hide_banner -y \
  -ss 00:00:08 \
  -i "$input" \
  -frames:v 1 \
  -vf "scale='min(1600,iw)':-2" \
  -q:v 4 \
  "$tmp/poster.jpg"

ffmpeg -hide_banner -y \
  -i "$input" \
  -filter_complex "[0:v]split=3[v1][v2][v3];[v1]scale=1920:-2[v1080];[v2]scale=1280:-2[v720];[v3]scale=854:-2[v480]" \
  -map "[v1080]" -map 0:a:0 \
  -map "[v720]" -map 0:a:0 \
  -map "[v480]" -map 0:a:0 \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p \
  -g 60 -keyint_min 60 -sc_threshold 0 \
  -b:v:0 5000k -maxrate:v:0 5500k -bufsize:v:0 10000k \
  -b:v:1 2600k -maxrate:v:1 3000k -bufsize:v:1 5200k \
  -b:v:2 1100k -maxrate:v:2 1400k -bufsize:v:2 2200k \
  -c:a aac \
  -b:a:0 160k -b:a:1 128k -b:a:2 96k \
  -ac 2 -ar 48000 \
  -f hls \
  -hls_time 4 \
  -hls_playlist_type vod \
  -hls_flags independent_segments \
  -master_pl_name master.m3u8 \
  -var_stream_map "v:0,a:0,name:1080p v:1,a:1,name:720p v:2,a:2,name:480p" \
  -hls_segment_filename "$tmp/%v/seg_%05d.ts" \
  "$tmp/%v/index.m3u8"

ffmpeg -hide_banner -y \
  -i "$input" \
  -vf "scale=1920:-2" \
  -c:v libx264 -preset veryfast -crf 22 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -ac 2 -ar 48000 \
  -movflags +faststart \
  "$tmp/verdify-launch-1080p.mp4"

ffmpeg -hide_banner -y \
  -i "$input" \
  -vf "scale=1280:-2" \
  -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ac 2 -ar 48000 \
  -movflags +faststart \
  "$tmp/verdify-launch-720p.mp4"

generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
duration="$(ffprobe -hide_banner -v error -show_entries format=duration -of default=nw=1:nk=1 "$input")"

cat > "$tmp/manifest.json" <<JSON
{
  "source": "$input",
  "generated_at": "$generated_at",
  "duration_seconds": $duration,
  "hls": "/static/video/launch/master.m3u8",
  "poster": "/static/video/launch/poster.jpg",
  "fallbacks": [
    "/static/video/launch/verdify-launch-1080p.mp4",
    "/static/video/launch/verdify-launch-720p.mp4"
  ],
  "variants": [
    {"name": "1080p", "width": 1920, "video_bitrate": "5000k"},
    {"name": "720p", "width": 1280, "video_bitrate": "2600k"},
    {"name": "480p", "width": 854, "video_bitrate": "1100k"}
  ]
}
JSON

backup=""
if [[ -d "$output" ]]; then
  backup="${output}.previous.$(date +%s)"
  mv "$output" "$backup"
fi
mv "$tmp" "$output"
trap - EXIT

if [[ -n "$backup" ]]; then
  rm -rf "$backup"
fi

du -sh "$output"
find "$output" -maxdepth 2 -type f | sort
