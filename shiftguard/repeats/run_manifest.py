"""Gate 8 precondition 3: the frozen, digest-bound run manifest ``gate8-run-manifest-v1``.

The manifest fixes the exact source, dataset hashes, configuration, roles and schedule before
any real coordinate runs. It is generic over the binding: it is built from a ``RepeatPlan``,
so fabricated fixtures and the verified Bank development binding use the same code. Building
or verifying a manifest executes no coordinate, fits nothing and computes no loss.

Nothing here reviews, approves or locks the protocol, grants SCI-03 authority or makes any
Bank result confirmatory. Every manifest carries the development label.

What each ``build_development_binding`` digest covers (the field names are fixed by
``SourceBinding``; the coverage is decided here):

* ``dataset`` / ``release`` / ``raw_sha256`` / ``clean_sha256``: the frozen Bank identity that
  ``planning`` owns (``VERIFIED_BANK_*``); the dataset object must already carry exactly the
  frozen raw and clean hashes, and its rows must re-hash to the clean hash.
* ``feature_schema_sha256``: canonical digest of the declared feature schema, that is the
  ordered ``BANK_FEATURES`` and ``FEATURE_GROUP_VERSION``.
* ``group_manifest_sha256``: canonical digest of the ordered ``(source_row_id,
  feature_group_id)`` pairs (ordered by row id). Feature-only; no label, mask or split enters.
* ``source_sha256``: canonical digest of the source tree entries (``source_tree_entries``):
  git-normalized blob ids (``git hash-object``, so CRLF checkouts hash like the commit) of the
  run's import closure, that is ``shiftguard/__init__.py``, the packages in
  ``SOURCE_PACKAGES``, the two Gate 8 scripts, ``pyproject.toml`` and ``uv.lock``.
* ``dependency_lock_sha256``: SHA-256 of the bytes of ``uv.lock`` with CRLF read as LF.
* ``protocol_review_sha256``: canonical digest over the (file name, SHA-256 of bytes) of each
  protocol file given. The coordinator pins only SCIENTIFIC_DECISIONS.md here. It only pins
  those bytes; it does not claim the protocol is reviewed. The authorization file is a status
  document whose checkboxes change, so its hash at freeze time is recorded in the separate
  provenance field ``authorization_sha256_at_freeze`` and is never re-verified against the live
  file.

The manifest never contains row ids, group ids, labels, losses or paired sums: roles appear as
digests and counts, the schedule as repeat ids and seed-map digests.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
from typing import Any

from shiftguard.datasets.bank import BANK_FEATURES, BankDataset, hash_clean_rows
from shiftguard.repeats import development_store as store
from shiftguard.repeats import planning
from shiftguard.repeats.development_adapter import (
    EXECUTION_TIER,
    FEATURE_GROUP_VERSION,
    SPLIT_PROFILE,
    claim_scope_for,
    feature_group_id,
    source_row_id,
)
from shiftguard.repeats.models import (
    DEVELOPMENT_EXPOSURE,
    PAIRED_CELL_RECORD_VERSION,
    PREDICTORS,
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    TERMINAL_CONDITION_RECORD_VERSION,
    RepeatContractError,
    RepeatPlan,
    SourceBinding,
    canonical_digest,
    canonical_json,
)
from shiftguard.repeats.planning import (
    ensure_planned,
    is_verified_bank_development,
    require_authorized_source,
)
from shiftguard.repeats.seeds import seed_plan_digest


MANIFEST_SCHEMA = "gate8-run-manifest-v1"
MANIFEST_LABEL = "development; Bank outcomes previously inspected; not confirmatory"
DEFAULT_STORE_ROOT_RELATIVE = "var/gate8-private/bank-development-v1"
DEFAULT_MANIFEST_RELATIVE = "docs/research/gate8-run-manifest-bank-development-v1.json"
OWNER_ACTIONS_RELATIVE = ".agent/OWNER_ACTIONS.md"
BANK_DATASET_CSV_RELATIVE = "var/datasets/bank.csv"
BANK_DATASET_MANIFEST_RELATIVE = "var/datasets/bank.manifest.json"
EARLIEST_RUN_DATE = date(2026, 10, 20)  # Asia/Kolkata local date (authorization, precondition 5)
KOLKATA = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")  # no daylight saving

_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_STORE_PREFIX = "var/gate8-private/"
_PROVISIONAL = "0" * 64
_BLOB = re.compile(r"[0-9a-f]{40}")
# Any spelling of "gate 8: no" anywhere in the owner actions file is a veto.
_VETO = re.compile(r"gate[\s_-]*8\s*[:\uff1a\-\u2013\u2014]?\s*no\b", re.IGNORECASE)
# The one place OWNER_ACTIONS item 9 itself quotes the veto phrase, as an instruction to the owner.
_VETO_INSTRUCTION = re.compile(
    r"write\s+[\"'\u201c\u201d]gate8:\s*no[\"'\u201c\u201d]\s+here", re.IGNORECASE)
_ITEM_NINE = re.compile(r"^[ \t]*9\.[ \t]+\*\*Gate 8\b", re.MULTILINE)
_NEXT_ITEM = re.compile(r"^[ \t]*\d+\.[ \t]+\*\*", re.MULTILINE)
_STATUS = re.compile(r"^[ \t]*Status:", re.MULTILINE)
_AFFIRMATIVE = re.compile(
    r"(?:yes|ok|okay|go|proceed|allowed|gate8:\s*yes)[\s.!]*", re.IGNORECASE)
SOURCE_PACKAGES = (
    "calibration", "datasets", "experiments", "metrics", "missingness", "predictors",
    "preprocessing", "protocol", "repeats",
)
SOURCE_SCRIPTS = ("scripts/gate8_freeze_run_manifest.py", "scripts/gate8_run_development.py")
ENVIRONMENT_PACKAGES = ("numpy", "scipy", "scikit-learn")

MANIFEST_KEYS = (
    "analysis", "authorization_sha256_at_freeze", "binding", "binding_digest", "claim_scope",
    "dataset_manifest_sha256", "dependency_lock_sha256", "environment", "execution_tier", "label",
    "manifest_digest", "plan_digest",
    "primary_contrast", "roles", "schedule", "schema", "seed_plan_digest", "source_commit",
    "source_tree", "source_tree_digest", "spec", "spec_digest", "split_profile",
    "store_record_versions", "store_root_relative",
)
# The failure code of a mismatch, by manifest key. Keys not listed are declarations.
_MISMATCH_CODE = {
    "plan_digest": "MANIFEST_PLAN", "seed_plan_digest": "MANIFEST_PLAN",
    "execution_tier": "MANIFEST_PLAN", "split_profile": "MANIFEST_PLAN",
    "claim_scope": "MANIFEST_PLAN",
    "schedule": "MANIFEST_SCHEDULE", "roles": "MANIFEST_ROLES",
    "spec": "MANIFEST_SPEC", "spec_digest": "MANIFEST_SPEC",
    "binding": "MANIFEST_BINDING", "binding_digest": "MANIFEST_BINDING",
    "store_root_relative": "MANIFEST_STORE_ROOT",
    "source_tree_digest": "MANIFEST_SOURCE_TREE",
    "schema": "MANIFEST_SCHEMA", "label": "MANIFEST_SCHEMA",
    "environment": "MANIFEST_ENVIRONMENT",
}


# ------------------------------------------------------------------ git and the source tree

def _git(repo_root: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={Path(repo_root).resolve().as_posix()}",
             "-C", str(repo_root), *args],
            capture_output=True, check=False, input=stdin,
        )
    except OSError as error:
        raise RepeatContractError("GIT_UNAVAILABLE", type(error).__name__) from None


def _git_ok(repo_root: Path, *args: str) -> bytes:
    done = _git(repo_root, *args)
    if done.returncode != 0:
        raise RepeatContractError("GIT_FAILED", args[0])
    return done.stdout


def _require_repo_top(repo_root: Path) -> None:
    if _git_ok(repo_root, "rev-parse", "--show-prefix").strip():
        raise RepeatContractError("SOURCE_REPO", "repo_root is not the top of its git repository")


def is_source_path(path: str) -> bool:
    """Whether a repository-relative posix path is part of the frozen source scope."""
    if path in ("pyproject.toml", "uv.lock", "shiftguard/__init__.py") or path in SOURCE_SCRIPTS:
        return True
    return any(path.startswith(f"shiftguard/{package}/") for package in SOURCE_PACKAGES)


def head_commit(repo_root: Path) -> str:
    commit = _git_ok(Path(repo_root), "rev-parse", "HEAD").decode("ascii").strip()
    if _COMMIT.fullmatch(commit) is None:
        raise RepeatContractError("SOURCE_COMMIT", "HEAD")
    return commit


def source_tree_entries(repo_root: Path) -> list[dict[str, str]]:
    """Sorted ``{path, blob}`` of every tracked source file.

    ``blob`` is the git-normalized blob id of the working-copy file (``git hash-object`` applies
    the path's eol/clean filters), so a CRLF checkout hashes like the commit it came from.
    """
    repo_root = Path(repo_root)
    _require_repo_top(repo_root)
    listed = _git_ok(repo_root, "ls-files", "-z").split(b"\0")
    paths = sorted({item.decode("utf-8") for item in listed if item})
    paths = [path for path in paths if is_source_path(path)]
    for path in paths:
        if not (repo_root / path).is_file():
            raise RepeatContractError("SOURCE_FILE_MISSING", path)
    if "uv.lock" not in paths:
        raise RepeatContractError("SOURCE_FILE_MISSING", "uv.lock")
    hashed = _git(
        repo_root, "hash-object", "--stdin-paths", stdin=("\n".join(paths) + "\n").encode("utf-8"))
    blobs = hashed.stdout.decode("ascii", "replace").split()
    if hashed.returncode != 0 or len(blobs) != len(paths) or any(
        _BLOB.fullmatch(blob) is None for blob in blobs
    ):
        raise RepeatContractError("GIT_FAILED", "hash-object")
    return [{"path": path, "blob": blob} for path, blob in zip(paths, blobs)]


def committed_source_entries(repo_root: Path, commit: str) -> dict[str, str]:
    """The source scope as committed: ``git ls-tree -r`` of one commit, path to blob id."""
    listing = _git(Path(repo_root), "ls-tree", "-r", "-z", commit)
    if listing.returncode != 0:
        raise RepeatContractError("MANIFEST_SOURCE_COMMIT", "source_commit cannot be read")
    found: dict[str, str] = {}
    for item in listing.stdout.split(b"\0"):
        if not item:
            continue
        meta, _, path = item.partition(b"\t")
        fields = meta.split()
        name = path.decode("utf-8")
        if len(fields) == 3 and fields[1] == b"blob" and is_source_path(name):
            found[name] = fields[2].decode("ascii")
    return found


def dependency_lock_sha256(repo_root: Path) -> str:
    try:
        data = (Path(repo_root) / "uv.lock").read_bytes()
    except OSError:
        raise RepeatContractError("SOURCE_FILE_MISSING", "uv.lock") from None
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def current_environment() -> dict[str, Any]:
    packages = {}
    for name in ENVIRONMENT_PACKAGES:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "absent"
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
    }


def source_tree_digest(entries: list[dict[str, str]]) -> str:
    return canonical_digest(["gate8-source-tree-v1", _checked_tree(entries)])


def _checked_tree(entries: Any) -> list[dict[str, str]]:
    if type(entries) is not list or not entries:
        raise RepeatContractError("MANIFEST_SOURCE_FIELDS", "source_tree")
    previous = None
    for entry in entries:
        if (
            type(entry) is not dict or set(entry) != {"path", "blob"}
            or type(entry["path"]) is not str or type(entry["blob"]) is not str
            or _BLOB.fullmatch(entry["blob"]) is None
            or not entry["path"] or "\\" in entry["path"] or entry["path"].startswith("/")
            or ".." in entry["path"].split("/")
        ):
            raise RepeatContractError("MANIFEST_SOURCE_FIELDS", "source_tree entry")
        if previous is not None and entry["path"] <= previous:
            raise RepeatContractError("MANIFEST_SOURCE_FIELDS", "source_tree order")
        previous = entry["path"]
    return entries


def dirty_source_paths(repo_root: Path) -> list[str]:
    """Source paths with any change, staged, unstaged, untracked, renamed or deleted."""
    repo_root = Path(repo_root)
    _require_repo_top(repo_root)
    parts = _git_ok(repo_root, "status", "--porcelain", "-z", "--untracked-files=all").split(b"\0")
    dirty: list[str] = []
    index = 0
    while index < len(parts):
        entry = parts[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2].decode("ascii"), entry[3:].decode("utf-8")
        dirty.append(path)
        if ("R" in status or "C" in status) and index < len(parts):
            dirty.append(parts[index].decode("utf-8"))
            index += 1
    return sorted({path for path in dirty if is_source_path(path)})


def require_clean_source(repo_root: Path) -> None:
    dirty = dirty_source_paths(repo_root)
    if dirty:
        raise RepeatContractError("SOURCE_DIRTY", f"{len(dirty)} source path(s), first: {dirty[0]}")


# ------------------------------------------------------------------ run permission

def kolkata_today(now: datetime | None = None) -> date:
    moment = datetime.now(timezone.utc) if now is None else now
    return moment.astimezone(KOLKATA).date()


def owner_veto_state(text: str) -> str | None:
    """None when the owner has not vetoed, otherwise a short reason. Fails closed.

    Item 9 is located by its heading; a missing item or ``Status:`` line is a veto. Any
    non-empty status text is a veto unless it is an explicit affirmative. Independently, any
    spelling of "gate 8: no" anywhere (outside the item's own instruction sentence) is a veto.
    """
    stripped = _VETO_INSTRUCTION.sub("", text)
    if _VETO.search(stripped):
        return "gate 8: no"
    heading = _ITEM_NINE.search(stripped)
    if heading is None:
        return "item 9 not found"
    following = _NEXT_ITEM.search(stripped, heading.end())
    item = stripped[heading.start(): following.start() if following else len(stripped)]
    status = _STATUS.search(item)
    if status is None:
        return "item 9 has no Status line"
    answer = item[status.end():].strip()
    if answer and _AFFIRMATIVE.fullmatch(answer) is None:
        return "item 9 status is not an explicit affirmative"
    return None


def owner_veto_present(text: str) -> bool:
    return owner_veto_state(text) is not None


def require_run_permitted(
    repo_root: Path, *, today: date | None = None, date_gate: bool = True
) -> None:
    """Authorization precondition 5: the date gate and the owner veto (fails closed)."""
    if date_gate:
        current = kolkata_today() if today is None else today
        if current < EARLIEST_RUN_DATE:
            raise RepeatContractError("DATE_GATE", f"no run before {EARLIEST_RUN_DATE.isoformat()}")
    path = Path(repo_root) / OWNER_ACTIONS_RELATIVE
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise RepeatContractError("OWNER_VETO", "owner actions file unreadable (fails closed)") from None
    reason = owner_veto_state(text)
    if reason is not None:
        raise RepeatContractError("OWNER_VETO", reason)


def require_tracked_unmodified(repo_root: Path, path: Path) -> None:
    """The manifest must be inside the repository, git-tracked and identical to HEAD."""
    repo_root = Path(repo_root)
    try:
        relative = Path(path).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        raise RepeatContractError("MANIFEST_OUTSIDE_REPO", Path(path).name) from None
    if _git(repo_root, "ls-files", "--error-unmatch", "--", relative).returncode != 0:
        raise RepeatContractError("MANIFEST_UNTRACKED", Path(path).name)
    if _git(repo_root, "diff", "--quiet", "HEAD", "--", relative).returncode != 0:
        raise RepeatContractError("MANIFEST_MODIFIED", Path(path).name)


# ------------------------------------------------------------------ binding

def _file_sha256(path: Path, code: str) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        raise RepeatContractError(code, Path(path).name) from None


def feature_schema_digest() -> str:
    return canonical_digest(["gate8-feature-schema-v1", list(BANK_FEATURES), FEATURE_GROUP_VERSION])


def protocol_review_digest(protocol_paths: Any) -> str:
    paths = [Path(item) for item in protocol_paths]
    if not paths:
        raise RepeatContractError("PROTOCOL_FILES", "none given")
    names = [path.name for path in paths]
    if len(set(names)) != len(names):
        raise RepeatContractError("PROTOCOL_FILES", "duplicate file name")
    pairs = sorted([path.name, _file_sha256(path, "PROTOCOL_FILES")] for path in paths)
    return canonical_digest(["gate8-protocol-files-v1", pairs])


def build_development_binding(
    dataset: BankDataset, *, repo_root: Path, protocol_paths: Any
) -> SourceBinding:
    """The development_exposed binding of the verified Bank release (see the module docstring)."""
    repo_root = Path(repo_root)
    if type(dataset) is not BankDataset or not dataset.rows:
        raise RepeatContractError("DATASET_SCHEMA", "dataset")
    if (
        dataset.raw_hash != planning.VERIFIED_BANK_RAW_SHA256
        or dataset.clean_hash != planning.VERIFIED_BANK_CLEAN_SHA256
    ):
        raise RepeatContractError("SOURCE_BINDING_MISMATCH", "dataset is not the verified Bank release")
    if hash_clean_rows(dataset.rows) != dataset.clean_hash:
        raise RepeatContractError("SOURCE_BINDING_MISMATCH", "rows do not hash to the clean digest")
    schema = feature_schema_digest()
    provisional = SourceBinding(
        dataset=planning.VERIFIED_BANK_DATASET, release=planning.VERIFIED_BANK_RELEASE,
        raw_sha256=dataset.raw_hash, clean_sha256=dataset.clean_hash,
        feature_schema_sha256=schema, group_manifest_sha256=_PROVISIONAL,
        source_sha256=_PROVISIONAL, dependency_lock_sha256=_PROVISIONAL,
        protocol_review_sha256=_PROVISIONAL, exposure_status=DEVELOPMENT_EXPOSURE,
    )
    pairs, seen = [], set()
    for row in sorted(dataset.rows, key=lambda item: item.get("row_id", -1)):
        row_id = row.get("row_id")
        if type(row_id) is not int or row_id in seen:
            raise RepeatContractError("DATASET_SCHEMA", "row_id")
        seen.add(row_id)
        pairs.append([source_row_id(provisional, row_id), feature_group_id(row, schema)])
    entries = source_tree_entries(repo_root)
    binding = SourceBinding(
        dataset=provisional.dataset, release=provisional.release,
        raw_sha256=provisional.raw_sha256, clean_sha256=provisional.clean_sha256,
        feature_schema_sha256=schema,
        group_manifest_sha256=canonical_digest(
            ["gate8-group-manifest-v1", FEATURE_GROUP_VERSION, schema, pairs]),
        source_sha256=source_tree_digest(entries),
        dependency_lock_sha256=dependency_lock_sha256(repo_root),
        protocol_review_sha256=protocol_review_digest(protocol_paths),
        exposure_status=DEVELOPMENT_EXPOSURE,
    )
    return require_authorized_source(binding)


def load_verified_bank_dataset(repo_root: Path) -> tuple[BankDataset, str]:
    """The repository's normal verified loader. Returns the dataset and its manifest file hash."""
    root = Path(repo_root)
    manifest_path = root / BANK_DATASET_MANIFEST_RELATIVE
    raw = manifest_path.read_bytes()
    dataset = BankDataset.from_clean_csv(root / BANK_DATASET_CSV_RELATIVE, json.loads(raw))
    return dataset, hashlib.sha256(raw).hexdigest()


def default_protocol_paths(repo_root: Path) -> tuple[Path, ...]:
    """The protocol files the binding pins: SCIENTIFIC_DECISIONS.md only."""
    return (Path(repo_root).parent / "research" / "gate8-20261009" / "SCIENTIFIC_DECISIONS.md",)


def default_authorization_path(repo_root: Path) -> Path:
    """A status document: hashed once at freeze time, never re-verified against the live file."""
    return (
        Path(repo_root).parent / "research" / "gate8-20261009"
        / "AUTHORIZATION-20261017-bank-development-repeats.md"
    )


def authorization_sha256(path: Path) -> str:
    return _file_sha256(path, "PROTOCOL_FILES")


# ------------------------------------------------------------------ the manifest

def _store_record_versions() -> dict[str, str]:
    return {
        "store_schema": store.STORE_SCHEMA,
        "coordinate_record": store.COORDINATE_RECORD_VERSION,
        "compact_cell_record": store.COMPACT_CELL_RECORD_VERSION,
        "compact_context_record": store.COMPACT_CONTEXT_RECORD_VERSION,
        "compact_pair_record": store.COMPACT_PAIR_RECORD_VERSION,
        "plan_owned_digest": store.PLAN_OWNED_DIGEST_VERSION,
        "terminal_condition_record": TERMINAL_CONDITION_RECORD_VERSION,
        "cell_record": PAIRED_CELL_RECORD_VERSION,
        "feature_group": FEATURE_GROUP_VERSION,
    }


def _primary_contrast() -> dict[str, Any]:
    return {
        "contrast": f"{PRIMARY_TARGET_METHOD} minus {PRIMARY_SOURCE_METHOD}",
        "target_method": PRIMARY_TARGET_METHOD,
        "source_method": PRIMARY_SOURCE_METHOD,
        "budget": PRIMARY_BUDGET,
        "metric": "binary_brier",
        "predictors": list(PREDICTORS),
        "scenarios": list(PRIMARY_SCENARIOS),
        "cell_count": len(PREDICTORS) * len(PRIMARY_SCENARIOS),
        "cell_weight": "1/8",
    }


def _analysis() -> dict[str, Any]:
    return {
        "interval": "conditional_group_bootstrap",
        "sensitivity_summaries": ["split_profile", "seed"],
        "split_profile": SPLIT_PROFILE,
        "outer_first_bootstrap_claimed": False,
        "hypothesis_decision_supported": False,
        "coverage_claim_supported": False,
        "qualification_while_sci03_unresolved": "unknown_authority",
        "primary_estimate_expected": "MissingEvidence",
    }


def _checked_store_root(value: Any) -> str:
    if (
        type(value) is not str or not value.startswith(_STORE_PREFIX) or value == _STORE_PREFIX
        or "\\" in value or value.endswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise RepeatContractError("MANIFEST_STORE_ROOT", "store root must be inside var/gate8-private/")
    return value


def seal_manifest(unsealed: dict[str, Any]) -> dict[str, Any]:
    """Attach the digest of everything else."""
    body = {key: value for key, value in unsealed.items() if key != "manifest_digest"}
    return {**body, "manifest_digest": canonical_digest(body)}


def _checked_environment(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"python", "implementation", "platform", "packages"}
        or any(type(value[key]) is not str for key in ("python", "implementation", "platform"))
        or type(value["packages"]) is not dict
        or set(value["packages"]) != set(ENVIRONMENT_PACKAGES)
        or any(type(item) is not str for item in value["packages"].values())
    ):
        raise RepeatContractError("MANIFEST_ENVIRONMENT", "malformed environment record")
    return value


def build_run_manifest(
    plan: RepeatPlan,
    *,
    source_commit: str,
    source_tree: list[dict[str, str]],
    dependency_lock_sha256: str,
    dataset_manifest_sha256: str,
    store_root_relative: str,
    authorization_sha256: str,
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_planned(plan)
    binding = require_authorized_source(plan.binding)
    if type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None:
        raise RepeatContractError("MANIFEST_SOURCE_FIELDS", "source_commit")
    tree = _checked_tree(source_tree)
    tree_digest = source_tree_digest(tree)
    for name, value in (
        ("dependency_lock_sha256", dependency_lock_sha256),
        ("dataset_manifest_sha256", dataset_manifest_sha256),
        ("authorization_sha256", authorization_sha256),
    ):
        if type(value) is not str or _SHA256.fullmatch(value) is None:
            raise RepeatContractError("MANIFEST_SOURCE_FIELDS", name)
    if "uv.lock" not in {entry["path"] for entry in tree}:
        raise RepeatContractError("MANIFEST_DEPENDENCY_LOCK", "the source tree has no uv.lock entry")
    environment = _checked_environment(current_environment() if environment is None else environment)
    if is_verified_bank_development(binding) and (
        binding.source_sha256 != tree_digest
        or binding.dependency_lock_sha256 != dependency_lock_sha256
    ):
        raise RepeatContractError("MANIFEST_BINDING", "binding does not describe this source tree")
    spec = plan.spec
    roles = []
    for role in plan.outer_roles:
        roles.append({
            "outer_seed": role.outer_seed,
            "role_manifest_digest": role.digest,
            "split_profile": role.split_profile,
            "counts": {
                "train": role.train_count, "source_cal": role.source_cal_count,
                "target_pool": role.target_pool_count, "evaluation": len(role.evaluation_ids),
                "evaluation_group_count": len(set(role.evaluation_groups)),
            },
            "evaluation_order_digest": role.evaluation_order_digest,
        })
    schedule = [
        {
            "outer_seed": item.key.outer_seed, "inner_id": item.key.inner_id,
            "repeat_id": item.repeat_id, "seed_map_digest": item.seed_map.digest,
        }
        for item in plan.repeats
    ]
    return seal_manifest({
        "schema": MANIFEST_SCHEMA,
        "label": MANIFEST_LABEL,
        "execution_tier": EXECUTION_TIER,
        "split_profile": SPLIT_PROFILE,
        "claim_scope": claim_scope_for(binding),
        "source_commit": source_commit,
        "source_tree": [dict(entry) for entry in tree],
        "source_tree_digest": tree_digest,
        "dependency_lock_sha256": dependency_lock_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "authorization_sha256_at_freeze": authorization_sha256,
        "environment": environment,
        "binding": binding.to_canonical(),
        "binding_digest": binding.digest,
        "spec": spec.to_canonical(),
        "spec_digest": spec.digest,
        "seed_plan_digest": seed_plan_digest(spec),
        "roles": roles,
        "schedule": schedule,
        "plan_digest": plan.plan_digest,
        "store_record_versions": _store_record_versions(),
        "primary_contrast": _primary_contrast(),
        "analysis": _analysis(),
        "store_root_relative": _checked_store_root(store_root_relative),
    })


def dump_manifest(manifest: dict[str, Any]) -> bytes:
    """Canonical sorted-key ASCII JSON with one trailing newline; identical inputs, identical bytes."""
    return (canonical_json(manifest) + "\n").encode("ascii")


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise RepeatContractError("MANIFEST_UNREADABLE", Path(path).name) from None
    if type(value) is not dict:
        raise RepeatContractError("MANIFEST_KEYS", "not an object")
    try:
        canonical = dump_manifest(value)
    except (TypeError, ValueError):
        raise RepeatContractError("MANIFEST_NOT_CANONICAL", Path(path).name) from None
    if canonical != raw:
        raise RepeatContractError("MANIFEST_NOT_CANONICAL", Path(path).name)
    return value


def verify_run_manifest(
    manifest: dict[str, Any],
    plan: RepeatPlan,
    *,
    repo_root: Path,
    dataset_manifest_sha256: str | None = None,
    check_environment: bool = True,
) -> None:
    """Recompute everything and compare; any mismatch is a typed ``RepeatContractError``.

    ``authorization_sha256_at_freeze`` is provenance only: it is digest-bound in the manifest but
    deliberately not compared with the live authorization file.
    """
    if type(manifest) is not dict or set(manifest) != set(MANIFEST_KEYS):
        raise RepeatContractError("MANIFEST_KEYS", "unknown or missing top-level key")
    body = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    try:
        recomputed = canonical_digest(body)
    except (TypeError, ValueError):
        raise RepeatContractError("MANIFEST_DIGEST", "not canonical JSON") from None
    if manifest["manifest_digest"] != recomputed:
        raise RepeatContractError("MANIFEST_DIGEST", "manifest_digest does not match the contents")
    expected = build_run_manifest(
        plan,
        source_commit=manifest["source_commit"],
        source_tree=manifest["source_tree"],
        dependency_lock_sha256=manifest["dependency_lock_sha256"],
        dataset_manifest_sha256=manifest["dataset_manifest_sha256"],
        store_root_relative=manifest["store_root_relative"],
        authorization_sha256=manifest["authorization_sha256_at_freeze"],
        environment=manifest["environment"],
    )
    for key in MANIFEST_KEYS:
        # manifest_digest was self-checked above; it follows from every other key matching.
        if key != "manifest_digest" and canonical_json(expected[key]) != canonical_json(manifest[key]):
            raise RepeatContractError(_MISMATCH_CODE.get(key, "MANIFEST_DECLARATION"), key)
    if dataset_manifest_sha256 is not None and dataset_manifest_sha256 != manifest[
        "dataset_manifest_sha256"
    ]:
        raise RepeatContractError("MANIFEST_DATASET", "dataset manifest file hash differs")
    if check_environment and manifest["environment"] != current_environment():
        raise RepeatContractError("MANIFEST_ENVIRONMENT", "python, platform or package versions differ")
    repo_root = Path(repo_root)
    frozen = {entry["path"]: entry["blob"] for entry in manifest["source_tree"]}
    if not all(is_source_path(path) for path in frozen):
        raise RepeatContractError("MANIFEST_SOURCE_FIELDS", "source_tree path outside the source scope")
    ancestor = _git(repo_root, "merge-base", "--is-ancestor", manifest["source_commit"], "HEAD")
    if ancestor.returncode != 0:
        raise RepeatContractError("MANIFEST_SOURCE_COMMIT", "source_commit is not an ancestor of HEAD")
    if committed_source_entries(repo_root, manifest["source_commit"]) != frozen:
        raise RepeatContractError(
            "MANIFEST_SOURCE_COMMIT", "the frozen tree is not the tree of source_commit")
    current = {entry["path"]: entry["blob"] for entry in source_tree_entries(repo_root)}
    if current != frozen:
        differing = sorted(path for path in set(current) | set(frozen) if current.get(path) != frozen.get(path))
        raise RepeatContractError(
            "MANIFEST_SOURCE_DRIFT", f"{len(differing)} path(s), first: {differing[0]}")
    if dependency_lock_sha256(repo_root) != manifest["dependency_lock_sha256"]:
        raise RepeatContractError("MANIFEST_DEPENDENCY_LOCK", "uv.lock differs from the frozen hash")
