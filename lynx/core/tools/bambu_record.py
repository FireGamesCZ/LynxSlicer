"""Record raw Bambu LAN reports as JSON lines, to turn into test fixtures later.

  BAMBU_ACCESS_CODE=... uv run --with paho-mqtt python3 lynx/core/tools/bambu_record.py \
      --host IP --serial SN --out file.jsonl

The access code comes from the environment or a prompt, never argv. The serial number
is replaced by SERIAL in the output; other identifiers in a report are not scrubbed,
so look at the file before sharing it. Read-only: only sends pushall.
"""
import argparse
import getpass
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lynx_core import bambu  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    code = os.environ.get("BAMBU_ACCESS_CODE") or getpass.getpass("LAN access code: ")

    def on_report(message):
        line = json.dumps({"t": time.time(), "report": message})
        with open(args.out, "a") as f:
            f.write(line.replace(args.serial, "SERIAL") + "\n")

    pin = bambu.fetch_cert(args.host)  # trust on first use, for this session only
    bambu.run(args.host, args.serial, code, on_report, pin)


if __name__ == "__main__":
    main()
