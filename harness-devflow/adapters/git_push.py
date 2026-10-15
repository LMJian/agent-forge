#!/usr/bin/env python3
"""Optional Git remote push adapter. Never force-push or guess the destination."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", required=True)
    args = parser.parse_args()
    request = json.loads(Path(os.environ["HARNESS_REQUEST"]).read_text())
    if request["stage"] != "push" or args.remote.startswith("-"):
        raise ValueError("Expected push stage and an explicit remote name")
    destinations = subprocess.run(["git", "remote", "get-url", "--push", "--all", args.remote],
                                  cwd=request["repository"], check=True, capture_output=True,
                                  text=True, stdin=subprocess.DEVNULL, timeout=15).stdout.splitlines()
    if not destinations:
        raise ValueError("Remote has no push destination")
    subprocess.run(["git", "push", "--set-upstream", args.remote,
                    f"refs/heads/{request['branch']}:refs/heads/{request['branch']}"],
                   cwd=request["repository"], check=True, stdout=sys.stderr, stderr=sys.stderr,
                   stdin=subprocess.DEVNULL, timeout=180)
    ref = f"refs/heads/{request['branch']}"
    # A named remote's fetch URL may differ from its push URLs. Verify every
    # destination that Git actually pushes to, including pushInsteadOf rewrites.
    for destination in destinations:
        observed = subprocess.run(["git", "ls-remote", "--exit-code", "--", destination, ref],
                                  cwd=request["repository"], check=True, capture_output=True,
                                  text=True, stdin=subprocess.DEVNULL, timeout=60)
        if observed.stdout.split() != [request["head"], ref]:
            raise ValueError("Push returned but a push destination's branch does not match the reviewed commit; reconcile before retrying")
    print(json.dumps({"schema_version": 1, "status": "pass", "summary": "Reviewed branch pushed",
                      "remote": args.remote, "head": request["head"], "remote_head": request["head"], "ref": ref}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema_version": 1, "status": "fail", "summary": str(error)}))
        sys.exit(1)
