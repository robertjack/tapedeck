---
id: LESSON-0006
components: [ingest]
source: production
evidence: 2026-08-17 pilot: sJ4VJWycX9M (public, not age-restricted) 403'd on video data through the default client chain with a current yt-dlp (2026.07.04, brew's latest); the tv client reported "this video is drm protected and only images are available"; ios offered no matching format; web_embedded served the full avc1 1080p stream cleanly (verified by test download). Fix lived only in the pilot library's hand-edited config.toml until this lesson.
status: active
---
YouTube now serves some public videos DRM-flagged to yt-dlp's default player clients:
formats are listed but their data URLs 403, and the failure is per-video, not
per-setup — the same chain fetched a different video cleanly thirty minutes earlier.
The embedded player (`web_embedded`) still receives clean avc1 streams for these
videos, so the shipped default's extractor-args must lead with it:
`youtube:player_client=web_embedded,default,-web_safari` — web_embedded first so its
working URLs win when the same format id is offered twice, the default set behind it
for anything non-embeddable. This is LESSON-0001's lesson recurring one platform
change later: a battle-tested seam command is durable knowledge, and a fix that lives
only in one library's config.toml is re-suffered by every fresh install.
