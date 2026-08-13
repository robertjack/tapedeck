---
id: LESSON-0001
components: [ingest]
source: production
evidence: 2026-08-12 pilot: stock yt-dlp format selection hit YouTube 403s on AV1 streams for both library videos; the avc1-preferring selector downloaded the same videos cleanly. Fix lived only in the pilot library's hand-edited config.toml until this lesson.
status: active
---
YouTube serves 403s to yt-dlp AV1 format downloads in this setup; h264 (avc1) streams work. The default fetcher command the component ships must therefore prefer avc1 at <=1080p with plain fallbacks — -f "bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b" — never the naive bv*+ba/b. A battle-tested seam command is durable knowledge: promote it into the shipped default, or every fresh install re-suffers the solved incident.
