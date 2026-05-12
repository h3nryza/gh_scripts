"""
lambda_handler.py - AWS Lambda entry point for gh-version-resolver
Written by h3nryza

Expected event payload:
{
  "mode": "hash-to-version",     # hash-to-version | version-to-hash | scan-file |
                                 #   scan-dir | import
  "hash": "abc123f",             # commit hash (mode: hash-to-version)
  "version": "v4.1.0",           # version tag (mode: version-to-hash)
  "repo": "actions/checkout",    # owner/repo (for single-ref modes)
  "scan_file": "/tmp/ci.yml",    # file path (mode: scan-file)  [mounted EFS or /tmp]
  "scan_dir": "/tmp/terraform/", # directory (mode: scan-dir)
  "import_items": [              # inline items (mode: import)
    {"repository": "actions/checkout", "hash": "abc123f", "type": "github-action"}
  ],
  "type": "github-action",       # ecosystem type (default: general)
  "check_currency": true,        # whether to check version currency
  "current_version": "",         # optional explicit latest version
  "auth_method": "app",          # gh|pat|app (default: app for Lambda)
  "app_id": "12345",
  "app_secret_name": "gh-app-key",  # AWS Secrets Manager secret name
  "pat_token": "",               # used when auth_method == "pat"
  "format": "csv",               # csv|json (default: csv)
  "s3_bucket": "my-bucket",
  "s3_prefix": "github-audit/"
}

The handler:
1. Resolves credentials (App key from Secrets Manager, or PAT from event)
2. Runs hash/version resolution
3. Writes results to /tmp/
4. Uploads to S3
5. Returns a summary dict
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from gh_version_resolver import (
    export_results,
    load_import_file,
    process_bulk_items,
    run_resolver,
    setup_logging,
    upload_to_s3,
    SCRIPT_NAME,
    VERSION,
    AUTHOR,
)

log = logging.getLogger(SCRIPT_NAME)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler for gh-version-resolver.

    Reads configuration from the event payload, runs resolution, writes results
    to S3, and returns a JSON-serialisable summary.
    """
    setup_logging(verbose=event.get("verbose", False))
    log.info("%s v%s — Lambda mode — written by %s", SCRIPT_NAME, VERSION, AUTHOR)

    fmt = event.get("format", os.environ.get("GH_FORMAT", "csv"))
    resolve_mode = event.get("mode", "hash-to-version")

    config: dict[str, Any] = {
        "auth": event.get("auth_method", os.environ.get("GH_AUTH_METHOD", "app")),
        "token": event.get("pat_token", os.environ.get("GH_PAT_TOKEN", "")),
        "app_id": event.get("app_id", os.environ.get("GH_APP_ID", "")),
        "app_key": None,  # no filesystem key in Lambda — use Secrets Manager
        "app_secret_name": event.get(
            "app_secret_name", os.environ.get("GH_APP_SECRET_NAME", "")
        ),
        "type": event.get("type", os.environ.get("GH_ECOSYSTEM_TYPE", "general")),
        "check_currency": bool(
            event.get("check_currency", os.environ.get("GH_CHECK_CURRENCY", False))
        ),
        "current_version": event.get(
            "current_version", os.environ.get("GH_CURRENT_VERSION", "")
        ),
        "format": fmt,
        "s3_bucket": event.get("s3_bucket", os.environ.get("GH_S3_BUCKET", "")),
        "s3_prefix": event.get(
            "s3_prefix", os.environ.get("GH_S3_PREFIX", "github-audit/")
        ),
        "mode": "lambda",
    }

    # Map event mode to config keys
    if resolve_mode == "hash-to-version":
        config["hash_to_version"] = event.get("hash", "")
        config["repo"] = event.get("repo", "")
        if not config["hash_to_version"] or not config["repo"]:
            raise ValueError(
                "Event must include 'hash' and 'repo' for mode 'hash-to-version'"
            )

    elif resolve_mode == "version-to-hash":
        config["version_to_hash"] = event.get("version", "")
        config["repo"] = event.get("repo", "")
        if not config["version_to_hash"] or not config["repo"]:
            raise ValueError(
                "Event must include 'version' and 'repo' for mode 'version-to-hash'"
            )

    elif resolve_mode == "scan-file":
        scan_file = event.get("scan_file", "")
        if not scan_file:
            raise ValueError("Event must include 'scan_file' for mode 'scan-file'")
        config["scan_file"] = scan_file

    elif resolve_mode == "scan-dir":
        scan_dir = event.get("scan_dir", "")
        if not scan_dir:
            raise ValueError("Event must include 'scan_dir' for mode 'scan-dir'")
        config["scan_dir"] = scan_dir

    elif resolve_mode == "import":
        # Inline items or S3 import file
        import_items = event.get("import_items")
        if import_items:
            # Write inline items to a temp file so run_resolver can load them
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir="/tmp"
            )
            json.dump(import_items, tmp)
            tmp.close()
            config["import_file"] = tmp.name
        else:
            raise ValueError(
                "Event must include 'import_items' (list) for mode 'import'"
            )
    else:
        raise ValueError(
            f"Unknown mode '{resolve_mode}'. "
            "Valid: hash-to-version, version-to-hash, scan-file, scan-dir, import"
        )

    # Run resolution
    results = run_resolver(config)

    # Write locally to /tmp
    ext = "json" if fmt == "json" else "csv"
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    local_path = Path(f"/tmp/{ts}_version_resolver.{ext}")
    export_results(results, local_path, fmt=fmt)

    # Upload to S3
    s3_uri: str | None = None
    s3_bucket = config.get("s3_bucket")
    if s3_bucket:
        s3_uri = upload_to_s3(local_path, s3_bucket, prefix=config.get("s3_prefix", ""))
    else:
        log.warning("No s3_bucket configured — results not uploaded to S3")

    summary = {
        "statusCode": 200,
        "script": SCRIPT_NAME,
        "version": VERSION,
        "mode": resolve_mode,
        "total_resolved": len(results),
        "output_file": str(local_path),
        "s3_uri": s3_uri,
        "results": results,
    }

    log.info("Lambda complete. %d reference(s) resolved.", len(results))
    return summary


# Allow local invocation for testing:
#   python lambda_handler.py '{"mode":"hash-to-version","hash":"abc123f","repo":"actions/checkout"}'
if __name__ == "__main__":
    import sys

    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(handler(payload, None), indent=2, default=str))
