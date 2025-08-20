---
title: "{{title}}"
created: "{{created_at}}"
processed: "{{processed_at}}"
tags: {{tags}}
audio_file: "{{audio_file}}"
transcript_file: "{{transcript_file}}"
duration: "{{duration}}"
file_size: "{{file_size}}"
sample_rate: "{{sample_rate}}"
channels: "{{channels}}"
format: "{{format}}"
profile: "{{profile}}"
sha256_file: "{{sha256_file}}"
sha256_pcm: "{{sha256_pcm}}"
participants: {{participants}}
model_version: "{{model_version}}"
filters_applied: {{filters_applied}}
processing_version: "{{processing_version}}"
---

# {{title}}

## Summary
<!-- Auto-generated summary will be inserted here -->

## Key Points
<!-- Important points from the conversation -->

## Decisions
<!-- Any decisions made during the conversation -->

## Action Items
<!-- Tasks or follow-ups identified -->

## People
<!-- Participants and their roles -->
{{#each participants}}
- **{{name}}**: {{role}}
{{/each}}

## Technical Metadata
- **Duration**: {{duration}}
- **File Size**: {{file_size}}
- **Sample Rate**: {{sample_rate}}Hz
- **Channels**: {{channels}}
- **Format**: {{format}}
- **Profile**: {{profile}}
- **Model**: {{model_version}}
- **Processing**: {{processing_version}}

## Links
- [Audio File]({{audio_file}})
- [Transcript]({{transcript_file}})

---

## Full Transcript

{{transcript_content}}