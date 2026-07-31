#!/usr/bin/env bash
# Mutation testing for the modules the escaped bugs actually lived in (方案 3 of #19).
#
# Coverage says a line ran; mutation testing says breaking that line gets noticed.
# The suite sat at 86% coverage while shipping nine "claims to record, writes
# nothing" bugs, so this measures the thing coverage cannot.
#
# The gate is a ratchet, not a target: today's survivors are recorded in
# tests/mutation_baseline.json and the run fails only if that number grows.
# Clearing 526 survivors is a long job; letting new ones in is not allowed.
#
#   ./scripts/mutation.sh            # run and check against the baseline
#   ./scripts/mutation.sh --update   # rerun and rewrite the baseline
#
# mutmut goes into a venv of its own, never .venv. Installing it into the
# project environment made uv re-resolve and drop pytest-asyncio, which turns
# all 275 async unit tests into "async def not natively supported" failures —
# a wrecked test run that looks exactly like a broken code change.
set -euo pipefail

cd "$(dirname "$0")/.."

BASELINE="tests/mutation_baseline.json"
TOOL_VENV="${MUTATION_VENV:-.tmp/mutation-venv}"
STATS="mutants/mutmut-cicd-stats.json"
update_baseline=false
[[ "${1:-}" == "--update" ]] && update_baseline=true

export TMPDIR="${TMPDIR:-$PWD/.tmp}"
mkdir -p "$TMPDIR"

echo "── Preparing the tool environment (kept apart from .venv) ──"
if [[ ! -x "$TOOL_VENV/bin/mutmut" ]]; then
  uv venv "$TOOL_VENV" --quiet
  uv pip install --quiet --python "$TOOL_VENV/bin/python" -e ".[dev]" mutmut
fi
"$TOOL_VENV/bin/mutmut" --version

# A mutmut run that cannot execute async tests would report every mutant as
# surviving, which reads like a catastrophe instead of a broken setup.
echo "── Checking the tool environment can actually run async tests ──"
"$TOOL_VENV/bin/python" -m pytest \
  "tests/unit/core/test_recorder.py::TestRecorder::test_stop" -q -p no:randomly >/dev/null
echo "async tests run: ok"

echo "── Running mutation testing ──"
rm -rf mutants
"$TOOL_VENV/bin/mutmut" run --max-children "$(nproc)" 2>&1 | tail -3
"$TOOL_VENV/bin/mutmut" export-cicd-stats >/dev/null
# The per-mutant verdicts only come out of this command, not out of a file.
"$TOOL_VENV/bin/mutmut" results > mutants/results.txt

MUTATION_UPDATE_BASELINE="$update_baseline" \
  "$TOOL_VENV/bin/python" scripts/mutation_report.py "$STATS" "$BASELINE"
