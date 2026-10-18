# Gate 9 prospective Adult protocol amendment (DRAFT)

**Status: DRAFT — not the lock. The lock is a later public commit that changes this status line after a further Opus model consistency check (not human review); until then nothing here is binding. Revision r3 (19 Oct 2026) applied the r1 and r2 findings of Opus model consistency checks (19 Oct), not human review, and is still not lockable: see section 9A.**

**Label (applies only once locked):** author-locked, not externally peer-reviewed.

Drafted 18 October 2026 for Gate 9 prerequisite 2 (`docs/superpowers/plans/2026-10-15-results-assistant-and-remaining-gates.md:78-82`).

This draft makes no claim of external scientific approval, independent human review, custodian attestation or confirmatory status. Model consistency checks are not human review. No Adult test file, test label or test outcome was read to prepare it. No analysis of real data was run for it. An Opus model consistency check (19 Oct), not human review, was run on revision r1 (`../../../verification/autopilot-20261019-run11/gate9-draft-check-r1.md`); revision r2 applies its findings. A delta model check of r2 returned ACCEPT_AS_DRAFT with further findings, and a second, parallel Opus model review of r1 exists (`../../../verification/autopilot-20261018-run11/review-gate9-draft-r1.md`, recorded at LOG:320); revision r3 applies the delta findings and dispositions the parallel review in section 11.4. Neither check opened `adult.test` or any label. Only the label-blind train-only manifest counts of run 10 are used here.

Path citations are written `path:line`. Where a source says nothing, the item is an `<<OPEN DECISION>>` and is collected in section 11. Where two sources disagree, the conflict is recorded in section 11 (C-items) and is not silently resolved.

Short names used below:

| Short name | Path |
|---|---|
| SD | `research/gate8-20261009/SCIENTIFIC_DECISIONS.md` |
| DRAFT | `research/protocol-v0.3/RESEARCH_PROTOCOL_DRAFT.md` |
| REG | `research/protocol-v0.3/DECISION_REGISTER.json` |
| PLAN | `shiftguard/docs/superpowers/plans/2026-10-15-results-assistant-and-remaining-gates.md` |
| G3 | `shiftguard/docs/gate3-development-contract.md` |
| adult.py | `shiftguard/shiftguard/datasets/adult.py` |
| features.py, grouping.py, missingness.py, source_manifest.py | `shiftguard/shiftguard/adult_adapter/<name>` |
| RM | `shiftguard/shiftguard/repeats/run_manifest.py` |
| LOG | `shiftguard/.agent/AUTOPILOT_LOG.md` |
| AUTOPILOT | `shiftguard/.agent/AUTOPILOT.md` |
| OWNER_ACTIONS | `shiftguard/.agent/OWNER_ACTIONS.md` |
| development_adapter.py | `shiftguard/shiftguard/repeats/development_adapter.py` |

All paths in the table are relative to the workspace root `nvidia/`. Paths starting `shiftguard/` are inside the application repository (so `shiftguard/shiftguard/...` is the Python package). Sources outside the repository (SD, DRAFT, REG) and the git-ignored `shiftguard/var/datasets/adult.manifest.json` (`.gitignore:12`) are not public; the lock must bind their SHA-256 or quote the cited lines (9A, rule 4). Line numbers were re-derived on 19 Oct 2026 from the current files, including `source_manifest.py` as changed in commit `645aace` and LOG with its run-11 entry.

---

## 1. Status, scope and labels

**What this amendment is.** A prospective design for one Adult analysis: the same primary contrast as Gate 8, run on an Adult source whose test file is unsealed once, after a public lock commit. It extends the draft v0.3 Adult mapping (DRAFT:57-61) and the Gate 8 candidate amendment (SD:114-128) with exact rules.

**Scope.**

| Item | Rule | Source |
|---|---|---|
| Development runs | `adult.data` only (role of such runs: OD-18). No `adult.test` label is read or used for features, groups, masks, calibration or model choices. `adult.test` bytes are used only label-blind, for feature fingerprints, the source manifest and quarantine (sections 2.2 and 4.4). | PLAN:83-84; DRAFT:53, 55; adult.py:176-206 |
| Test file | `adult.test` is unsealed exactly once, after the lock commit is public. **Unseal** means the first decode of the label field of `adult.test` or the first evaluator scoring against it, whichever comes first. | PLAN:81-84 |
| Bank | Out of scope. Bank outcomes were inspected; no Bank analysis is confirmatory. | PLAN:66; DRAFT:13 |
| Execution guard | `execute_adult_confirmatory()` always raises today. Lifting it is a code change that happens after the lock, in the execution-binding commit of section 10 (see OD-19). | adult.py:265-267; shiftguard/configs/adult-confirmatory.yaml:2,7 |

**Exposure status of Adult test: UNKNOWN.** Download metadata proves only that `adult.data` was fetched on 2026-09-16 and that a code constant `confirmatory_test_sealed: true` was written (SD:56; adult.py:257). That flag is not an access audit. Neither local file absence, the guard, nor a new seed shows that the test outcomes were never seen, scored or used in design (SD:16, SD:35, SD:39, SD:58). Register items P-05 and U-02 are open (REG:120-123, REG:146-149).

**Manifest status.** The label-blind train+test source manifest is built by author tooling. Its own field reads `author-built, not custodian-attested` (source_manifest.py:80). Self-verification checks only a closed schema and internal consistency; a coherent forgery would pass it (source_manifest.py:43-50). Producing it is an exposure event to record, not custodian evidence (LOG:291). PLAN:77 and AUTOPILOT:78 call the same manifest "custodian evidence" and "custodian manifest"; that wording conflicts with the tool's own status and is recorded as C-09.

**How results will be labelled because of this.** Every table, figure, abstract line and README mention of an Adult result produced under this amendment carries all three phrases:

1. "Adult test exposure status: UNKNOWN (no custodian attestation)".
2. "Source manifest: author-built, not custodian-attested".
3. "Author-locked, not externally peer-reviewed".

The analysis is described as a **prospective Adult analysis under author lock**. It is not called confirmatory, because the draft's own rule says that without verified exposure separation neither Adult nor fresh Bank seeds may be called confirmatory (DRAFT:67). The sealed configuration still says `evaluation_tier: confirmatory` (shiftguard/configs/adult-confirmatory.yaml:5); that text conflicts with this labelling and is recorded as C-04. Even a clean result supports only the declared Adult source and intervention regime, not other populations (DRAFT:15; SD:95).

Register flags stay as they are: `confirmatory_dispatch_permitted` is false and `lock_gate.status` is `DRAFT_NOT_LOCKED` (REG:216-223). This amendment does not edit the register.

---

## 2. Data and source binding

### 2.1 Training file (frozen)

| Field | Value | Source |
|---|---|---|
| Dataset id | `uci-adult-2` | adult.py:64 |
| Source version | `adult.data` | adult.py:66 |
| Source URL | `https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.data` | adult.py:65 |
| Raw SHA-256 | `5b00264637dbfec36bdeaab5676b0b309ff9eb788d63554ca0a249491c86603d` | adult.py:67; shiftguard/var/datasets/adult.manifest.json:25 |
| Raw records | 32,561 | adult.py:70; shiftguard/var/datasets/adult.manifest.json:24 |
| Local retrieval | official download, 2026-09-16T07:40:40.566281+00:00 | shiftguard/var/datasets/adult.manifest.json:27-28 |
| Physical lines (author manifest, train only) | 32,562 lines, 32,561 records, 24 duplicate groups covering 49 rows | LOG:293-294 (run 10, "Real run, train only") |

The acquisition function refuses `adult.test` URLs and combined archives (adult.py:179-206) and checks the SHA-256 and record count (adult.py:215-238).

The author-built train-only manifest has `manifest_sha256` starting `6336aa16` and ending `7317` (LOG:296, run 10). The full 64-character digest is not recorded in the log; it is bound at the lock (OD-01).

### 2.2 Test file (to be bound before the lock)

| Field | Binding |
|---|---|
| Source URL | `https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.test` (named in OWNER_ACTIONS:107-116). `<<TO BIND BEFORE LOCK>>` confirm it is the URL actually used. |
| Raw SHA-256 of `adult.test` | `<<TO BIND BEFORE LOCK>>` (from the train+test source manifest) |
| Byte size | `<<TO BIND BEFORE LOCK>>` |
| Record count | `<<TO BIND BEFORE LOCK>>` (the documented count is 16,281 — DRAFT:59; REG:123 — it is a documented figure, not a verified one; which rows form the fixed evaluation cohort is OD-16) |
| Physical lines, skipped lines (header, blanks) | `<<TO BIND BEFORE LOCK>>` |
| Train+test source manifest `manifest_sha256` | `<<TO BIND BEFORE LOCK>>` |
| Manifest `release` string | `<<TO BIND BEFORE LOCK>>` (the frozen release is `uci-adult-2`; source_manifest.py:84; adult.py:64) |
| Feature schema digest and feature-group version in the manifest | `<<TO BIND BEFORE LOCK>>` (`tool_versions`, source_manifest.py:221-224) |
| Code pins | The release string is forced by code in `connected_group_key_set` (source_manifest.py:448-465); the `adult.test` bytes themselves are not pinned in code, so their SHA-256 comes only from the manifest and the lock (OD-01). |
| Evaluator label parser | `<<TO BIND BEFORE LOCK>>` a bound parser for `adult.test` labels aligned to `uci-adult-2:adult.test:<physical line>` ids (OD-19). `clean_adult_rows` (adult.py:95-123) numbers rows sequentially, skips blank lines and would raise on the `|` header, so it cannot be used for this. |
| Download/placement event | date, who, how — `<<TO BIND BEFORE LOCK>>`. Downloading needs the owner's explicit permission (OWNER_ACTIONS:107-116; LOG:304). |

No hash for the test file is stated anywhere in this draft because none has been established. The first line of the official test file is a `|` comment header and its labels carry a trailing period (documented UCI format, handled by adult.py:87; not verified locally); the manifest builder skips the header by physical line number and never reads the label slot (source_manifest.py:6-15, 38-41, 134-142).

### 2.3 What else the lock binds

SD:40 (U-03) requires one lock to bind the accepted source commit (that conflicts with PLAN:83, which wires the engine after the lock; recorded as C-10), dependency lock, exact evaluation bytes, release, parser, feature/group/role membership, the complete seed map and approval. The Gate 8 manifest pattern shows the shape: schema name, source tree digest from git blob ids, dependency-lock digest, feature-schema digest, ordered `(row id, group id)` digest, protocol-file digest, role counts as digests and counts only, and a development label (RM:11-35, RM:83-86). For this amendment the Adult analogue of each digest is `<<TO BIND BEFORE LOCK>>` (OD-02). Binding is in two stages (section 10, C-10): the lock binds the protocol text, the manifest and the allocation digests; a public execution-binding commit before the unseal binds the source and dependency digests, the guard lift, the seed-map digest and the run manifest. Row ids, group ids, labels, losses and paired sums are never put in a public manifest (RM:33-35; SD:182). The source manifest lists row ids for its duplicate groups (source_manifest.py:186-189), so it is bound by its `manifest_sha256` digest only and is not published; whether it could be published is OD-20.

---

## 3. Predictors, missing tokens and label rule

**The 13 predictors** (`education` dropped, `education-num` kept): `age, workclass, fnlwgt, education-num, marital-status, occupation, relationship, race, sex, capital-gain, capital-loss, hours-per-week, native-country` (adult.py:33-48; DRAFT:59).

| Type | Features | Source |
|---|---|---|
| Numeric (6) | `age, fnlwgt, education-num, capital-gain, capital-loss, hours-per-week` | adult.py:50-57 |
| Categorical (7) | `workclass, marital-status, occupation, relationship, race, sex, native-country` | adult.py:59 |

**Raw columns** are the 15 UCI columns including `education` and `income` (adult.py:15-31). Any key outside the 13 predictors, including `income` and `education`, is rejected when a feature record is built (features.py:177-182), so group keys and masks cannot see a label.

**Natural missingness.** The raw token `?`, after whitespace stripping, becomes null; every other token is kept with its exact spelling (adult.py:112-113; features.py:166-193; SD:116). Actual category values stay categories (DRAFT:55). Categories absent from the predictor-training role use the frozen encoder's `handle_unknown=ignore` rule, with no vocabulary refit (DRAFT:55; G3:26).

**Label normalization (rule only).** The code does `raw.strip().rstrip(".")`, which removes surrounding whitespace and **every** trailing period (not just one); then `<=50K` maps to 0 and `>50K` to 1, and any other string raises `ValueError` (adult.py:85-92, rstrip at line 87). This rule is stated so the later evaluator uses it unchanged. It is never applied to test bytes before the unseal; the existing `clean_adult_rows` parses income and must not be called on test bytes before then (SD:124).

---

## 4. Exact-token grouping and test-connected quarantine

### 4.1 Schema and key

| Element | Rule | Source |
|---|---|---|
| Key content | SHA-256 of canonical ASCII JSON `[FEATURE_GROUP_VERSION, feature_schema_digest, ordered tokens]`, where each token is the exact raw string or JSON null for `?` | grouping.py:42-49; SD:116 |
| `FEATURE_GROUP_VERSION` | `gate8-feature-group-v1` | grouping.py:30 |
| Feature schema | `gate9-adult-feature-schema-v1`: ordered 13 features, numeric and categorical lists, natural-missing token `?` | features.py:25, 72-102 |
| Canonical JSON | `sort_keys`, separators `(",", ":")`, `ensure_ascii`, `allow_nan=False` | features.py:44-50 |
| Excluded from the key | labels, masks, row ids, source file name, encodings, fitted vocabulary | SD:116; grouping.py:42-47 |
| Numeric tokens | kept as spelled (no float conversion), so `40` and `40.0` are different tokens | SD:116; features.py:166-193 |
| Identity assumption | An exact-feature key is not a fuzzy identity inference. Adult has no entity id in the sources, so exact-feature groups are a proxy for entity clusters (OD-14). | SD:98, 116; DRAFT:49 |

The same feature vector gets the same key in `adult.data` and `adult.test` (grouping.py:42-47).

### 4.2 Source-qualified row ids

A row id is `<release>:<source_file>:<physical_line>` with source file `adult.data` or `adult.test` and a 1-based physical line number (features.py:125-140; SD:118). The same line number in two files is two different rows. Ordering of members is numeric on `(release, source_file, line)`, not text order (features.py:119-123).

### 4.3 Duplicates inside a file

All rows are kept; nothing is deduplicated (DRAFT:19, 49; SD:98). Groups with conflicting labels, if any, are kept intact and reported only through the authorized evaluator after the lock, never by inspecting test labels beforehand (SD:98; DRAFT:49).

### 4.4 Test-connected quarantine

| Step | Rule | Source |
|---|---|---|
| Test membership | Fixed. All official test rows are retained. | SD:95, 124; DRAFT:53 |
| Connected groups | Every exact-feature group that has at least one row in `adult.test` and at least one row in `adult.data`. The manifest lists them as `test_connected_group_keys`. | source_manifest.py:203-213, 229 |
| Quarantine | Every `adult.data` row in a test-connected group is removed from all development roles before any role allocation. | SD:124; grouping.py:90-117; DRAFT:53 |
| Record | Quarantined row ids, group ids, reason `test_connected_exact_feature_group`, original and remaining row and group counts. | grouping.py:33, 76-87; SD:124 |
| Inputs | The `adult.data` records plus a caller-supplied set of connected group keys (grouping.py:90-99). That set comes from `connected_group_key_set`, which needs the manifest **and the bytes of both files** and rebuilds the manifest from them with `verify_against_bytes` (source_manifest.py:428-445, 448-465). Quarantine therefore needs the `adult.test` bytes (read label-blind), not only the manifest. | grouping.py:90-99; source_manifest.py:448-465 |
| If this leaves an unsupported role | The Adult test source is ineligible for this analysis until a reviewed rule is set (OD-15; section 10, step 3). | DRAFT:53; SD:122 |

SD:118 also allows coarsening by equal entity id; with no entity id in the sources this reduces to the exact-feature key. SD:124 says "connected component", DRAFT:53 says "matching feature groups"; under exact-feature keys the two are the same set, noted as C-03.

---

## 5. Missingness intervention

### 5.1 The block and the five scenarios

| Scenario (Adult analogue) | Definition | Source |
|---|---|---|
| Baseline | No injected missingness; natural `?` kept | DRAFT:61; G3:42-43 |
| MCAR 0.10, MCAR 0.30 | Cellwise, over originally observed eligible cells, on one shared uniform matrix per partition so that mask(0.10) is a subset of mask(0.30) | G3:44-48; missingness.py:137-142, 190-197 |
| Employment block | Row probability 0.50. A selected row has `workclass`, `occupation` and `hours-per-week` nulled together. | SD:128; DRAFT:61; missingness.py:27-28, 99-109 |
| Matched cellwise MCAR | Cellwise Bernoulli at the realized aggregate new-missing rate of the block (see 5.3). Whose realized block rate drives the pool mask, and the test mask, is open (OD-08). | DRAFT:61; G3:53-60 |

Pool and test masks use distinct streams; equal seeds are rejected (missingness.py:118-134; SD:170, 174). The scenario names used in code for Bank (`history_block_0_50`, `mcar_matched_history`; `shiftguard/shiftguard/repeats/models.py:34-37`) are Bank-owned; Adult scenario identifiers are `<<OPEN DECISION>>` OD-08. **Streams.** The seed leaves `pool_block`, `test_block`, `pool_mcar`, `test_mcar` (SD:170) are meant to feed `employment_outage_mask_pair(pool_seed, test_seed)` (missingness.py:118-134) and `shared_mcar_uniforms(n_rows, seed)` (missingness.py:137-142); which leaf feeds which call, and the row order handed to the generators (proposed: numeric source-qualified row-id order of each partition), are `<<OPEN DECISION>>` OD-11. For the matched scenario, SD:51 records that the legacy runner used the test target rate for pool MCAR; whether the Adult pool uses the pool's own realized block rate or the test's is OD-08 and is tied to SCI-03 (OD-04). This is a design mapping, not an implemented or scientifically equivalent version of Bank's history block (DRAFT:61).

### 5.2 Zero-observed-cell semantics and the two denominators

The two rates are kept separate in code and must not be conflated (SD:36, 128; missingness.py:200-243).

| Quantity | Numerator | Denominator | Use | Source |
|---|---|---|---|---|
| Aggregate realized new-missing rate | cells newly set to null by the intervention | cells that were **originally observed** (not `?`) across the 13 predictors in the partition | scenario matching and reporting | SD:128; DRAFT:61; missingness.py:29, 214-222 |
| Fraction-bin routing value (per row) | number of features newly injected in that row | 13 (the eligible feature count) | routing in `source_fraction_binned_temperature` | SD:128; missingness.py:211, 225-227; G3:105-108 |

Natural `?` cells are excluded from both the numerator and the aggregate denominator (SD:128; missingness.py:259-268). Fraction bins are ten equal-width bins with index `min(9, floor(10 f))` and minimum support 10 per bin (G3:107-110; DRAFT:23).

**Zero-observed semantics as implemented (proposed rule, to be confirmed at lock, OD-07).** The sources declare the two denominators but not these edge cases, so each rule below cites the code and not a protocol statement:

1. **Row selection ignores observed state.** Each row consumes one uniform in row order; the stream depends only on the seed and the row count (missingness.py:99-109). A selected row with no observed cells in the block is still "selected" and is still counted as a row.
2. **Nothing is injected in already-null cells.** Masking a null cell leaves it null and counts as natural, not new (missingness.py:259-268, 295-301). A selected row whose three block cells are all `?` injects zero cells.
3. **Row routing.** Such a row has injected count 0, so its fraction-bin value is 0/13 = 0 and it routes to bin 0 (missingness.py:210, 225-227). A row with only some block cells observed injects only those cells.
4. **Aggregate rate with zero denominator.** If a partition has zero originally observed eligible cells, the aggregate rate is `None` (unavailable), never 0.0 (missingness.py:218-222). A comparison that needs it is `impossible` and not qualified (G3:58, 60).
5. **A row with zero originally observed cells in the block contributes 0 to the numerator and 0 to the aggregate denominator for the block cells.** It still contributes its other observed cells to the denominator, which is across all 13 predictors.

### 5.3 Matched cellwise comparison

The matched scenario uses cellwise Bernoulli at the realized aggregate rate from 5.2, strategy `bernoulli_matched_rate`, with requested rate, realized rate (numerator and denominator), matching status and residual persisted (G3:53-60). Bank's matching tolerance is 0.02 and its statuses are `exact_match`, `within_tolerance`, `outside_tolerance`, `impossible` (G3:58). The Adult adapter does not implement matching yet: no match code exists in `shiftguard/shiftguard/adult_adapter/`. Whether Adult inherits the 0.02 tolerance is an `<<OPEN DECISION>>` (OD-08). The 0.02 rule is not SCI-03 authority (DRAFT:25; SD:51).

### 5.4 Source remasking

DRAFT:23 and DRAFT:61 keep the four equally weighted source regimes (clean, MCAR 0.10, MCAR 0.30, block at row probability 0.50) and say to use "the same ... source-remasking regime weights". The Adult source-remask adapter with a 13-feature denominator is not implemented (SD:36, 42, 128). The exact Adult regime definition is `<<OPEN DECISION>>` OD-09.

---

## 6. Roles and allocation

### 6.1 Role fractions and the grouped profile

| Role | Target fraction | Source |
|---|---|---|
| train | 0.6875 | adult.py:78-82; shiftguard/configs/adult-confirmatory.yaml:11-14 |
| source_cal | 0.1875 | same |
| target_pool | 0.1250 | same |
| evaluation | official `adult.test` membership, fixed (`fixed_external`) | SD:95; DRAFT:53 |

The development roles are allocated by the **grouped largest-deficit profile** `gate9-adult-grouped-allocation-v1` (grouping.py:32). It is a new, separately versioned profile. It does not replace `make_adult_role_splits`, which permutes rows and rounds counts (adult.py:140-165; SD:126). The legacy splitter and the Bank splitter are not changed (SD:34, 41).

Algorithm, outcome-blind (SD:120; grouping.py:163-223):

1. Start from the development rows that remain after quarantine (section 4.4). Let N be that row count; targets are N times (0.6875, 0.1875, 0.125), kept as exact rationals.
2. Order groups by SHA-256 of canonical JSON `["gate8-group-order-v1", split_seed, group_id]` (grouping.py:31, 182-184), ties by `group_id`.
3. Give each whole group to the role with the largest `target_rows - assigned_rows`; ties break in the fixed order train, source_cal, target_pool.
4. Append members in numeric source-qualified row-id order.
5. No label balancing, no retry for better scores, no tuning on class counts or accuracy (SD:120, 122; DRAFT:51).

The `split_seed` for each outer repeat is the outer repeat's `split` stream from the nested seed schedule (SD:170); the sources say "split_seed" without naming it, so this binding is OD-12.

### 6.2 Achieved fractions and unsupported roles

Fractions are targets, not exact row-stratified rounding (SD:122). Reported for every outer repeat: achieved row and group fractions per role, deviation from target in rows, largest group size, quarantined counts, and the allocation digest (SD:122, 124; grouping.py:120-149, 211-223). **Class counts (OD-13).** DRAFT:51 asks for class counts. Development-role class counts come from `adult.data` labels, which are development data; SD:122 forbids tuning on class counts, not reporting them. They are reported once per outer repeat after that repeat's allocation is frozen, and are never used to change the allocation. Evaluation (test) class counts, and test-label duplicate conflicts (SD:98), are reported only through the evaluator after the unseal.

Unsupported-role rule: an empty role, or a `target_pool` of fewer than 200 rows, gives `UNSUPPORTED_ROLE` and the grid is never silently shrunk (SD:122; grouping.py:34, 206-210). 200 equals the largest budget (`shiftguard/shiftguard/repeats/models.py:38, 60`). Under that status memberships are reported but must not be trained on (grouping.py:157-160). A one-class fitting role triggers the frozen failure and fallback rules after authorized label access, not a new allocation (SD:122; G3:181-185). Role support does not need labels, so it can be checked before the lock: section 10, step 3, and OD-15.

### 6.3 Evaluation membership

`fixed_external`: the same exact evaluation rows and groups in all five outer repeats, independent of every training, source and pool role. For Adult this is official test membership; only development-file roles vary by outer seed (SD:95). Which rows are in the cohort (all test rows, or all minus a rejected line) is OD-16. The conditional interval then concerns evaluation-group sampling with the fits, seed schedule, masks and acquired prefixes fixed (SD:95).

---

## 7. Methods, predictors, budgets and seed schedule

Copied from the sources. Nothing is added. Seed numbers are declared for the Gate 8 Bank design (DRAFT:39); DRAFT:61 asks Adult to use the same paired seed nesting, but does not say that the numbers are reused, so the seed values below are not declared for Adult (OD-11).

| Element | Declared value | Source |
|---|---|---|
| Predictors | `logistic_regression`, `random_forest` | DRAFT:21; `shiftguard/shiftguard/repeats/models.py:33` |
| Methods (8) | `raw`, `source_temperature`, `source_remasked_temperature`, `source_fraction_binned_temperature`, `target_temperature`, `target_platt_logodds`, `target_beta`, `target_isotonic` | DRAFT:21; G3:76-85 |
| Budgets | 0, 25, 50, 100, 200; budget 50 is the only primary budget | DRAFT:21, 37 |
| Cost pairs | (1,1) (1,4) (1,9) (4,1) (9,1) with thresholds 0.50 0.20 0.10 0.80 0.90; secondary, descriptive | DRAFT:45; G3:114-125 |
| Metrics | binary Brier as MSE (`scale_by_half=true`); log loss clip 1e-15; 10-bin reliability; decision loss `(C_FP*FP + C_FN*FN)/N` | DRAFT:25 |
| Outer seeds | 41001–41005 (declared for the Gate 8 design; Adult reuse of the numbers is OD-11) | DRAFT:39; `shiftguard/shiftguard/repeats/models.py:31` |
| Inner ids | 51001–51010 (same caveat, OD-11) | DRAFT:39; `shiftguard/shiftguard/repeats/models.py:32` |
| Seed algorithm | `gate8-nested-v1`, NumPy 2.5.3. The normative text is SD:170-172 (uint32 `generate_state(1)` respawn at each level; the outer `spawn(2)` gives split then model, model respawned with two children; the inner `SeedSequence([outer, inner]).spawn(3)` gives mask, acquisition, source_remask; mask respawned with four children in order pool_block, test_block, pool_mcar, test_mcar; source-remask uses the frozen PCG64 root and `integers(0,1000000,size=2)` children in order source_mcar, source_block). This table does not restate it. The golden 50-map digest `68900ea10536435e183f1f57d47154281f7c32db34a5f837b369330693bbffee` (SD:207, a synthetic engineering vector) is bound as the implementation check. | SD:170-172, 207; `shiftguard/shiftguard/repeats/models.py:28-29` |
| Reuse | One fitted preprocessor and model per predictor per outer repeat, trained on that outer's train role only; acquisition is one label-blind order per outer/inner and budgets are its nested prefixes; no refit on source, pool or test | SD:174; G3:37, 143-145 |
| Fallback chain | each method resolves down its own chain; failed raw prediction gives null metrics | G3:158-186; SD:110 |
| Fraction-binned map | ten equal-width bins, minimum support 10, fallback to `source_remasked_temperature` then `source_temperature` then `raw` | G3:107-110; DRAFT:23 |
| Design size | 5 outer x 10 inner = 50 coordinates; no 1x20 or other reduced design without a prospective amendment | DRAFT:39; SD:43 |

**Not declared for Adult in the sources (all `<<OPEN DECISION>>`):**

| Item | Why open | ID |
|---|---|---|
| Adult preprocessing and model hyperparameters | G3:20-35 declares them for Bank's 10 features (3 numeric, 7 categorical). For Adult the sources require a separately reviewed adapter (SD:42, 128) and give only the numeric/categorical split (adult.py:50-59). | OD-10 |
| Adult seed schedule beyond DRAFT:39 | `shiftguard/configs/adult-confirmatory.yaml:10` has one `master_seed: 41001` while DRAFT:39 declares a 5x10 nested schedule (C-05). DRAFT:61 asks for the same paired seed nesting for Adult; whether the Bank numbers are reused, which seed is the `split_seed` and which leaf feeds which mask call are not declared. | OD-11, OD-12 |
| Adult source-remask regime definition | see 5.4 | OD-09 |
| Resource feasibility of the Adult 5x10 run | unverified for any dataset (SD:43, 197) | OD-17 |

The Bank Gate 8 run has not run on real data as of the last log entry (run 11, LOG:310-320, which records no Bank run); the freeze is planned for on or after 20 October (LOG:261, 273-274, run 9; LOG:305-307, run 10). Nothing in this amendment depends on its results.

---

## 8. Primary contrast and analysis

Mirrors Gate 8 (DRAFT:33-37; SD:62-112; RM:468-492), with one difference: the Gate 8 Bank manifest sets `hypothesis_decision_supported: false` and the `bank_overlap_diagnostic` split profile (RM:486-488), while Adult uses `fixed_external` with a decision reading (8.3).

### 8.1 Primary contrast

`target_temperature` at budget 50 minus `source_fraction_binned_temperature` at budget 50. Endpoint: paired binary Brier difference (MSE scale, no extra factor 1/2). It compares complete strategies, including their declared valid fallbacks, and is not a target-label-only effect (DRAFT:11, 33; SD:31, 66).

Eight shifted cells: 2 predictors x 4 scenarios (employment block, MCAR 0.10, MCAR 0.30, matched cellwise), each weight 1/8. Baseline is reported separately and is not in the primary average (DRAFT:35). Negative values favor the target strategy.

```text
delta[o,i,c] = sum_g S[o,i,c,g] / sum_g n[o,g]      (row-count denominator within the cell)
inner[o,i]   = (1/8)  * sum_c delta[o,i,c]
outer[o]     = (1/10) * sum_i inner[o,i]
theta        = (1/5)  * sum_o outer[o]
```

Each original row counts once inside its cell, including duplicates; groups are not averaged with equal weight (SD:68-77). The five outer summaries, the ten inner summaries per outer, the within-outer SD (`ddof=1`) and the SD of the five outer values are reported as split and seed sensitivity, not as a standard error (SD:79). The 50 executions are not 50 independent datasets (DRAFT:41; SD:79).

### 8.2 Interval

Conditional group bootstrap (SD:81-104; `shiftguard/shiftguard/repeats/uncertainty.py:30-35`):

| Setting | Value |
|---|---|
| Mode | `fixed_external` |
| Draws | 10,000, draw ids 0 to 9999 |
| Draw stream and weights | For draw `b`: `np.bincount(Generator(PCG64(SeedSequence([61001, 8, 1, b]))).integers(0, G, size=G), minlength=G)` (SD:83, 172; uncertainty.py:32-33, 103-107) |
| Resampling unit | exact-feature evaluation group. The universe is the groups of the `adult.test` evaluation cohort (OD-16), G of them, **sorted once by ascending group id** (uncertainty.py:96-100; SD:83); G indices are drawn uniformly with replacement |
| Multiplicity | one shared integer weight per group across every method, predictor, scenario, inner and outer repeat; duplicate multiplicity multiplies both loss sums and row counts |
| Interval | linear-interpolation percentile, quantiles 0.025 and 0.975 |
| Zero evaluated mass in any outer, or fewer than two groups | interval unavailable; the draw id is recorded; no redraw |

**Inferential scope, as the sources state it.** The interval is conditional on the fitted outer training partitions, seed schedule, masks and acquired prefixes. It reflects evaluation-group sampling only. It does not include training-sample population uncertainty and does not establish generalization across datasets or populations (SD:95; DRAFT:43). It is an approximate percentile procedure, not an exact test: no p-value is produced (SD:108). Exact-feature groups are a proxy for independent persons; that assumption is not established (SD:98).

This replaces the Blueprint 13.6 outer-first bootstrap with a conditional-on-fits group interval; the two estimate different uncertainty, and SD:17 and SD:104 say human approval must reconcile that. Under author lock no such approval exists; the difference is disclosed and decided in OD-05. The Blueprint 13.6 outer-first interval is **not** a primary interval and is not reported as one; section 8.2 is the only primary interval.

### 8.3 Decision reading and multiplicity

One primary contrast, one nominal two-sided 0.05 procedure, one 95% interval (DRAFT:43; SD:108). After lock, an interval entirely below zero supports the target-favoring direction, entirely above zero the reverse, and an interval containing zero is inconclusive (SD:108). SD:108 words this as "following actual approval/lock"; under author lock the reading is the same text without any approval claim (OD-06). Everything else (other budgets, methods, scenarios, predictors, metrics, cost pairs) is descriptive. Choosing the best budget, seed or interval is not allowed. A secondary confirmatory claim needs a prospective multiplicity amendment (SD:108; DRAFT:43).

### 8.4 Missing evidence

If any required primary pair is absent, failed, unqualified or of unknown authority, the primary estimate and interval are null with all reasons kept; remaining cells are never reweighted (SD:112). In the Gate 8 manifest, qualification stays `unknown_authority` while SCI-03 is unresolved and the expected primary estimate is `MissingEvidence` (RM:490-491; SD:44, 51, 112).

**Which primary cells depend on SCI-03.** In the Gate 8 development adapter qualification is keyed to the source binding, not to the scenario: any real (non-synthetic) source gets `unknown_authority` (development_adapter.py:134-138), the typed SCI-03 reason is attached to every such condition (development_adapter.py:149-152, 739), and the primary estimate is then `MissingEvidence`. So all eight primary shifted cells (employment block, MCAR 0.10, MCAR 0.30 and matched cellwise, each for two predictors) depend on SCI-03, not only the matched cellwise cell. SD:51 places the original SCI-03 issue in the pool-versus-test qualification of pattern-versus-rate comparisons, but the code does not restrict `unknown_authority` to that comparison. No Adult adapter exists yet, so how an Adult adapter would qualify cells is part of OD-04.

SCI-03 is unresolved and an author lock cannot supply that authority. If the lock were made and `adult.test` unsealed with OD-04 open, the primary result would be `MissingEvidence` by construction and would use up the single unseal. Hence OD-04 is a lock precondition and no unseal may happen while it is open (section 9A). This is stated deliberately, not hidden.

SCI-04 (boundary semantics of the temperature fit) is carried unchanged and is not called scientifically approved (SD:44, 52; DRAFT:25). DRAFT:65(3) requires both SCI-03 and SCI-04 authorities to be source-bound, so OD-04 covers SCI-04 as well (REG:176-179).

---

## 9. Reporting rules

1. Report everything, including null, adverse, failed and unqualified conditions, all 50 coordinates and the full 400-slot condition grid per coordinate (DRAFT:27, 67; SD:110, 180).
2. Requested and resolved methods, fallback reasons, fit failures per unique calibrator and prediction failures per attempt are reported (DRAFT:27; G3:186).
3. No re-run after the unseal. A coordinate with a recorded failure is not re-run to replace it; a crash that left no record is a restart, not a replacement (scripts/gate8_run_development.py:11-26 for the Gate 8 pattern). A corrupt completion stops the run.
   Failures after the unseal are handled as follows (the byte check against the bound manifest is a pre-unseal step, section 10, step 7):
   - a failure before any label is read may be fixed only in a disclosed stage-2b commit that touches no locked item, re-checks the golden seed digest and reproduces the stage-1 allocation digests (section 10, step 6), after which the run is restarted;
   - any fix made after outcomes are computed makes the analysis exploratory and it is labelled so;
   - a restart after a crash uses the same commit and must give byte-identical content for everything already written.
4. No selection of cells, budgets, seeds or intervals after seeing outcomes (DRAFT:27; SD:108).
5. Group-level loss sums, row-wise differences and predictions are evaluator-private and never published before release (SD:182).
6. Public wording: only the labels in section 1. Secondary quantities carry nominal intervals marked descriptive (DRAFT:43).
7. The unsealed outcome is reported even if it contradicts the Bank development direction.

**What may never change after the lock** (any change makes the analysis exploratory and must be disclosed as such):

- the 13 predictors, the `?` rule, the label rule (strip and every trailing period), the group key and its versions, and the group order version;
- preprocessing and model hyperparameters (OD-10);
- the quarantine rule and the allocation algorithm, role fractions, 200-row pool floor and the five outer allocation digests;
- the evaluation cohort (OD-16);
- the scenario definitions, block features, 0.50 row probability and both denominators;
- the source-remask regimes and weights (OD-09), and the matching tolerance and qualification rule (OD-08);
- predictors, methods, budgets, metric definitions, cost pairs and fallback chains;
- the seed schedule, the mask-leaf mapping and all derived seeds;
- the bound hashes in section 2, the protocol text and the manifest; the source commit and dependency lock are bound at stage 2 (section 10) and may change afterwards only through a stage-2b commit (section 9, item 3);
- the primary contrast, weights, interval procedure, draws, quantiles and decision reading;
- the exposure and review labels.

---

## 9A. Lock preconditions

This section was added in r2 after the r1 model consistency check found that, as drafted, a lock could be made that covers nothing and an unseal could be spent on a result that is null by construction. It lists decisions that this draft deliberately does not settle: no scientific value is chosen here for any of them.

**Blocking open decisions (must be settled before the lock):**

- OD-01 test bytes, hash, counts and manifest digest, plus the full train digest
- OD-02 the two-stage binding scheme (section 10, C-10)
- OD-04 SCI-03 qualification for Adult, and the SCI-04 disposition
- OD-08 matching tolerance, qualification, whose realized rate, scenario ids
- OD-09 source-remask regimes
- OD-10 preprocessing and hyperparameters
- OD-11 and OD-12 seed reuse, split_seed and the mask-leaf mapping
- OD-15 the unsupported-role rule
- OD-16 the evaluation cohort
- OD-19 the guard and evaluator procedure, including a bound, aligned test-label parser (2.2)

OD-04 is read as covering SCI-04 too (DRAFT:65(3); REG:176-179). The author cannot supply SCI-04 authority, so its likely disposition is to carry `fraction_binned.py` unchanged with no claim of approval. Rule 2 keys the no-unseal rule to SCI-03 alone because only SCI-03 forces `MissingEvidence`; SCI-04 affects labelling, not whether a primary estimate exists. OD-15 stays blocking; its proposed rule is in section 10, step 3.

**Rules.**

1. The lock commit is forbidden while any item above is open. A blocking item is settled only when its value is written into this file with a dated one-line rationale; leaving a placeholder or a deferral is not settling it. A lock that leaves one open would cover nothing for that item.
2. No unseal while OD-04 (SCI-03 qualification) is open, because the primary result would be `MissingEvidence` by construction and would use up the single unseal (8.4). The primary cells that depend on SCI-03 are all eight shifted cells, since the Gate 8 adapter assigns `unknown_authority` to any real source regardless of scenario (development_adapter.py:134-138; RM:490-491).
3. OD-01 needs the `adult.test` bytes, which need the owner's permission to download (OWNER_ACTIONS item 11, which the r1 check records as still unanswered). Until that is answered, the lock cannot be made.
4. The lock binds the SHA-256 of each cited non-public source (SD, DRAFT, REG and `shiftguard/var/datasets/adult.manifest.json`, which is git-ignored at `.gitignore:12`), or the cited lines are quoted in the lock commit. Without that, the line citations in this file cannot be checked by a reader.

**Items that may stay open, with the declared default that applies if they do** (the r1 check's defaults; they are declared defaults, not scientific approvals):

| ID | Declared default |
|---|---|
| OD-03 | Exposure of `adult.test` stays UNKNOWN; results carry the section 1 labels. |
| OD-05, OD-06 | Wording only. Section 8.2 is the only primary interval. |
| OD-07 | The zero-observed-cell rules as drafted in 5.2. |
| OD-13 | Development-role class counts are reported after the allocation is frozen; evaluation class counts only through the evaluator after the unseal (6.2). |
| OD-14 | Exact-feature groups are the only unit, with the independence caveat stated in results. |
| OD-17 | No reduced design; no unseal if the full 5x10 run is infeasible. |
| OD-18 | Development runs on `adult.data` are development tier only and may not change any locked item. |
| OD-20 | The source manifest is bound by digest only and not published. |

---

## 10. Lock procedure

Order matters; no step may read an `adult.test` label. Binding happens in two stages (C-10): stage 1 is the lock commit, stage 2 is a public execution-binding commit made before the unseal.

1. **Preconditions (section 9A).** Every blocking decision is settled and every `<<TO BIND BEFORE LOCK>>` is filled. If any is open the lock commit is forbidden. A placeholder is never left in a lock commit with a note.
2. **Dispositions.** Every non-blocking open decision either is settled or keeps its declared default (section 9A), each with a dated one-line rationale in this file. Every conflict C-01 to C-10 is given an explicit disposition. "Accepted" here means only: the author wrote a dated one-line disposition in this file. It is not review.
3. **Allocations and role support.** After the manifest exists, compute all five outer allocations once, label-blind (this needs the `adult.test` bytes through `connected_group_key_set`, source_manifest.py:448-465, but no label) and bind their digests in the lock. Proposed rule, awaiting disposition under OD-15 (which stays blocking): if any outer repeat is `UNSUPPORTED_ROLE`, `adult.test` is not unsealed.
4. **Model consistency check.** An Opus model consistency check of this file against the cited sources (PLAN:80). Its output is a model review. It is not human acceptance and is not described as peer review.
5. **Stage 1: lock commit.** Change the status line at the top from DRAFT to LOCKED and add the label "author-locked, not externally peer-reviewed". The lock binds the protocol text, the source manifest by digest only (OD-20; it is not published), the allocation digests and the SHA-256 of each cited non-public source (9A rule 4). Commit and push publicly before any test outcome is read. The commit hash and timestamp are the lock (PLAN:81-82). A commit timestamp is self-asserted, so the remote's push-receipt time is also recorded. The lock commit hash cannot be written inside the locked file (it would change the hash); it is cited afterwards in the results and in a later file.
6. **Stage 2: execution-binding commit.** Before the unseal, a second public commit binds the source tree and dependency-lock digests, the guard lift, the seed-map digest (checked against the golden digest in section 7) and the run manifest. Its diff is limited to implementing the locked text: any change to a scientific choice voids the lock. Engine wiring (PLAN:83) happens before it, and protected numerical owners that change must reproduce the Bank Gate 2/3 artifacts byte for byte (PLAN:83). The guard at adult.py:265-267 is lifted in this commit (OD-19). The stage-2 code must reproduce the five stage-1 allocation digests exactly. A later pre-label fix is a disclosed stage-2b commit with the same limits (section 9, item 3).
7. **Single unseal.** Before any label is decoded or any scoring starts, `verify_against_bytes` is run on the `adult.test` bytes against the bound manifest (source_manifest.py:428-445); the test file is then unsealed once, the locked analysis is run once, and the result is reported whatever it shows (PLAN:84). No unseal while OD-04 is open (9A).
8. After the unseal, re-runs, parameter changes and subset selections are forbidden, except as stated in section 9, item 3 (stage-2b fixes before any label is read).

If any step above is skipped the label "author-locked" is not used.

---

## 11. Open decisions and source conflicts

### 11.1 Open decisions

"Blocking" means a lock precondition (section 9A). Other items keep the declared default of 9A if left open.

| ID | Open decision | Where | Status |
|---|---|---|---|
| OD-01 | Test file binding: SHA-256, byte size, record count, line counts, manifest digest, release string, the full train-only manifest digest (only a prefix and suffix are logged) and the download/placement event. Needs `adult.test` (OWNER_ACTIONS item 11). `<<TO BIND BEFORE LOCK>>` | 2.1, 2.2 | Blocking |
| OD-02 | The two-stage binding scheme (C-10): what the lock binds (protocol text, manifest digest only per OD-20, allocation digests, SHA-256 of cited non-public sources per 9A rule 4) and what the execution-binding commit binds (source tree, dependency lock, guard lift, seed-map digest, run manifest), with the Adult analogues of the Gate 8 manifest digests | 2.3, 10 | Blocking |
| OD-03 | Exposure of `adult.test`: remains UNKNOWN; no custodian is named; whether to seek custodian evidence before or after the lock. Until then results use the section 1 labels. | 1; SD:190-191 | Default: UNKNOWN plus labels |
| OD-04 | SCI-03 pool-qualification scope for Adult, and the SCI-04 authority (DRAFT:65(3); REG:176-179). With it unresolved, the primary estimate is `MissingEvidence` (RM:490-491) for all eight primary cells. Needs an owner decision recorded with its authority. No unseal while open. | 8.4, 9A | Blocking |
| OD-05 | Blueprint 13.6 versus the conditional group bootstrap: author-lock disposition and wording | 8.2 | Default: wording only; 8.2 is the only primary interval |
| OD-06 | Decision-reading wording under author lock (SD:108 says "approval/lock") | 8.3 | Default: wording only |
| OD-07 | Confirm the zero-observed-cell rules in 5.2 (taken from missingness.py, not declared in SD/DRAFT) | 5.2 | Default: as drafted |
| OD-08 | Adult scenario identifiers; whether the 0.02 matching tolerance and the four match statuses apply to Adult; the qualification rule; whose realized block rate drives the pool and the test matched MCAR (SCI-03, SD:51); the matched-rate adapter does not exist | 5.1, 5.3 | Blocking |
| OD-09 | Adult source-remask regimes and weights (four regimes with the block at 0.50, 13-feature denominator) | 5.4 | Blocking |
| OD-10 | Adult preprocessing and model hyperparameters | 7 | Blocking |
| OD-11 | Adult seed schedule: DRAFT:39 and DRAFT:61 declare the seed nesting (v0.3, reused by Gate 8); what is open is confirming the reuse for Adult and retiring the single yaml `master_seed` field in the sealed config. Also open: whether 41001–41005 and 51001–51010 are reused, which seed leaf feeds `employment_outage_mask_pair` and `shared_mcar_uniforms`, and the row order fed to the generators | 5.1, 7 | Blocking |
| OD-12 | Which seed is the `split_seed` in the group-order hash (assumed: outer `split` stream) | 6.1 | Blocking |
| OD-13 | Class-count reporting for grouped roles: development-role counts come from `adult.data` labels (development data) and are reported once the allocation is frozen; SD:122 forbids tuning on class counts, not reporting; evaluation counts only through the evaluator after the unseal | 6.2 | Default per 9A |
| OD-14 | Entity clustering: no Adult entity id is declared; confirm exact-feature groups as the only unit and state the independence caveat in results | 4.1, 8.2 | Default: exact-feature groups plus caveat |
| OD-15 | What happens if any outer repeat is `UNSUPPORTED_ROLE` after quarantine (DRAFT:53 says the test source becomes ineligible; no fallback is declared). Role support is checkable before the lock (10, step 3). Proposed value, awaiting disposition: do not unseal if any outer is unsupported. | 4.4, 6.2, 10 | Blocking |
| OD-16 | The fixed evaluation cohort: all test rows, or all minus any rejected line; the count is verified from the manifest, not assumed from the documented 16,281; it also defines the bootstrap group universe | 2.2, 6.3, 8.2 | Blocking |
| OD-17 | Resource feasibility of the Adult 5x10 run (memory, time, storage) | 7 | Default: no reduced design; no unseal if infeasible |
| OD-18 | Role of development runs on `adult.data` (PLAN:83 allows them): development tier, may not change any locked item, and whether any are run before the lock | 1 | Default: development tier only |
| OD-19 | How and when the Adult guard (adult.py:265-267) and the sealed config (`status: NON_EXECUTABLE_BEFORE_GATE_8_PROTOCOL_LOCK`) are lifted (stage 2 commit), and the evaluator adapter that gives labels only to the evaluator (G3:149-152; SD:182 requires separate authorization), including a bound test-label parser aligned to `uci-adult-2:adult.test:<physical line>` ids: `clean_adult_rows` (adult.py:95-123) renumbers rows, skips blanks and would raise on the `|` header | 1, 10 | Blocking |
| OD-20 | Whether the label-free source manifest (which lists duplicate-group row ids, source_manifest.py:186-189) may be published, given 2.3 | 2.3 | Default: bound by digest only, not published |

### 11.2 Source conflicts

| ID | Conflict | Sources | Disposition in this draft |
|---|---|---|---|
| C-01 | Lock authority. The v0.3 lock gate and register require an independent human approver and a custodian audit before any lock (DRAFT:65; REG:216-223; SD:5, 190-191). PLAN replaces this with an author lock and an Opus model consistency check (not human review), no external approval (PLAN:78-82). | DRAFT, REG, SD vs PLAN | Not resolved. The amendment is labelled author-locked only and never described as satisfying the v0.3 lock gate; the register flags stay false. Owner to confirm this scoping. |
| C-02 | Role-split contract. DRAFT:59 says to preserve the 68.75/18.75/12.50 split contract unless a reviewed amendment binds grouped allocation; adult.py:140-165 permutes rows and rounds counts; SD:120 uses grouped largest-deficit. | DRAFT:59, adult.py:140-165, SD:120 | This amendment is the grouped binding. Whether it counts as the "reviewed amendment" DRAFT:59 requires depends on C-01. |
| C-03 | Quarantine wording: SD:124 quarantines "any test-connected component" (entity or feature); DRAFT:53 quarantines "matching feature groups". | SD:124 vs DRAFT:53 | Same set when no entity id exists (section 4.4). |
| C-04 | Tier wording. `shiftguard/configs/adult-confirmatory.yaml:5` says `evaluation_tier: confirmatory`; DRAFT:67 says without verified exposure separation the Adult source may not be called confirmatory. | yaml vs DRAFT; PLAN:66 moves the confirmatory clause to Gate 9 | This draft follows DRAFT:67 ("prospective Adult analysis under author lock"). The yaml is not edited here. |
| C-05 | Seed form. The sealed yaml has a single `master_seed: 41001`; DRAFT:39 declares nested 5x10 seeds (outer 41001 equals that value). The yaml `protocol_id` is `sg-protocol-1.0-draft`, whereas the code protocol version is `shiftguard.research.protocol-draft.v0.3` (`shiftguard/shiftguard/repeats/models.py:27`). | yaml:4,10 vs DRAFT:39, models.py:27 | See OD-11. |
| C-06 | Lock naming. The guard message, the yaml status and G3:231 tie the seal to "Gate 8 protocol lock"; PLAN assigns the Adult lock to Gate 9. | adult.py:267, yaml:2,7, G3:231 vs PLAN:73-84 | Text to be reconciled when the guard is lifted (OD-19). |
| C-07 | Test-file handling. G3:218 forbids downloading or inspecting `adult.test` in Gate 3; Gate 9 prerequisite 1 requires downloading it for the label-blind manifest (PLAN:77; OWNER_ACTIONS:107-116). SD:126 and SD:128 are earlier-phase restrictions on real data. | G3:218 vs PLAN:77 | Gate 3's rule was scoped to Gate 3. The download is an exposure event to be recorded (section 2.2). Pending owner permission. |
| C-08 | Wording of the primary decision text: SD:108 "following actual approval/lock" versus no approval under author lock. | SD:108 | See OD-06. |
| C-09 | Custodian wording. PLAN:77 calls prerequisite 1 "Custodian evidence" and AUTOPILOT:78 says "custodian manifest"; `source_manifest.py:80` and LOG:291 say "author-built, not custodian-attested"; U-08, SD:124 and EXT-FEATURE-GROUP-AUDIT (SD:195) remain unmet. | PLAN:77, AUTOPILOT:78 vs source_manifest.py:80, LOG:291 | Not resolved. This draft follows the tool's own status: the manifest is author-built, never described as custodian evidence. |
| C-10 | Binding timing. SD:40 and DRAFT:65(4) require code, dependency lock and data manifests to be bound at the lock; PLAN:83 puts engine wiring after the lock (prerequisite 3 follows prerequisite 2) and the guard is lifted after it. The source commit cannot be both frozen at the lock and changed afterwards. | SD:40, DRAFT:65, PLAN:78-84 | Two-stage binding. Stage 1, the lock commit, binds the protocol text, the manifest and the allocation digests. Stage 2, a public execution-binding commit before the unseal, binds the source and dependency digests, the guard lift, the seed-map digest and the run manifest; its diff is limited to implementing the locked text. This is a disposition proposed by the author and is not review (OD-02). |

### 11.3 Author self-check of citations (not a review)

The r1 check found the grouping.py citations (all 193 lines too high), the source_manifest.py citations (about 3 lines low), and two LOG citations to be wrong. In r2, and again for every citation added in r3, every cited line below was re-derived by the drafting model from the current files on 19 Oct 2026 (`source_manifest.py` as changed in commit `645aace`; LOG with its run-11 entry). This is a model re-derivation, not human review, and it covers only the text at the cited lines.

- 13 predictors, dropped `education`, `?` to null: adult.py:33-48, 112-113; DRAFT:59; REG:128; G3:219-223.
- Frozen train hash and 32,561 records: adult.py:67, 70; shiftguard/var/datasets/adult.manifest.json:25-26.
- Block features, 0.50 probability and the two denominators: SD:128; DRAFT:61; missingness.py:27-29, 211-227.
- Group key, quarantine and allocation: SD:116-122; grouping.py:30-49 (versions, key), 76-117 (quarantine), 120-223 (allocation, unsupported roles).
- Manifest tool: source_manifest.py:80 (status), 84 (frozen release), 203-213 and 229 (connected keys), 221-224 (tool versions), 428-445 (`verify_against_bytes`), 448-465 (`connected_group_key_set`).
- Primary contrast and bootstrap parameters: DRAFT:33-37; SD:81-88; RM:468-479; `shiftguard/shiftguard/repeats/uncertainty.py:30-35, 96-107`.

### 11.4 Disposition of the parallel Opus model review of r1 (19 Oct 2026)

Source: `../../../verification/autopilot-20261018-run11/review-gate9-draft-r1.md` (model review, not human acceptance; recorded at LOG:320). Its Part A (the manifest code) is outside this file. Its Part B findings are dispositioned here as covered-by-r1-fix, applied-now (r3) or recorded-as-open.

| Finding | Disposition |
|---|---|
| 1 grouping.py cites | covered-by-r1-fix (r2) |
| 2 source_manifest.py cites | covered-by-r1-fix (r2); cites re-derived from the current file, commit `645aace` |
| 3 firewall contradiction | covered-by-r1-fix (r2) |
| 4 lock with unresolved bindings | superseded by the two-stage binding (C-10): the source commit and dependency-lock digests are bound at stage 2, not before the lock; unresolved bindings are forbidden in the lock (9A, step 1) |
| 5 binding timing | covered-by-r1-fix (C-10, two stages; stage 2b added in r3) |
| 6 custodian wording | covered-by-r1-fix (C-09); U-08, SD:124 and SD:195 added in r3 |
| 7 non-repo sources | applied-now: note in the short-name section and 9A rule 4 |
| 8 C-items range | covered-by-r1-fix (r2) |
| 9 rstrip rule | covered-by-r1-fix (r2) |
| 10 class counts | covered-by-r1-fix (r2, OD-13) |
| 11 matched-rate partition | covered-by-r1-fix (r2, OD-08, OD-04) |
| 12 SCI-04 in OD-04 | applied-now (8.4, OD-04, 9A) |
| 13 release forced by code, test bytes not pinned | applied-now (2.2, "Code pins" row) |
| 14 aligned test-label parser | applied-now (2.2, OD-19, 9A); the parser itself is recorded-as-open |
| 15 C-04 and PLAN:66 | applied-now |
| 16 repo-relative paths | partially applied / declined: paths stay workspace-relative because several cited sources are outside the public repository; those are marked non-public and their SHA-256 is bound at the lock (9A rule 4) |
| 17 seed declaration | applied-now (OD-11 reworded); confirmation of reuse for Adult is recorded-as-open |
| 18 publication of the source manifest | applied-now (2.3, digest only); publication is recorded-as-open as OD-20 |
| 19 hash in own commit | covered-by-r1-fix (10, step 5) |
| 20 C-07 SD:126, SD:128 | applied-now |
| 21 OD-18 PLAN cite | applied-now (PLAN:83) |
| 22 LOG run cite | covered-by-r1-fix (r2); run-11 entry now LOG:310-320 |
| 23 header wording | applied-now (2.2) |
| 24 labels | applied-now (H1, 11.3 heading, line 9 wording) |

---

Changelog

- r1, 18 Oct 2026: first draft.
- r2, 19 Oct 2026: applied the r1 model consistency check (../../../verification/autopilot-20261019-run11/gate9-draft-check-r1.md)
- r3, 19 Oct 2026: applied the r2 delta model check and dispositioned the parallel r1 review (../../../verification/autopilot-20261018-run11/review-gate9-draft-r1.md)
- r3.1, 19 Oct 2026: applied the r3 delta model check (status line, lock contents, SCI-04 disposition, two 11.4 dispositions, OD-11 wording, 11.3 scope).
