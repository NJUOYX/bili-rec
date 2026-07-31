"""Report mutation results and hold them to the recorded baseline.

Split out of ``scripts/mutation.sh`` so the ratchet logic is testable and the
per-module breakdown can be read without digging through mutmut's own output.

A mutant that no test even reaches (``no_tests``) counts as not-killed here:
"nothing exercises this" is a wider hole than "a test runs it but asserts too
little". Timeouts are reported but left out of the count, since a mutant that
makes the suite hang did get noticed.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

MUTANTS_SRC = Path("mutants/src/birec")
RESULTS = Path("mutants/results.txt")


def survivors_by_module() -> Counter[str]:
    """Count surviving mutants per module from mutmut's own result listing."""
    counts: Counter[str] = Counter()
    if not RESULTS.exists():
        return counts
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.endswith((": survived", ": no tests")):
            continue
        counts[line.split(".x")[0].rsplit(":", 1)[0].strip()] += 1
    return counts


def mutants_by_module() -> Counter[str]:
    """Count generated mutants per module by reading the mutated sources."""
    counts: Counter[str] = Counter()
    if not MUTANTS_SRC.exists():
        return counts
    for path in MUTANTS_SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        found = len(re.findall(r"def x\w+__mutmut_\d+", source))
        if not found:
            continue
        rel = path.relative_to(MUTANTS_SRC).with_suffix("")
        parts = [p for p in rel.parts if p != "__init__"]
        counts["birec." + ".".join(parts)] = found
    return counts


def main() -> int:
    stats_path, baseline_path = Path(sys.argv[1]), Path(sys.argv[2])
    stats = json.loads(stats_path.read_text(encoding="utf-8"))

    killed = stats.get("killed", 0)
    survived = stats.get("survived", 0)
    no_tests = stats.get("no_tests", 0)
    timeout = stats.get("timeout", 0)
    total = stats.get("total", 0)
    alive = survived + no_tests

    per_module = survivors_by_module()
    totals = mutants_by_module()
    if per_module:
        print(f"\n{'module':<40} {'alive':>6} {'total':>6} {'alive %':>8}")
        print("-" * 64)
        for module, count in per_module.most_common():
            module_total = totals.get(module, 0)
            share = f"{count / module_total * 100:.0f}%" if module_total else "-"
            print(f"{module:<40} {count:>6} {module_total:>6} {share:>8}")
        print("-" * 64)

    rate = alive / total * 100 if total else 0.0
    print(
        f"\n{total} mutants: {killed} killed, {survived} survived, "
        f"{no_tests} never reached by a test, {timeout} timed out"
    )
    print(f"not killed: {alive} ({rate:.0f}% of all mutants)")

    if os.environ.get("MUTATION_UPDATE_BASELINE") == "true":
        baseline_path.write_text(
            json.dumps(
                {
                    "not_killed": alive,
                    "total": total,
                    "per_module": dict(per_module.most_common()),
                },
                indent=2,
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nbaseline written to {baseline_path}: not_killed = {alive}")
        return 0

    if not baseline_path.exists():
        print(f"\nno baseline at {baseline_path}; run with --update to record one")
        return 1

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    allowed = baseline["not_killed"]

    if alive > allowed:
        print(
            f"\n::error::mutation testing went backwards: {alive} mutants survive, "
            f"baseline allows {allowed}. New logic needs tests that fail when it "
            f"breaks — see `mutmut show <mutant>` for what went unnoticed."
        )
        return 1

    if alive < allowed:
        print(
            f"\n::notice::{allowed - alive} fewer mutants survive than the baseline "
            f"allows. Run ./scripts/mutation.sh --update to tighten it."
        )
    else:
        print(f"\nheld at the baseline of {allowed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
