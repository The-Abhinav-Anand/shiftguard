# Third-party notices

Gate0 includes no bundled third-party source code, datasets, models, or binary assets.

Python runtime dependencies are declared in `pyproject.toml` and resolved into `uv.lock`. Frontend dependencies are declared in `frontend/package.json` and resolved into `frontend/package-lock.json`. Their own licenses apply.

The product frontend bundles Three.js 0.186.1 (MIT) and GSAP 3.15.0 (GSAP Standard License). Development typings use `@types/three` 0.186.0 (MIT). Their notices/licenses are retained in the installed dependency packages. No Manrope font file was added; the declared family uses available system fallbacks.
