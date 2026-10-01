"""Offline CLI subprocess fixture; intentionally capable of returning unsafe/non-JSON output."""

import json
import os
import sys
from pathlib import Path

Path(os.environ["FAKE_CLI_RECEIVED"]).write_text(
    json.dumps({"arguments": sys.argv[1:], "cwd": str(Path.cwd())}), encoding="utf-8"
)
sys.stdout.write(os.environ.get("FAKE_CLI_STDOUT", ""))
sys.stderr.write(os.environ.get("FAKE_CLI_STDERR", ""))
sys.exit(int(os.environ["FAKE_CLI_STATUS"]))
