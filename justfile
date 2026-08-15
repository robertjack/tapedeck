# phx eval runner — customize per component/language as the project grows

default:
    @just --list

# Run durable evals for one component (boundary only — SPEC-core-002)
eval component:
    uv run --no-project --with pytest pytest system/evals/{{component}} -q

# Run all durable evals
eval-all:
    uv run --no-project --with pytest pytest system/evals -q
