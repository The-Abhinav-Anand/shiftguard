# Third-party notices

SHIFTGUARD itself is licensed under Apache-2.0 (see [LICENSE](LICENSE)). This repository
contains no third-party source code copied into it, no datasets and no model weights. Third-party
components reach a build or a running deployment as listed below; their own licences apply, and
their full licence texts are shipped inside each installed package.

Audited on 15 October 2026 against `uv.lock`, `frontend/package-lock.json`, the frontend imports
and the `Dockerfile`.

## Bundled into the committed frontend build (`shiftguard/static/`)

| Package | Version | Licence |
|---|---|---|
| React, React DOM | 19.3.0 | MIT |
| Plotly.js (`plotly.js/dist/plotly-basic`) | 4.1.1 | MIT |
| react-plotly.js | 4.1.0 | MIT |
| Three.js | 0.186.1 | MIT |
| GSAP | 3.15.0 | GSAP Standard "no charge" licence (<https://gsap.com/standard-license>) |

Their transitive dependencies are listed in `frontend/package-lock.json`. No font files are
bundled; the declared typeface falls back to system fonts.

## Python runtime (installed from `uv.lock`, not vendored)

Main direct dependencies: FastAPI 0.141.1 (MIT), Starlette 1.6.0 (BSD-3-Clause),
Uvicorn 0.52.4 (BSD-3-Clause), Pydantic 2.13.5 and pydantic-settings 2.15.0 (MIT),
SQLAlchemy 2.0.52 (MIT), Alembic 1.19.2 (MIT), psycopg 3.3.5 with psycopg-binary (LGPL-3.0;
the binary wheel bundles libpq under the PostgreSQL Licence and OpenSSL under Apache-2.0),
scikit-learn 1.9.0, NumPy 2.5.3 and SciPy 1.18.1 (BSD-3-Clause), Typer 0.27.2 (MIT),
PyYAML 6.0.3 (MIT) and the OpenAI Python client 1.109.1 (Apache-2.0). The complete resolved
set, with hashes, is in `uv.lock`.

psycopg is used unmodified as a dynamically imported library; its LGPL-3.0 terms allow
replacing it with another build.

## Container image

The `Dockerfile` builds on `python:3.13-slim` (Debian packages under their own licences) and
`node:22-alpine` (build stage only), copies `uv` from `ghcr.io/astral-sh/uv` (MIT or
Apache-2.0), and compiles SQLite 3.53.1 from the official source archive (public domain).
The judge deployment also runs the unmodified `postgres:16` (PostgreSQL Licence) and
`caddy:2` (Apache-2.0) images.

## Data and model services

- **UCI Bank Marketing** (Moro, Rita and Cortez, 2014, DOI 10.24432/C5K306), CC BY 4.0. It is
  downloaded and hash-checked at setup, not redistributed in this repository or the image.
- **UCI Adult** (Becker and Kohavi, 1996), CC BY 4.0: referenced by the adapter's manifest
  only; not distributed and not used for any result.
- **NVIDIA Nemotron** is called as a hosted model through Nebius Token Factory under the
  provider's terms. No model weights are included.
