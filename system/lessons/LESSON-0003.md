---
id: LESSON-0003
components: [ingest, cli]
source: conversation
evidence: 2026-08-13 audit of the generated components — hms/deep-link formatting, the 11-character video-id regex, TAPEDECK_HOME resolution, atomic JSON writing and the video-file rules had each been hand-copied into several components, and the copies had drifted: cli's media() counted a `video.part` as a downloaded video where ingest's NOT_VIDEO rules did not, so the two disagreed about whether a video was present and every eval stayed green.
status: active
---
Shared vocabulary belongs to exactly one component and is imported from it, never
re-derived by its readers. Each independently generated component will happily write
its own correct-looking copy of a rule the system already has — and the copies drift
apart silently, because each component's own evals still pass while the two answers
disagree. ingest owns the canonical video-id grammar and the rules for what counts as
a downloaded video file; archive owns the archive page format and its deep links. A
component that needs one of those consumes the owning component's definition, and the
owner publishes it for that purpose. Duplicating the rule is the defect, whether or not
the copy is currently right.
