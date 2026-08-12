---
id: SPEC-core-001
type: invariant
component: core
status: active
depends: []
---
Code and data are strictly separated. The repository holds only the durable layer and
generated implementations; all user data lives under `$TAPEDECK_HOME` (default
`~/Tapedeck`) in the structure defined by `system/contracts/library-layout.md`, and
every path in that structure has exactly one component with write authority. No
component may write outside its declared paths.
