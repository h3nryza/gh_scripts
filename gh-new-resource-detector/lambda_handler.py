"""
lambda_handler.py - AWS Lambda entry point for gh-new-resource-detector
Written by h3nryza

Expected event payload:
{
  "enterprise":   "my-enterprise",    # or "org"/"user"
  "org":          "",
  "user":         "",
  "auth_method":  "app",              # gh|pat|app
  "app_id":       "12345",
  "app_secret_name": "gh-app-key",    # AWS Secrets Manager secret name for app private key
  "pat_token":    "",                 # used when auth_method == "pat"
  "days":         7,
  "since":        "",                 # ISO date string, overrides days
  "type":         "all",              # repos|orgs|all
  "format":       "csv",              # csv|json
  "s3_bucket":    "my-bucket",
  "s3_prefix":    "github-audit/"
}

The handler:
1. Resolves credentials (App key from Secrets Manager, or PAT from event)
2. Runs detection
3. Writes results to /tmp/
4. Uploads to S3
5. Returns a summary dict
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from gh_new_resource_detector import (
    export_results,
    run_detection,
    upload_to_s3,
    setup_logging,
    SCRIPT_NAME,
    VERSION,
    AUTHOR,
)

log = logging.getLogger(SCRIPT_NAME)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler for gh-new-resource-detector.

    Reads configuration from the event payload, runs detection, writes results
    to S3, and returns a JSON-serialisable summary.
    """
    setup_logging(verbose=event.get("verbose", False))
    log.info("%s v%s — Lambda mode — written by %s", SCRIPT_NAME, VERSION, AUTHOR)

    # Build config dict from event + environment variable overrides
    config: dict[str, Any] = {
        "enterprise": event.get("enterprise", os.environ.get("GH_ENTERPRISE", "")),
        "org": event.get("org", os.environ.get("GH_ORG", "")),
        "user": event.get("user", os.environ.get("GH_USER", "")),
        "auth": event.get("auth_method", os.environ.get("GH_AUTH_METHOD", "app")),
        "token": event.get("pat_token", os.environ.get("GH_PAT_TOKEN", "")),
        "app_id": event.get("app_id", os.environ.get("GH_APP_ID", "")),
        "app_key": None,  # no filesystem key in Lambda — use Secrets Manager
        "app_secret_name": event.get(
            "app_secret_name", os.environ.get("GH_APP_SECRET_NAME", "")
        ),
        "days": int(event.get("days", os.environ.get("GH_DAYS", 7))),
        "since": event.get("since", os.environ.get("GH_SINCE", "")),
        "type": event.get("type", os.environ.get("GH_RESOURCE_TYPE", "all")),
        "format": event.get("format", os.environ.get("GH_FORMAT", "csv")),
        "s3_bucket": event.get("s3_bucket", os.environ.get("GH_S3_BUCKET", "")),
        "s3_prefix": event.get("s3_prefix", os.environ.get("GH_S3_PREFIX", "github-audit/")),
        # Persist org state between invocations using /tmp (Lambda ephemeral storage)
        "state_file": "/tmp/.gh_detector_state.json",
        "mode": "lambda",
    }

    if not any([config["enterprise"], config["org"], config["user"]]):
        raise ValueError(
            "Event must include at least one of: enterprise, org, user"
        )

    # Run detection
    results = run_detection(config)

    # Write locally to /tmp
    fmt = config["format"]
    ext = "json" if fmt == "json" else "csv"
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    local_path = Path(f"/tmp/{ts}_new_resources.{ext}")
    export_results(results, local_path, fmt=fmt)

    # Upload to S3
    s3_uri: str | None = None
    s3_bucket = config.get("s3_bucket")
    if s3_bucket:
        s3_uri = upload_to_s3(local_path, s3_bucket, prefix=config.get("s3_prefix", ""))
    else:
        log.warning("No s3_bucket configured — results not uploaded")

    summary = {
        "statusCode": 200,
        "script": SCRIPT_NAME,
        "version": VERSION,
        "total_new_resources": len(results),
        "output_file": str(local_path),
        "s3_uri": s3_uri,
        "results": results,
    }

    log.info("Lambda complete. %d new resource(s) found.", len(results))
    return summary


# Allow local invocation for testing:
#   python lambda_handler.py '{"enterprise":"my-co","days":7,"s3_bucket":"my-bucket"}'
if __name__ == "__main__":
    import sys

    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(handler(payload, None), indent=2))
