"""kengine — drive the REAL shipping Boost Kotlin engines from Python. One JVM invocation per batch;
state carried across cycles inside the engine as on-device. See HARNESS_SPEC.md. Build the jar first:
`boost-harness/build.sh`."""
from __future__ import annotations
import json, os, subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_HARNESS = os.path.join(_HERE, "boost-harness")
_JAR = os.path.join(_HARNESS, "boost-harness.jar")


def _java() -> str:
    jh = os.environ.get("JAVA_HOME") or "/Applications/Android Studio.app/Contents/jbr/Contents/Home"
    cand = os.path.join(jh, "bin", "java")
    return cand if os.path.exists(cand) else "java"


def _jsonjar() -> str:
    f = os.path.join(_HARNESS, ".jsonjar")
    return open(f).read().strip() if os.path.exists(f) else ""


def run_engine(engine: str, cycles: list[dict], params: dict | None = None, seed: int = 1) -> list[dict]:
    """engine in {twin, backout, sleep}. cycles = list of per-cycle input dicts (see Harness.kt).
    Returns the list of per-cycle result dicts from the real engine."""
    if not os.path.exists(_JAR):
        raise RuntimeError(f"harness jar missing — run {_HARNESS}/build.sh first")
    req = json.dumps({"engine": engine, "seed": seed, "params": params or {}, "cycles": cycles})
    cp = f"{_JAR}:{_jsonjar()}"
    p = subprocess.run([_java(), "-cp", cp, "HarnessKt"], input=req, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"harness engine '{engine}' failed (rc={p.returncode}): {p.stderr[:800]}")
    return json.loads(p.stdout)["results"]
