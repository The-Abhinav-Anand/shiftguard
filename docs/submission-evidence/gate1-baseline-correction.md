# Gate1 baseline correction

The local artifact `var/artifacts/ed919a121dbbaedb2960cc1d/` is superseded and must not be used: its Brier score was computed with an extra binary half-scale division.

The earlier corrected run `69cb729db238a7dd131bbd18` is preserved but superseded for Gate1 review after the validated-input, frozen-preprocessing, byte-hashed artifact, and append-only provenance changes below.

The current frozen-seed development identity is `7f3f12fe8464532ada86f280`, with logical content hash `7f3f12fe8464532ada86f28041f785b023774405fdf31bcb5993d6e4b0bd8d85`. It records Brier score `0.08820837511458743`, log loss `0.3131764240810899`, and `null` fields for the empty `0.9`--`1.0` reliability bin. This remains a development-only no-outage baseline, not scientific or confirmatory evidence.

This identity freezes median imputation and standard scaling for the three numeric features, an explicit categorical missing token, and one-hot encoding that ignores held-out categories. It records the resolved logistic-regression parameters and preprocessing configuration in deterministic content; each execution has a separate UUID and append-only audit provenance row. Existing local artifacts remain preserved.
