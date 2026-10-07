"""Playwright-only local launcher for the explicit scripted test application."""

from __future__ import annotations

import os
from pathlib import Path
import threading
import time

import uvicorn

from shiftguard.api.test_harness import create_scripted_test_app
from shiftguard.settings import Settings


def main() -> None:
    attempt_dir = Path(os.environ["SG_GATE5_ATTEMPT_DIR"]).resolve()
    stop_file = attempt_dir / "server.stop"
    app = create_scripted_test_app(Settings())
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning")
    )

    def watch_shutdown() -> None:
        deadline = time.monotonic() + 1800
        while not stop_file.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        server.should_exit = True

    threading.Thread(target=watch_shutdown, daemon=True, name="scripted-harness-shutdown").start()
    server.run()


if __name__ == "__main__":
    main()
