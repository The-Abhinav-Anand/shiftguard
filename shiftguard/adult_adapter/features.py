"""Adult feature contract and label-blind raw records for the Gate 9 adapter.

Engineering slice only: the constants come from the frozen training parser and
are imported, never redefined. Nothing here reads a file, parses a label,
fits a model or scores an outcome, and building these types is not a
replication or confirmation of anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Mapping

from shiftguard.datasets.adult import (
    ADULT_CATEGORICAL_FEATURES,
    ADULT_NUMERIC_FEATURES,
    ADULT_PREDICTORS,
)


SCHEMA_VERSION = "gate9-adult-feature-schema-v1"
NATURAL_MISSING_TOKEN = "?"
DEVELOPMENT_SOURCE_FILE = "adult.data"
SOURCE_FILES = (DEVELOPMENT_SOURCE_FILE, "adult.test")

_DIGEST = re.compile(r"[0-9a-f]{64}")
_RELEASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]*")
_ROW_ID = re.compile(r"([A-Za-z0-9][A-Za-z0-9._\-]*):(adult\.data|adult\.test):([1-9][0-9]*)")


class AdultAdapterError(ValueError):
    """A typed rejection; ``code`` is stable, ``detail`` names the offending field."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def canonical_digest(value: Any) -> str:
    """Logical identity: SHA-256 of canonical ASCII JSON, never of file bytes."""
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def strict_int(value: Any, name: str, code: str = "STRICT_INTEGER") -> int:
    # bool is an int subclass and floats compare equal to ints; both would alias seeds silently.
    if type(value) is not int:
        raise AdultAdapterError(code, name)
    return value


def immutable_tuple(value: Any, name: str) -> tuple:
    if type(value) is not tuple:
        raise AdultAdapterError("IMMUTABLE_TUPLE", name)
    return value


def digest_field(value: Any, name: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise AdultAdapterError("DIGEST", name)
    return value


@dataclass(frozen=True)
class AdultFeatureContract:
    """Explicit numeric/categorical declaration of the 13 predictors and the natural-missing token."""

    features: tuple[str, ...] = ADULT_PREDICTORS
    numeric: tuple[str, ...] = ADULT_NUMERIC_FEATURES
    categorical: tuple[str, ...] = ADULT_CATEGORICAL_FEATURES
    natural_missing_token: str = NATURAL_MISSING_TOKEN

    def __post_init__(self) -> None:
        for name in ("features", "numeric", "categorical"):
            value = immutable_tuple(getattr(self, name), name)
            if any(type(item) is not str or not item for item in value) or len(set(value)) != len(value):
                raise AdultAdapterError("FEATURE_CONTRACT", name)
        # A feature is numeric xor categorical; anything else would make preprocessing ambiguous.
        if not self.features or set(self.numeric) | set(self.categorical) != set(self.features):
            raise AdultAdapterError("FEATURE_CONTRACT", "numeric+categorical must cover features")
        if set(self.numeric) & set(self.categorical):
            raise AdultAdapterError("FEATURE_CONTRACT", "numeric and categorical overlap")
        if type(self.natural_missing_token) is not str or not self.natural_missing_token.strip():
            raise AdultAdapterError("FEATURE_CONTRACT", "natural_missing_token")

    @cached_property
    def schema_digest(self) -> str:
        return canonical_digest({
            "schema_version": SCHEMA_VERSION,
            "features": list(self.features),
            "numeric": list(self.numeric),
            "categorical": list(self.categorical),
            "natural_missing_token": self.natural_missing_token,
        })


ADULT_FEATURE_CONTRACT = AdultFeatureContract()
FEATURE_COUNT = len(ADULT_FEATURE_CONTRACT.features)


@dataclass(frozen=True)
class SourceRowId:
    release: str
    source_file: str
    line: int

    @property
    def text(self) -> str:
        return f"{self.release}:{self.source_file}:{self.line}"

    @property
    def order_key(self) -> tuple[str, str, int]:
        # Numeric line order: text order would put line 10 before line 9.
        return (self.release, self.source_file, self.line)


def make_row_id(release: Any, source_file: Any, line: Any) -> str:
    """Source-qualified id ``<release>:<source_file>:<line>``; the same line number in two files differs."""
    if type(release) is not str or _RELEASE.fullmatch(release) is None:
        raise AdultAdapterError("ROW_ID", "release")
    if source_file not in SOURCE_FILES:
        raise AdultAdapterError("ROW_ID", "source_file")
    if type(line) is not int or line < 1:
        raise AdultAdapterError("ROW_ID", "line")
    return f"{release}:{source_file}:{line}"


def parse_row_id(text: Any) -> SourceRowId:
    match = _ROW_ID.fullmatch(text) if type(text) is str else None
    if match is None:
        raise AdultAdapterError("ROW_ID", "row_id")
    return SourceRowId(match.group(1), match.group(2), int(match.group(3)))


@dataclass(frozen=True)
class AdultRecord:
    """Ordered raw tokens (``None`` = natural or injected missing) under a source-qualified id.

    There is deliberately no label slot: allocation and masking cannot see an outcome.
    """

    row_id: str
    tokens: tuple[str | None, ...]

    def __post_init__(self) -> None:
        parse_row_id(self.row_id)
        immutable_tuple(self.tokens, "tokens")
        if len(self.tokens) != FEATURE_COUNT:
            raise AdultAdapterError("TOKEN_COUNT", "tokens")
        if any(token is not None and type(token) is not str for token in self.tokens):
            raise AdultAdapterError("TOKEN_TYPE", "tokens")

    @property
    def source(self) -> SourceRowId:
        return parse_row_id(self.row_id)


def record_from_raw_fields(
    row_id: str,
    fields: Mapping[str, Any],
    contract: AdultFeatureContract = ADULT_FEATURE_CONTRACT,
) -> AdultRecord:
    """Build a record from raw token strings keyed by the 13 predictor names.

    Mirrors the parser's token rules (strip whitespace, ``?`` -> null, keep every other spelling)
    without parsing numerics, so group keys keep the exact spelling. Any key outside the
    contract, including ``income`` and ``education``, is rejected rather than ignored.
    """
    parse_row_id(row_id)
    unexpected = sorted(set(fields) - set(contract.features))
    if unexpected:
        raise AdultAdapterError("UNEXPECTED_FIELD", ",".join(map(str, unexpected)))
    missing = [name for name in contract.features if name not in fields]
    if missing:
        raise AdultAdapterError("MISSING_FIELD", ",".join(missing))
    tokens: list[str | None] = []
    for name in contract.features:
        raw = fields[name]
        if type(raw) is not str:
            raise AdultAdapterError("TOKEN_TYPE", name)
        token = raw.strip()
        if not token:
            raise AdultAdapterError("EMPTY_TOKEN", name)
        tokens.append(None if token == contract.natural_missing_token else token)
    return AdultRecord(row_id, tuple(tokens))
