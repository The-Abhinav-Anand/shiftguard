# Adapting SHIFTGUARD to your own tabular dataset

**Status: documentation only.** The app and the approved presets run on the UCI Bank Marketing
data and nothing else. There is no upload, and the code deliberately refuses other datasets:
the experiment config rejects any feature list other than the frozen Bank one, and readiness
fails unless the Bank file matches its frozen SHA-256. This guide explains what a fork has to
change to run the same evaluation on another binary-outcome table, and why each guard exists.

A supported command-line path for your own CSV, run locally with no upload, is on the roadmap.

## What the evaluation needs from a dataset

| Need | Bank implementation | Why |
|---|---|---|
| A frozen source | `data/manifests/bank.json`: source URL, archive and member SHA-256, licence, citation | Every result is tied to exact bytes; a changed file is a different experiment |
| A canonical clean CSV | `shiftguard/datasets/bank.py`: `clean_bank_rows`, `write_clean_csv`, `FROZEN_CLEAN_DIGEST` | Stable column order, a `row_id` column and a 0/1 target `y`, hashed after cleaning |
| A feature list | `BANK_FEATURES` in `shiftguard/datasets/bank.py` | Predictors, masks and provenance all refer to features by name |
| A "history block" | `HISTORY_FEATURES` in `shiftguard/missingness/block.py` (`pdays`, `previous`, `poutcome`) | The structured outage removes a related group of fields together; pick a group that could plausibly fail together in your pipeline |
| Role splits | `ROLE_FRACTIONS` in `shiftguard/protocol/splits.py` (train 55%, source calibration 15%, target pool 10%, final test 20%), stratified on the label | The target pool supplies the 0–200 "new labels"; the final test is read only by the evaluator (the label firewall) |
| Preprocessing | `shiftguard/preprocessing/tabular.py` | Missing cells must reach the predictor in a defined way |

## Steps for a fork

1. **Write a manifest** for your source like `data/manifests/bank.json`: where the file comes
   from, its SHA-256, its licence and how to cite it. Use data you are allowed to use; do not
   commit private data.
2. **Write a loader and cleaner** like `shiftguard/datasets/bank.py`: emit `row_id`, your
   predictors and a binary `y`, and record the clean digest and row count.
3. **Choose the outage group.** Replace `HISTORY_FEATURES` with the fields that fail together
   in your setting. The random-cell outages (10% and 30%) and the matched-rate comparison need
   no change.
4. **Relax the frozen guards deliberately**, in your fork: `BaselineConfig.__post_init__` in
   `shiftguard/experiments/config.py` (feature list, seeds, protocol id) and the dataset
   identity check in `shiftguard/api/routes/health.py`. Replace them with checks against your
   own frozen identity rather than deleting them.
5. **Run the development tier first** with a copy of `configs/bank-stress.yaml` pointing at
   your CSV and manifest, then read the failures and fallbacks before the metrics.
6. **Keep the label firewall.** Final-test outcomes should only ever be read by the evaluator.
   Do not choose methods, budgets or thresholds by looking at final-test results.

`shiftguard/adult_adapter/` is a worked example of steps 1–3 for UCI Adult Income. It is an
engineering slice tested on fabricated records only; it has not been run on real outcomes.

## What not to claim from a fork

One seed on one split is development evidence. The repeat engine in `shiftguard/repeats/`
runs multiple seeds, but locking a protocol before looking at results is what turns a run
into a confirmatory one. Report failures and adverse metrics with the favourable ones.
