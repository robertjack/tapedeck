"""Durable evals: transcribe from-parakeet (SPEC-transcribe-002).

Boundary: `python -m transcribe from-parakeet`, parakeet JSON on stdin,
whisper-shaped JSON on stdout.
"""

import json
import os
import shlex
import subprocess
import sys

from conftest import REPO, TIMEOUT

PARAKEET = {
    "text": "Welcome to the fixture show. The core idea is regeneration.",
    "sentences": [
        {
            "text": "Welcome to the fixture show.",
            "start": 0.08,
            "end": 4.52,
            "duration": 4.44,
            "confidence": 0.97,
            "tokens": [
                {"text": "Welcome", "start": 0.08, "end": 0.4, "duration": 0.32, "confidence": 0.99}
            ],
        },
        {
            "text": "The core idea is regeneration.",
            "start": 96.0,
            "end": 103.5,
            "duration": 7.5,
            "confidence": 0.95,
            "tokens": [],
        },
    ],
}


def from_parakeet(payload, home):
    cmd = os.environ.get("TAPEDECK_TRANSCRIBE_CMD", f"{sys.executable} -m transcribe")
    return subprocess.run(
        [*shlex.split(cmd), "from-parakeet"],
        cwd=REPO,
        input=payload,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env={
            **os.environ,
            "TAPEDECK_HOME": str(home),
            # installation-independent: components run from src/ with no packaging
            "PYTHONPATH": os.pathsep.join(
                [str(REPO / "src"), os.environ.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep),
        },
    )


def test_parakeet_sentences_become_whisper_segments(home):
    r = from_parakeet(json.dumps(PARAKEET), home)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["segments"] == [
        {"start": 0.08, "end": 4.52, "text": "Welcome to the fixture show."},
        {"start": 96.0, "end": 103.5, "text": "The core idea is regeneration."},
    ]


def test_non_parakeet_input_exits_1_with_empty_stdout(home):
    for bad in ("not json at all", json.dumps({"nope": []}), json.dumps("just a string")):
        r = from_parakeet(bad, home)
        assert r.returncode == 1, f"accepted: {bad!r}"
        assert r.stdout.strip() == ""
