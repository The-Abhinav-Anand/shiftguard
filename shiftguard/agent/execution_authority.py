"""Derive bounded execution grants only from the immutable human command."""

from __future__ import annotations

import re

# Execution uses a closed command language rather than model interpretation.
# A full match rejects quoted, negated, hypothetical and appended instructions.
_COMMAND = re.compile(
    r"(?:please )?(?:inspect bank(?: dataset)? and )?(?:run|start|execute|launch) (.+?)[.!]?",
    re.ASCII,
)
_RESULT_SUFFIX = re.compile(
    r"(?:,? then (?:(?:show|compare|summarize) (?:the )?results|inspect bank(?: dataset)?)"
    r"| and retry once after an admission failure| with at most one retry| with bounded arguments)\Z"
)
_PRESETS = {
    "baseline": "bank-baseline",
    "bank baseline": "bank-baseline",
    "bank-baseline": "bank-baseline",
    "bank stress": "bank-stress",
    "bank-stress": "bank-stress",
    "bank-stress-30": "bank-stress",
    "stress suite": "bank-stress",
    "flagship stress": "bank-stress",
    "flagship stress suite": "bank-stress",
    "bank outage 50": "bank-outage-50",
    "bank-outage-50": "bank-outage-50",
    "outage suite": "bank-outage-50",
}


def authorized_execution_presets(prompt: str) -> frozenset[str]:
    """Return named grants, or none when the entire command is ambiguous."""
    if not isinstance(prompt, str) or not prompt.isascii():
        return frozenset()
    normalized = " ".join(prompt.lower().split())
    match = _COMMAND.fullmatch(normalized)
    if match is None:
        return frozenset()
    names = _RESULT_SUFFIX.sub("", match.group(1))
    parts = names.split(" and ")
    if len(parts) > 3:
        return frozenset()
    presets = []
    for part in parts:
        preset = _PRESETS.get(part.removeprefix("the "))
        if preset is None or preset in presets:
            return frozenset()
        presets.append(preset)
    return frozenset(presets)


def execution_preset(tool_name: str, arguments: dict) -> str | None:
    """Translate validated execution-tool arguments into their queue resource."""
    if tool_name == "run_experiment":
        return arguments.get("preset_name")
    if tool_name == "run_stress_suite":
        return "bank-stress"
    return None


EXECUTION_DENIED_MESSAGE = (
    "EXECUTION_NOT_AUTHORIZED: An explicit human command naming this preset is required. "
    "Use Run bank-baseline, Run bank-stress, or Run bank-outage-50."
)
