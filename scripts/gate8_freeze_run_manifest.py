"""Gate 8 precondition 3: freeze the run manifest for the Bank development repeats.

Requires a clean source tree, loads the verified Bank release through the repository's normal
loader, builds the development binding and the plan, and writes the canonical manifest. It
executes no coordinate and computes no loss. The date gate (no run before 20 Oct 2026,
Asia/Kolkata) and the owner veto ("gate8: no" in .agent/OWNER_ACTIONS.md) apply. Only digests,
counts and ids are printed. The output file is never overwritten.
"""

from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shiftguard.repeats import run_manifest as rm  # noqa: E402
from shiftguard.repeats.development_adapter import plan_development_repeats  # noqa: E402
from shiftguard.repeats.models import RepeatContractError  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None,
                        help=f"manifest path (default {rm.DEFAULT_MANIFEST_RELATIVE}); never overwritten")
    parser.add_argument("--store-root-relative", default=rm.DEFAULT_STORE_ROOT_RELATIVE)
    parser.add_argument("--protocol", type=Path, action="append", default=None,
                        help="protocol file to pin (repeatable); default SCIENTIFIC_DECISIONS.md")
    parser.add_argument("--authorization", type=Path, default=None,
                        help="authorization file whose hash is recorded as provenance only")
    parser.add_argument("--date-gate", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _refuse(code: str) -> int:
    print(f"refused: {code}")
    return 2


def main(
    argv: list[str] | None = None,
    *,
    dataset_loader: Callable[[Path], tuple[object, str]] | None = None,
    today: date | None = None,
    repo_root: Path | None = None,
) -> int:
    """``dataset_loader(repo_root) -> (dataset, dataset_manifest_sha256)`` is the test seam."""
    args = _parser().parse_args(argv)
    root = Path(ROOT if repo_root is None else repo_root)
    try:
        if dataset_loader is None:
            if not args.date_gate:
                raise RepeatContractError("DATE_GATE_REQUIRED", "the real dataset is never loaded without it")
            if (
                today is not None or repo_root is not None or args.out is not None or args.protocol is not None
                or args.authorization is not None
                or args.store_root_relative != rm.DEFAULT_STORE_ROOT_RELATIVE
            ):
                raise RepeatContractError(
                    "OVERRIDE_REQUIRES_LOADER", "overrides are test seams and need an injected loader")
        rm.require_run_permitted(root, today=today, date_gate=args.date_gate)
        rm.require_clean_source(root)
        out = Path(args.out) if args.out is not None else Path(rm.DEFAULT_MANIFEST_RELATIVE)
        out = out if out.is_absolute() else root / out
        try:
            relative = out.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = None
        if relative is not None and rm.is_source_path(relative):
            raise RepeatContractError("OUT_IN_SOURCE", "the manifest must not live inside the frozen source tree")
        if out.exists():
            raise RepeatContractError("OUT_EXISTS", out.name)
        protocol = args.protocol if args.protocol else rm.default_protocol_paths(root)
        dataset, dataset_manifest_sha256 = (dataset_loader or rm.load_verified_bank_dataset)(root)
        binding = rm.build_development_binding(dataset, repo_root=root, protocol_paths=protocol)
        plan = plan_development_repeats(dataset, binding)
        entries = rm.source_tree_entries(root)
        authorization = args.authorization or rm.default_authorization_path(root)
        manifest = rm.build_run_manifest(
            plan,
            source_commit=rm.head_commit(root),
            source_tree=entries,
            dependency_lock_sha256=rm.dependency_lock_sha256(root),
            dataset_manifest_sha256=dataset_manifest_sha256,
            store_root_relative=args.store_root_relative,
            authorization_sha256=rm.authorization_sha256(authorization),
        )
        rm.verify_run_manifest(
            manifest, plan, repo_root=root, dataset_manifest_sha256=dataset_manifest_sha256)
        data = rm.dump_manifest(manifest)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(out, "xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            raise RepeatContractError("OUT_EXISTS", out.name) from None
    except RepeatContractError as error:
        return _refuse(error.code)
    except Exception as error:  # noqa: BLE001  type name only; never a message that could carry data
        print(f"error: {type(error).__name__}")
        return 1
    print(f"manifest_digest {manifest['manifest_digest']}")
    print(f"plan_digest {plan.plan_digest}")
    print(
        f"coordinates {len(manifest['schedule'])} outer_seeds {len(manifest['roles'])} "
        f"source_files {len(manifest['source_tree'])}")
    print(f"written {out.name}")
    print("note: files in the source scope must not change until the campaign finishes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
