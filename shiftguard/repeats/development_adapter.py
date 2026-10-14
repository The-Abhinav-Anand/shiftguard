"""Development-tier adapter: one (outer_seed, inner_id) coordinate of the Gate 8 repeat grid.

Composes the existing deterministic Bank owners (splits, preprocessing, predictors,
missingness, calibration, evaluator) under the gate8-nested-v1 seed map and reduces the
result into the typed repeat contracts. It is synthetic-gated: any source binding whose
exposure status is not ``synthetic_fabricated`` is refused, so real Bank execution needs
a later, separately authorized step. Nothing here sets or implies confirmatory status.

Final-test labels enter only ``_EvaluatorPrivateGroupScorer``, which keeps them inside
``FinalTestEvaluator`` instances. No label-derived row-level value is returned or logged.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

import numpy as np

from shiftguard.calibration.base import CalibrationRecord
from shiftguard.calibration.beta import fit_beta_calibration
from shiftguard.calibration.fraction_binned import fit_source_fraction_binned_temperature
from shiftguard.calibration.platt_logodds import fit_platt_logodds
from shiftguard.calibration.sklearn_maps import (
    CalibrationFit,
    fit_isotonic_calibration,
    fit_temperature,
    frozen_pipeline,
    predict_conditions_with_fallback,
)
from shiftguard.calibration.source_remask import (
    fit_source_remasked_temperature,
    generate_source_remasked_dataset,
)
from shiftguard.datasets.bank import BANK_FEATURES, TARGET_COLUMN, BankDataset
from shiftguard.experiments.evaluator import FinalTestEvaluator
from shiftguard.missingness.block import history_block_mask
from shiftguard.missingness.mcar import (
    compute_matched_mcar,
    generate_mcar_mask,
    generate_shared_uniforms,
)
from shiftguard.predictors.logistic import fit_initial_logistic_regression, predictor_identity
from shiftguard.predictors.random_forest import (
    fit_initial_random_forest,
    fitted_rf_state,
    random_forest_identity,
)
from shiftguard.preprocessing.tabular import (
    feature_rows,
    fit_train_preprocessor,
    fit_tree_preprocessor,
    preprocessing_config,
)
from shiftguard.protocol.acquisition import LabelBlindTargetProvider
from shiftguard.protocol.splits import make_role_splits
from shiftguard.repeats.models import (
    BUDGETS,
    FALLBACK_GRAPH,
    METHODS,
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    SCENARIOS,
    SYNTHETIC_CLAIM_SCOPE,
    SYNTHETIC_EXPOSURE,
    OuterRoleManifest,
    PairContext,
    PairedGroupLossCell,
    ProbabilityArray,
    RepeatContractError,
    RepeatKey,
    RepeatPlan,
    RepeatSpec,
    SeedMap,
    SourceBinding,
    TerminalCondition,
    ValidatedPair,
    canonical_digest,
    declared_repeat,
    digest_field,
    identifier_tuple,
    immutable_tuple,
)
from shiftguard.repeats.planning import (
    ensure_planned,
    pair_context_for,
    plan_owned_mismatch,
    plan_repeats,
)
from shiftguard.repeats.seeds import derive_repeat_seed_map
from shiftguard.repeats.validation import (
    expected_condition_slots,
    validate_condition_accounting,
    validate_probability_pair,
)


FEATURE_GROUP_VERSION = "gate8-feature-group-v1"
# Bank keeps its legacy 55/15/10/20 row-stratified split per outer repeat (SCIENTIFIC_DECISIONS 4).
SPLIT_PROFILE = "bank_overlap_diagnostic"
EXECUTION_TIER = "development"
HISTORY_ROW_PROBABILITY = 0.50
_TARGET_FITTERS = {
    "target_temperature": lambda *a: fit_temperature(*a, "target_temperature"),
    "target_platt_logodds": lambda *a: fit_platt_logodds(*a),
    "target_beta": lambda *a: fit_beta_calibration(*a),
    "target_isotonic": lambda *a: fit_isotonic_calibration(*a),
}
# The binned map names its own bin-level resolution differently from the declared methods.
_BIN_RESOLUTION_NAMES = {"fitted_bin_temperature": PRIMARY_SOURCE_METHOD}
_SAFE_CODE = re.compile(r"[^A-Za-z0-9_.-]")


# ------------------------------------------------------------------ gating and validation

def _require_synthetic(binding: object) -> SourceBinding:
    if type(binding) is not SourceBinding:
        raise RepeatContractError("REPEAT_SCHEMA", "binding")
    # Real Bank development execution needs its own authorization; this adapter never runs it.
    if binding.exposure_status != SYNTHETIC_EXPOSURE:
        raise RepeatContractError("SYNTHETIC_ONLY", binding.exposure_status)
    return binding


def _qualification(binding: SourceBinding) -> str:
    # SCI-03 authority is not approved, so a real source would be "unknown_authority". Only the
    # synthetic binding may declare a cell "qualified", and only for engineering fixtures.
    return "qualified" if binding.exposure_status == SYNTHETIC_EXPOSURE else "unknown_authority"


def source_row_id(binding: SourceBinding, row_id: int) -> str:
    return f"{binding.release}:{binding.dataset}:{row_id}"


def feature_group_id(row: dict, schema_digest: str) -> str:
    """Label-blind exact-feature group key; row ID, label, masks and encodings never enter."""
    digest_field(schema_digest, "feature_schema_sha256")
    tokens = []
    for feature in BANK_FEATURES:
        token = row.get(feature)
        # Raw tokens only: Bank's literal unknown, 999 and nonexistent are values, not nulls.
        if token is not None and type(token) is not str:
            raise RepeatContractError("FEATURE_TOKEN", feature)
        tokens.append(token)
    return canonical_digest([FEATURE_GROUP_VERSION, schema_digest, tokens])


def _validated_rows(dataset: object, binding: SourceBinding) -> tuple[dict, dict[int, str]]:
    if type(dataset) is not BankDataset or not dataset.rows:
        raise RepeatContractError("DATASET_SCHEMA", "dataset")
    if dataset.raw_hash != binding.raw_sha256 or dataset.clean_hash != binding.clean_sha256:
        raise RepeatContractError("SOURCE_BINDING_MISMATCH", binding.dataset)
    rows_by_id: dict[int, dict] = {}
    groups: dict[int, str] = {}
    for row in dataset.rows:
        row_id = row.get("row_id")
        if type(row_id) is not int or row_id in rows_by_id:
            raise RepeatContractError("DATASET_SCHEMA", "row_id")
        if type(row.get(TARGET_COLUMN)) is not int or row[TARGET_COLUMN] not in (0, 1):
            raise RepeatContractError("DATASET_SCHEMA", TARGET_COLUMN)
        rows_by_id[row_id] = row
        groups[row_id] = feature_group_id(row, binding.feature_schema_sha256)
    return rows_by_id, groups


def _scope(values: object, declared: tuple, name: str) -> tuple:
    kind = type(declared[0])
    if (
        type(values) is not tuple or not values
        or any(type(item) is not kind or item not in declared for item in values)
        or [declared.index(item) for item in values] != sorted({declared.index(i) for i in values})
    ):
        raise RepeatContractError("ALTERED_GRID", name)
    return values


# ------------------------------------------------------------------ outer roles and plan

def _split_roles(rows: list[dict], spec: RepeatSpec, outer_seed: int) -> dict[str, tuple[int, ...]]:
    seeds = dict(derive_repeat_seed_map(RepeatKey(outer_seed, spec.inner_ids[0]), spec).seeds)
    # Split streams belong to the outer seed; the splitter consumes split, split+1 and split+2.
    return make_role_splits(rows, seeds["split"])


def _outer_manifest(
    rows: list[dict],
    groups: dict[int, str],
    binding: SourceBinding,
    spec: RepeatSpec,
    outer_seed: int,
) -> OuterRoleManifest:
    roles = _split_roles(rows, spec, outer_seed)

    def qualified(role: str) -> tuple[str, ...]:
        return tuple(source_row_id(binding, row_id) for row_id in roles[role])

    evaluation_ids = qualified("final_test")
    return OuterRoleManifest(
        outer_seed=outer_seed,
        split_profile=SPLIT_PROFILE,
        train_ids=qualified("train"),
        source_cal_ids=qualified("source_cal"),
        target_pool_ids=qualified("target_pool"),
        evaluation_ids=evaluation_ids,
        evaluation_groups=tuple(groups[row_id] for row_id in roles["final_test"]),
        evaluation_order_digest=canonical_digest(list(evaluation_ids)),
    )


def build_outer_roles(
    dataset: BankDataset, binding: SourceBinding, spec: RepeatSpec
) -> tuple[OuterRoleManifest, ...]:
    """Ordered role manifests for the declared outer seeds. Labels stay inside the splitter."""
    _require_synthetic(binding)
    if type(spec) is not RepeatSpec:
        raise RepeatContractError("REPEAT_SCHEMA", "spec")
    rows_by_id, groups = _validated_rows(dataset, binding)
    rows = list(rows_by_id.values())
    return tuple(_outer_manifest(rows, groups, binding, spec, outer) for outer in spec.outer_seeds)


def plan_development_repeats(
    dataset: BankDataset, binding: SourceBinding, spec: RepeatSpec | None = None
) -> RepeatPlan:
    _require_synthetic(binding)
    spec = RepeatSpec() if spec is None else spec
    return plan_repeats(spec, binding, build_outer_roles(dataset, binding, spec))


# ------------------------------------------------------------------ evaluator boundary

class _EvaluatorPrivateGroupScorer:
    """Holds final-test labels only inside FinalTestEvaluator instances, one per group."""

    __slots__ = ("_groups",)

    def __init__(self, labels: tuple[int, ...], groups: tuple[str, ...]) -> None:
        positions: dict[str, list[int]] = {}
        for position, group in enumerate(groups):
            positions.setdefault(group, []).append(position)
        self._groups = tuple(
            (group, tuple(members),
             FinalTestEvaluator([labels[i] for i in members], tier="baseline"))
            for group, members in sorted(positions.items())
        )

    def __repr__(self) -> str:
        return "<evaluator-private group scorer>"

    def evaluator_private_paired_group_sums(
        self,
        group_universe: tuple[str, ...],
        target: list[float],
        source: list[float],
    ) -> tuple[float, ...]:
        """Per-group sums of (p_target-y)^2 - (p_source-y)^2, aligned to the group universe.

        Brier here is binary MSE, so n times the evaluator's group mean is the exact sum.
        Probabilities are final: fallbacks were resolved before this call.
        """
        sums: dict[str, float] = {}
        for group, members, evaluator in self._groups:
            count = len(members)
            total = count * (
                evaluator.score([target[i] for i in members])["brier_score"]
                - evaluator.score([source[i] for i in members])["brier_score"]
            )
            # Exact signed row-count bounds, no tolerance and no repair: a value outside them
            # (or not finite) is a defect upstream, never something to clamp.
            if not math.isfinite(total) or abs(total) > count:
                raise RepeatContractError("INVALID_GROUP_SUM", "paired sum outside the group bounds")
            sums[group] = float(total)
        return tuple(sums.get(group, 0.0) for group in group_universe)


# ------------------------------------------------------------------ outer preparation

@dataclass(frozen=True, eq=False, repr=False)
class _FittedPredictor:
    name: str
    pipeline: object
    predictor_id: str
    source_fit: CalibrationFit


@dataclass(frozen=True, eq=False, repr=False)
class PreparedOuter:
    """Everything shared by the ten inner repeats of one outer seed."""

    plan: RepeatPlan
    outer_seed: int
    source_rows: tuple
    source_labels: tuple[int, ...]
    pool_rows: tuple
    final_features: tuple
    predictors: tuple[_FittedPredictor, ...]
    _scorer: _EvaluatorPrivateGroupScorer

    def __repr__(self) -> str:
        return f"PreparedOuter(outer_seed={self.outer_seed})"


def _logistic_state(preprocessor, model) -> dict:
    numeric = preprocessor.transformer.named_transformers_["numeric"]
    categorical = preprocessor.transformer.named_transformers_["categorical"]
    return {
        "numeric_medians": numeric.named_steps["imputer"].statistics_.tolist(),
        "numeric_scales": numeric.named_steps["scaler"].scale_.tolist(),
        "categories": [values.tolist() for values in categorical.categories_],
        "coefficients": model.coef_.tolist(),
        "intercepts": model.intercept_.tolist(),
        "classes": model.classes_.tolist(),
    }


def prepare_outer(dataset: BankDataset, plan: RepeatPlan, outer_seed: int) -> PreparedOuter:
    """Fit each predictor once on this outer's training role; shared by every inner repeat."""
    if type(plan) is not RepeatPlan:
        raise RepeatContractError("REPEAT_SCHEMA", "plan")
    binding = _require_synthetic(plan.binding)
    ensure_planned(plan)
    manifest = plan.roles(outer_seed)
    rows_by_id, groups = _validated_rows(dataset, binding)
    rows = list(rows_by_id.values())
    if _outer_manifest(rows, groups, binding, plan.spec, outer_seed) != manifest:
        raise RepeatContractError("PLAN_DATASET_MISMATCH", str(outer_seed))
    roles = _split_roles(rows, plan.spec, outer_seed)
    seeds = dict(plan.repeat(outer_seed, plan.spec.inner_ids[0]).seed_map.seeds)

    def role_rows(role: str) -> tuple[dict, ...]:
        return tuple(rows_by_id[row_id] for row_id in roles[role])

    train, source, pool, final = (
        role_rows("train"), role_rows("source_cal"), role_rows("target_pool"), role_rows("final_test"),
    )
    train_features = list(feature_rows(list(train)))
    train_labels = [int(row[TARGET_COLUMN]) for row in train]
    source_rows = tuple({"row_id": int(r["row_id"]), **feature_rows([r])[0]} for r in source)
    source_labels = tuple(int(row[TARGET_COLUMN]) for row in source)
    final_features = tuple({"row_id": int(r["row_id"]), **feature_rows([r])[0]} for r in final)
    # Final labels go straight into the evaluator boundary and are not kept anywhere else.
    scorer = _EvaluatorPrivateGroupScorer(
        tuple(int(row[TARGET_COLUMN]) for row in final), manifest.evaluation_groups)

    train_digest = canonical_digest(list(manifest.train_ids))
    fitted = []
    for name in plan.spec.predictors:
        seed = seeds[f"model_{name}"]
        if name == "logistic_regression":
            preprocessor = fit_train_preprocessor(train_features)
            model = fit_initial_logistic_regression(preprocessor.transform(train_features), train_labels, seed)
            meta, state, family = predictor_identity(model), _logistic_state(preprocessor, model), "linear"
        else:
            preprocessor = fit_tree_preprocessor(train_features)
            model = fit_initial_random_forest(preprocessor.transform(train_features), train_labels, seed)
            meta, state, family = random_forest_identity(model), fitted_rf_state(preprocessor, model), "tree"
        pipeline = frozen_pipeline(preprocessor, model)
        predictor_id = canonical_digest([
            "gate8-predictor-v1", binding.digest, train_digest, name,
            preprocessing_config(family), meta, state,
        ])
        source_fit = fit_temperature(pipeline, source_rows, source_labels, "source_temperature")
        fitted.append(_FittedPredictor(name, pipeline, predictor_id, source_fit))
    return PreparedOuter(
        plan=plan, outer_seed=outer_seed, source_rows=source_rows, source_labels=source_labels,
        pool_rows=pool, final_features=final_features, predictors=tuple(fitted), _scorer=scorer,
    )


# ------------------------------------------------------------------ one coordinate

@dataclass(frozen=True)
class CoordinateResult:
    """The label-free reduction of one execution coordinate."""

    key: RepeatKey
    repeat_id: str
    seed_map: SeedMap
    execution_tier: str
    claim_scope: str
    acquisition_order: tuple[str, ...]
    contexts: tuple[PairContext, ...]
    conditions: tuple[TerminalCondition, ...]
    validated_pairs: tuple[ValidatedPair, ...]
    pair_cells: tuple[PairedGroupLossCell, ...]


@dataclass(frozen=True, eq=False, repr=False)
class _ScenarioMasks:
    test_rows: tuple
    injected_fractions: np.ndarray
    pool_mask: object | None
    test_digest: str
    pool_digest: str


def _mask_digest(partition: str, scenario: str, mask: object | None, ids: tuple[int, ...]) -> str:
    if mask is None:
        return canonical_digest(["gate8-unmasked-v1", partition, list(ids)])
    return canonical_digest(["gate8-mask-v1", partition, scenario, mask.mask_id])


def _injected_fractions(original: tuple, masked: tuple) -> np.ndarray:
    fractions = [
        sum(o.get(f) not in (None, "") and m.get(f) in (None, "") for f in BANK_FEATURES)
        / len(BANK_FEATURES)
        for o, m in zip(original, masked, strict=True)
    ]
    return np.array(fractions, dtype=float)


def _scenario_masks(
    seeds: dict[str, int], pool_ids: tuple[int, ...], final_features: tuple
) -> dict[str, _ScenarioMasks]:
    """Raw masks for every scenario; the full pool mask is frozen before any label is revealed."""
    test_ids = tuple(int(row["row_id"]) for row in final_features)
    pool_uniforms = generate_shared_uniforms(len(pool_ids), len(BANK_FEATURES), seeds["pool_mcar"])
    test_uniforms = generate_shared_uniforms(len(test_ids), len(BANK_FEATURES), seeds["test_mcar"])
    pool_block = history_block_mask(pool_ids, seeds["pool_block"], HISTORY_ROW_PROBABILITY)
    test_block = history_block_mask(test_ids, seeds["test_block"], HISTORY_ROW_PROBABILITY)
    test_matched, report = compute_matched_mcar(
        record_ids=test_ids, rows=final_features, block_rates=test_block.rates(final_features),
        seed=seeds["test_mcar"], features=BANK_FEATURES, shared_uniforms=test_uniforms,
    )
    pool_matched = generate_mcar_mask(
        pool_ids, BANK_FEATURES, rate=float(report["target_rate"]), shared_uniforms=pool_uniforms)
    masks = {
        "baseline": (None, None),
        "history_block_0_50": (pool_block, test_block),
        "mcar_0_10": tuple(
            generate_mcar_mask(ids, BANK_FEATURES, rate=0.10, shared_uniforms=uniforms)
            for ids, uniforms in ((pool_ids, pool_uniforms), (test_ids, test_uniforms))),
        "mcar_0_30": tuple(
            generate_mcar_mask(ids, BANK_FEATURES, rate=0.30, shared_uniforms=uniforms)
            for ids, uniforms in ((pool_ids, pool_uniforms), (test_ids, test_uniforms))),
        "mcar_matched_history": (pool_matched, test_matched),
    }
    scenarios = {}
    for name in SCENARIOS:
        pool_mask, test_mask = masks[name]
        test_rows = final_features if test_mask is None else test_mask.apply(final_features)
        scenarios[name] = _ScenarioMasks(
            test_rows=test_rows,
            injected_fractions=_injected_fractions(final_features, test_rows),
            pool_mask=pool_mask,
            test_digest=_mask_digest("test", name, test_mask, test_ids),
            pool_digest=_mask_digest("pool", name, pool_mask, pool_ids),
        )
    return scenarios


def _closure(methods: tuple[str, ...]) -> tuple[str, ...]:
    """Requested methods plus every fallback they can resolve through, in declared order."""
    needed: set[str] = set()
    stack = list(methods)
    while stack:
        method = stack.pop()
        if method not in needed:
            needed.add(method)
            if FALLBACK_GRAPH[method] is not None:
                stack.append(FALLBACK_GRAPH[method])
    return tuple(method for method in METHODS if method in needed)


def _reason_codes(failures: tuple[dict, ...]) -> tuple[str, ...]:
    """Bounded stable codes; raw exception text never enters a typed contract."""
    codes: list[str] = []
    for failure in failures:
        reason = str(failure.get("reason") or "not_fitted")
        phase = "unattempted" if reason == "budget_zero_unattempted" else str(failure.get("phase", "unknown"))
        head = _SAFE_CODE.sub("_", reason.split(":", 1)[0].strip())[:64] or "unknown"
        code = f"{phase}:{_SAFE_CODE.sub('_', str(failure.get('method', 'unknown')))}:{head}"
        if code not in codes:
            codes.append(code)
    return tuple(codes)


def _resolution_counts(method, resolution, binned_fit, row_count) -> tuple[tuple[str, int], ...]:
    if resolution.resolved_method is None:
        return ()
    if method == PRIMARY_SOURCE_METHOD and resolution.resolved_method == method:
        # The binned map resolves per row; its diagnostics are current right after this prediction.
        counts: dict[str, int] = {}
        for name, count in binned_fit.probability_map.last_diagnostics["resolution_counts"].items():
            if count:
                label = _BIN_RESOLUTION_NAMES.get(name, name)
                counts[label] = counts.get(label, 0) + int(count)
        return tuple((label, counts[label]) for label in METHODS if label in counts)
    return ((resolution.resolved_method, row_count),)


def fit_identity(plan: RepeatPlan, context: PairContext, method: str) -> str | None:
    """The fit ID of a requested method, derived only from the plan and the shared context."""
    seeds = dict(plan.repeat(context.outer, context.inner).seed_map.seeds)
    predictor_id = context.predictor_id
    if method == "raw":
        return predictor_id
    source_digest = canonical_digest(list(plan.roles(context.outer).source_cal_ids))
    if method == "source_temperature":
        return canonical_digest(["gate8-fit-v1", method, predictor_id, source_digest])
    if method in ("source_remasked_temperature", PRIMARY_SOURCE_METHOD):
        return canonical_digest(
            ["gate8-fit-v1", method, predictor_id, source_digest, seeds["source_remask"]])
    if context.budget == 0:
        return None  # a target calibration is unattempted without acquired labels
    return canonical_digest([
        "gate8-fit-v1", method, predictor_id, context.pool_mask, context.acquisition_order,
        context.budget])


def condition_identity(
    repeat_id: str,
    context: PairContext,
    method: str,
    fit_id: str | None,
    resolved_method: str | None,
    counts: tuple[tuple[str, int], ...],
    status: str,
) -> str:
    """A condition's ID binds its context, fit and resolution accounting."""
    return canonical_digest([
        "gate8-condition-v1", repeat_id, context.predictor, context.scenario, context.budget,
        method, context.test_mask, context.pool_mask, context.acquisition_order,
        context.predictor_id, fit_id, resolved_method, counts, status])


def execute_coordinate(
    prepared: PreparedOuter,
    inner_id: int,
    *,
    scenarios: tuple[str, ...] = SCENARIOS,
    budgets: tuple[int, ...] = BUDGETS,
    methods: tuple[str, ...] = METHODS,
) -> CoordinateResult:
    """Compute one execution coordinate; scope arguments select an ordered subset of the grid."""
    if type(prepared) is not PreparedOuter:
        raise RepeatContractError("REPEAT_SCHEMA", "prepared")
    plan = prepared.plan
    binding = _require_synthetic(plan.binding)
    outer_seed = prepared.outer_seed
    declared_repeat(outer_seed, inner_id)
    scenarios = _scope(scenarios, SCENARIOS, "scenarios")
    budgets = _scope(budgets, BUDGETS, "budgets")
    methods = _scope(methods, METHODS, "methods")

    key = RepeatKey(outer_seed, inner_id)
    planned = plan.repeat(outer_seed, inner_id)
    seeds = dict(planned.seed_map.seeds)
    manifest = plan.roles(outer_seed)
    row_count = len(manifest.evaluation_ids)
    needed = _closure(methods)

    # Acquisition: one label-blind order per coordinate; every budget is a nested prefix of it.
    provider = LabelBlindTargetProvider(prepared.pool_rows, seeds["acquisition"])
    order_ids = tuple(source_row_id(binding, row_id) for row_id in provider.order)
    order_digest = canonical_digest(["gate8-acquisition-order-v1", list(order_ids)])
    masks = _scenario_masks(seeds, provider.pool_record_ids, prepared.final_features)

    remasked = None
    if {"source_remasked_temperature", "source_fraction_binned_temperature"} & set(needed):
        children = np.random.default_rng(seeds["source_remask"]).integers(0, 1_000_000, size=2)
        if (int(children[0]), int(children[1])) != (seeds["source_mcar"], seeds["source_block"]):
            raise RepeatContractError("SEED_MAP_MISMATCH", "source_remask")
        remasked = generate_source_remasked_dataset(
            prepared.source_rows, prepared.source_labels, seed=seeds["source_remask"],
            features=BANK_FEATURES)
    qualification = _qualification(binding)

    contexts: list[PairContext] = []
    conditions: list[TerminalCondition] = []
    validated: list[ValidatedPair] = []
    cells: list[PairedGroupLossCell] = []
    primary = {PRIMARY_TARGET_METHOD, PRIMARY_SOURCE_METHOD} <= set(methods)

    for fitted in prepared.predictors:
        pipeline, predictor_id = fitted.pipeline, fitted.predictor_id
        source_fit = fitted.source_fit
        remasked_fit = binned_fit = None
        if remasked is not None:
            remasked_fit = fit_source_remasked_temperature(pipeline, remasked[0], remasked[1])
            binned_fit = fit_source_fraction_binned_temperature(
                pipeline=pipeline, remasked_rows=remasked[0], remasked_labels=remasked[1],
                missing_fractions=remasked[2], global_fit=remasked_fit, source_fit=source_fit,
                n_bins=10, min_bin_samples=10)
        for scenario in scenarios:
            scene = masks[scenario]
            pool_features = provider.pool_features
            masked_pool = {
                int(r["row_id"]): r for r in (
                    pool_features if scene.pool_mask is None else scene.pool_mask.apply(pool_features))
            }
            for budget in budgets:
                context = pair_context_for(
                    plan, key, fitted.name, scenario, budget,
                    test_mask=scene.test_digest, pool_mask=scene.pool_digest,
                    acquisition_order=order_digest, acquired_prefix=order_ids[:budget],
                    predictor_id=predictor_id)
                contexts.append(context)

                fits = {"raw": pipeline, "source_temperature": source_fit}
                if remasked_fit is not None:
                    fits["source_remasked_temperature"] = remasked_fit
                    fits[PRIMARY_SOURCE_METHOD] = binned_fit
                target_names = [name for name in _TARGET_FITTERS if name in needed]
                if budget > 0:
                    acquired = provider.reveal_prefix(budget)
                    rows = tuple(masked_pool[row_id] for row_id in acquired.record_ids)
                    for name in target_names:
                        fits[name] = _TARGET_FITTERS[name](pipeline, rows, acquired.labels)
                else:
                    unattempted = CalibrationRecord(
                        "not_fitted", "not_fitted", "not_fitted", "budget_zero_unattempted", 0, None)
                    for name in target_names:
                        fits[name] = CalibrationFit(pipeline, unattempted)

                # Every fallback is resolved here, before any final-test outcome is touched.
                resolutions, _attempts = predict_conditions_with_fallback(
                    {name: fits[name] for name in METHODS if name in needed},
                    FALLBACK_GRAPH, scene.test_rows, injected_fractions=scene.injected_fractions)

                made: dict[str, TerminalCondition] = {}
                for method in methods:
                    resolution = resolutions[method]
                    failed = resolution.probabilities is None
                    counts = _resolution_counts(method, resolution, binned_fit, row_count)
                    reasons = _reason_codes(resolution.failures)
                    if failed and not reasons:
                        reasons = ("no_probabilities_resolved",)
                    fit_id = fit_identity(plan, context, method)
                    status = "failed" if failed else "completed"
                    made[method] = TerminalCondition(
                        condition_id=condition_identity(
                            planned.repeat_id, context, method, fit_id,
                            resolution.resolved_method, counts, status),
                        repeat_id=planned.repeat_id, outer_seed=outer_seed, inner_id=inner_id,
                        predictor=fitted.name, scenario=scenario, budget=budget,
                        requested_method=method,
                        resolved_method=resolution.resolved_method,
                        resolution_counts=counts, status=status,
                        metrics_available=not failed,
                        qualification="failed" if failed else qualification,
                        reasons=reasons, fit_id=fit_id)
                conditions.extend(made.values())

                if primary and budget == PRIMARY_BUDGET and scenario in PRIMARY_SCENARIOS:
                    cell = _paired_cell(
                        prepared, context, resolutions, made, qualification, validated)
                    cells.append(cell)

    result = CoordinateResult(
        key=key, repeat_id=planned.repeat_id, seed_map=planned.seed_map,
        execution_tier=EXECUTION_TIER, claim_scope=SYNTHETIC_CLAIM_SCOPE,
        acquisition_order=order_ids, contexts=tuple(contexts), conditions=tuple(conditions),
        validated_pairs=tuple(validated), pair_cells=tuple(cells),
    )
    # A coordinate is only returned (and so only persistable) once its pairs, conditions,
    # accounting and shared context agree with each other and with the plan.
    validate_coordinate_result(plan, result)
    return result


def _paired_cell(prepared, context, resolutions, made, qualification, validated) -> PairedGroupLossCell:
    plan = prepared.plan
    target, source = resolutions[PRIMARY_TARGET_METHOD], resolutions[PRIMARY_SOURCE_METHOD]
    target_condition, source_condition = made[PRIMARY_TARGET_METHOD], made[PRIMARY_SOURCE_METHOD]
    common = dict(
        context=context,
        target_condition_id=target_condition.condition_id,
        source_condition_id=source_condition.condition_id,
        group_ids=plan.group_universe,
        n_by_group=plan.group_counts(context.outer),
        target_resolved_method=target.resolved_method,
        source_resolved_method=source.resolved_method,
        target_resolution_counts=target_condition.resolution_counts,
        source_resolution_counts=source_condition.resolution_counts,
    )
    if target.probabilities is None or source.probabilities is None:
        # A failed raw prediction leaves no scores: null sums, never a fabricated number.
        reasons = tuple(
            code for code, resolution in (
                ("target_prediction_failed", target), ("source_prediction_failed", source))
            if resolution.probabilities is None)
        return PairedGroupLossCell(
            paired_loss_sum_by_group=None, qualification="failed", reasons=reasons, **common)

    def as_array(method, resolution):
        return ProbabilityArray(
            context, method, tuple((1.0 - float(p), float(p)) for p in resolution.probabilities))

    validated.append(validate_probability_pair(
        as_array(PRIMARY_TARGET_METHOD, target), as_array(PRIMARY_SOURCE_METHOD, source), context))
    sums = prepared._scorer.evaluator_private_paired_group_sums(
        plan.group_universe, target.probabilities, source.probabilities)
    return PairedGroupLossCell(
        paired_loss_sum_by_group=sums, qualification=qualification, reasons=(), **common)


# ------------------------------------------------------------------ joined coordinate validation

def _coordinate_error(code: str, detail: str) -> RepeatContractError:
    return RepeatContractError(code, detail)


def validate_coordinate_result(plan: RepeatPlan, result: CoordinateResult) -> None:
    """Join primary pairs to terminal records and check the whole coordinate against the plan.

    Only this joined path may claim that a coordinate's accounting is complete: every
    condition must account for exactly the plan-bound evaluation rows with a derivable fit
    identity and ID, every context must share the plan, masks, acquisition order and
    predictor, and every primary pair must reference the very conditions it was derived
    from, with the same resolution accounting.
    """
    ensure_planned(plan)
    if type(result) is not CoordinateResult:
        raise _coordinate_error("COORDINATE_SCHEMA", "result")
    key = result.key
    if type(key) is not RepeatKey:
        raise _coordinate_error("COORDINATE_SCHEMA", "key")
    declared_repeat(key.outer_seed, key.inner_id)
    planned = plan.repeat(key.outer_seed, key.inner_id)
    if (
        result.repeat_id != planned.repeat_id
        or result.seed_map != planned.seed_map
        or result.execution_tier != EXECUTION_TIER
        or result.claim_scope != SYNTHETIC_CLAIM_SCOPE
    ):
        raise _coordinate_error("COORDINATE_IDENTITY", f"{key.outer_seed}/{key.inner_id}")
    manifest = plan.roles(key.outer_seed)
    order = identifier_tuple(result.acquisition_order, "acquisition_order")
    if len(set(order)) != len(order) or sorted(order) != sorted(manifest.target_pool_ids):
        raise _coordinate_error("COORDINATE_ACQUISITION", "acquisition order is not the pool")
    order_digest = canonical_digest(["gate8-acquisition-order-v1", list(order)])

    contexts: dict[tuple[str, str, int], PairContext] = {}
    masks: dict[str, tuple[str, str]] = {}
    predictors: dict[str, str] = {}
    for context in immutable_tuple(result.contexts, "contexts"):
        if type(context) is not PairContext:
            raise _coordinate_error("COORDINATE_CONTEXT", "context type")
        if (context.outer, context.inner) != (key.outer_seed, key.inner_id):
            raise _coordinate_error("COORDINATE_CONTEXT", "context belongs to another coordinate")
        mismatch = plan_owned_mismatch(plan, context)
        if mismatch:
            raise _coordinate_error("COORDINATE_CONTEXT", ", ".join(mismatch))
        cell_key = (context.predictor, context.scenario, context.budget)
        if cell_key in contexts:
            raise _coordinate_error("COORDINATE_CONTEXT", f"duplicate context {cell_key}")
        if context.acquisition_order != order_digest or context.acquired_prefix != order[:context.budget]:
            raise _coordinate_error("COORDINATE_CONTEXT", "acquisition is not shared")
        if masks.setdefault(context.scenario, (context.test_mask, context.pool_mask)) != (
            context.test_mask, context.pool_mask
        ):
            raise _coordinate_error("COORDINATE_CONTEXT", f"masks differ within {context.scenario}")
        if predictors.setdefault(context.predictor, context.predictor_id) != context.predictor_id:
            raise _coordinate_error("COORDINATE_CONTEXT", f"predictor differs within {context.predictor}")
        contexts[cell_key] = context

    slot_index = {slot: index for index, slot in enumerate(expected_condition_slots(plan.spec))}
    by_id: dict[str, TerminalCondition] = {}
    by_slot: dict[tuple, TerminalCondition] = {}
    joined: set[tuple[str, str, int]] = set()
    previous = -1
    for condition in immutable_tuple(result.conditions, "conditions"):
        validate_condition_accounting(plan, condition)
        if (condition.outer_seed, condition.inner_id) != (key.outer_seed, key.inner_id) or (
            condition.repeat_id != planned.repeat_id
        ):
            raise _coordinate_error("COORDINATE_CONDITION", "condition belongs to another coordinate")
        index = slot_index.get(condition.slot)
        if index is None or index <= previous:
            raise _coordinate_error("COORDINATE_CONDITION", f"slot {tuple(condition.slot)}")
        previous = index
        cell_key = (condition.predictor, condition.scenario, condition.budget)
        context = contexts.get(cell_key)
        if context is None:
            raise _coordinate_error("COORDINATE_CONDITION", f"no context for {cell_key}")
        joined.add(cell_key)
        fit_id = fit_identity(plan, context, condition.requested_method)
        if condition.fit_id != fit_id:
            raise _coordinate_error("COORDINATE_FIT", f"{tuple(condition.slot)}")
        expected_id = condition_identity(
            planned.repeat_id, context, condition.requested_method, fit_id,
            condition.resolved_method, condition.resolution_counts, condition.status)
        if condition.condition_id != expected_id or condition.condition_id in by_id:
            raise _coordinate_error("COORDINATE_CONDITION", f"identity of {tuple(condition.slot)}")
        by_id[condition.condition_id] = condition
        by_slot[tuple(condition.slot)] = condition
    if joined != set(contexts):
        raise _coordinate_error("COORDINATE_CONTEXT", "a context has no terminal condition")

    expected_pairs = [
        (predictor, scenario)
        for predictor in plan.spec.predictors
        for scenario in PRIMARY_SCENARIOS
        if (key.outer_seed, key.inner_id, predictor, scenario, PRIMARY_BUDGET, PRIMARY_TARGET_METHOD) in by_slot
        and (key.outer_seed, key.inner_id, predictor, scenario, PRIMARY_BUDGET, PRIMARY_SOURCE_METHOD) in by_slot
    ]
    cells = immutable_tuple(result.pair_cells, "pair_cells")
    if any(type(cell) is not PairedGroupLossCell for cell in cells) or [
        (cell.context.predictor, cell.context.scenario) for cell in cells
    ] != expected_pairs:
        raise _coordinate_error("PAIR_BINDING", "primary pairs do not match the terminal conditions")
    scored = []
    for cell in cells:
        context = cell.context
        if contexts.get((context.predictor, context.scenario, PRIMARY_BUDGET)) != context:
            raise _coordinate_error("PAIR_BINDING", "pair context is not a coordinate context")
        target = by_id.get(cell.target_condition_id)
        source = by_id.get(cell.source_condition_id)
        slot_prefix = (key.outer_seed, key.inner_id, context.predictor, context.scenario, PRIMARY_BUDGET)
        if (
            target is None or source is None
            or tuple(target.slot) != (*slot_prefix, PRIMARY_TARGET_METHOD)
            or tuple(source.slot) != (*slot_prefix, PRIMARY_SOURCE_METHOD)
        ):
            raise _coordinate_error("PAIR_BINDING", "pair references another condition")
        if cell.group_ids != plan.group_universe or cell.n_by_group != plan.group_counts(key.outer_seed):
            raise _coordinate_error("PAIR_BINDING", "pair groups differ from the plan")
        if (
            (cell.target_resolved_method, cell.target_resolution_counts)
            != (target.resolved_method, target.resolution_counts)
            or (cell.source_resolved_method, cell.source_resolution_counts)
            != (source.resolved_method, source.resolution_counts)
        ):
            raise _coordinate_error("PAIR_BINDING", "pair accounting differs from its conditions")
        if cell.paired_loss_sum_by_group is None:
            if "failed" not in (target.status, source.status) or cell.qualification != "failed":
                raise _coordinate_error("PAIR_BINDING", "unscored pair without a failed condition")
        else:
            if (
                target.status != "completed" or source.status != "completed"
                or cell.qualification != target.qualification
                or cell.qualification != source.qualification
                or cell.reasons
            ):
                raise _coordinate_error("PAIR_BINDING", "scored pair disagrees with its conditions")
            scored.append(cell)
    validated = immutable_tuple(result.validated_pairs, "validated_pairs")
    if len(validated) != len(scored) or any(
        type(pair) is not ValidatedPair
        or pair.context != cell.context
        or pair.row_count != len(manifest.evaluation_ids)
        for pair, cell in zip(validated, scored)
    ):
        raise _coordinate_error("PAIR_BINDING", "validated pairs do not match the scored cells")
