"""Run the isolated scripted FastAPI app with portable test-harness shutdown."""
from pathlib import Path
import os
import threading
import time

import uvicorn

from shiftguard.api.test_harness import create_scripted_test_app
from shiftguard.settings import Settings

stop_file = Path(os.environ["SG_GATE5_ATTEMPT_DIR"]) / "server.stop"
server = uvicorn.Server(uvicorn.Config(create_scripted_test_app(Settings()), host="127.0.0.1", port=8765, log_level="warning"))


def watch_shutdown() -> None:
    deadline = time.monotonic() + 1800
    while not stop_file.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    server.should_exit = True


threading.Thread(target=watch_shutdown, daemon=True).start()
server.run()
