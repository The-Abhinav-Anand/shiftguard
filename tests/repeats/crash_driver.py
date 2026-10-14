"""Subprocess half of the synthetic restart tests.

Commits one fabricated completion and hard-exits at a named persistence seam.
``os._exit`` skips every cleanup and flush, the closest portable stand-in for a
killed process. Fabricated content only.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from repeat_fixtures import synthetic_plan
from shiftguard.repeats.completion import build_completion
from shiftguard.repeats.synthetic_store import SyntheticRepeatStore


CRASH_EXIT_CODE = 73
DRIVER_CONTENT = {"synthetic": True, "summary": {"theta": -0.1, "cells": 400}}


def main() -> int:
    root, seam = Path(sys.argv[1]), sys.argv[2]

    def die(name: str) -> None:
        if name == seam:
            os._exit(CRASH_EXIT_CODE)

    plan = synthetic_plan()
    record, artifact = build_completion(
        plan, plan.repeats[0].repeat_id, DRIVER_CONTENT, "completed"
    )
    result = SyntheticRepeatStore(root, fault=die).commit(
        record, artifact, attempt_id=f"driver-{seam}"
    )
    print(result.decision.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
