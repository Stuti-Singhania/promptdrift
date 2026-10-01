"""A deliberately synthetic incident through the real OpenAI-compatible adapter."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from promptdrift.engine.baseline import write_baseline
from promptdrift.engine.monitor import monitor_suite
from promptdrift.engine.runner import run_suite
from promptdrift.models import Config
from promptdrift.models.monitor import MonitorReport


def run_demo() -> MonitorReport:
    state = {"output": "Refunds are available within 30 days."}

    class FixtureHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.dumps(
                {
                    "model": "synthetic-support-model",
                    "choices": [{"message": {"content": state["output"]}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 9},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass  # Do not write fixture request logs.

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env_name = "PROMPTDRIFT_SYNTHETIC_DEMO_KEY"
    previous = os.environ.get(env_name)
    os.environ[env_name] = "local-fixture-not-a-credential"
    try:
        with TemporaryDirectory(prefix="promptdrift-demo-") as temporary:
            root = Path(temporary)
            (root / "support.txt").write_text("State the refund policy.", encoding="utf-8")
            config = Config.model_validate(
                {
                    "provider": {
                        "type": "openai",
                        "model": "synthetic-support-model",
                        "api_key_env": env_name,
                        "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    },
                    "tests": [
                        {
                            "id": "refund-policy",
                            "prompt": "support.txt",
                            "assertions": [{"type": "contains", "value": "30 days"}],
                        }
                    ],
                }
            )
            path = root / "promptdrift.yaml"
            baseline = root / config.baseline.path
            write_baseline(baseline, run_suite(config, path))
            state["output"] = "All purchases are final. Refunds are not offered."
            report = monitor_suite(config, path, samples=3)
            report.warnings.append(
                "Synthetic local fixture, not a real model incident or benchmark. Temporary baseline is deleted after the demo."
            )
            return report
    finally:
        if previous is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = previous
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
