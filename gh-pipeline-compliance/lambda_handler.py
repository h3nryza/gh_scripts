"""
lambda_handler.py - AWS Lambda entry point for gh-pipeline-compliance
Written by h3nryza

Expects an event payload with the same keys as the CLI flags.

Example event:
{
    "org": "my-org",
    "workflow": "my-org/reusable-workflows/.github/workflows/ci.yml@main",
    "auth": "pat",
    "s3_bucket": "my-compliance-bucket",
    "s3_prefix": "pipeline-compliance/",
    "format": "csv",
    "verbose": false
}

Environment variables (alternative to event payload):
    GITHUB_TOKEN     - PAT token
    GH_APP_ID        - GitHub App ID
    GH_APP_KEY_FILE  - Path to App private key (mounted in Lambda layer or /tmp)
    S3_BUCKET        - Default S3 bucket
    S3_PREFIX        - Default S3 key prefix
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from typing import Any

# Allow Lambda to find the main module when bundled flat
sys.path.insert(0, os.path.dirname(__file__))

from gh_pipeline_compliance import (
    __version__,
    calculate_summary,
    default_output_path,
    generate_report,
    load_required_workflows,
    run_scan,
    upload_to_s3,
)


def _event_to_namespace(event: dict) -> argparse.Namespace:
    """
    Map an event dict (or environment variables) to an argparse.Namespace
    compatible with the main module's run_scan() function.
    """
    def _get(key: str, default: Any = None) -> Any:
        return event.get(key, os.environ.get(key.upper(), default))

    return argparse.Namespace(
        enterprise=_get("enterprise"),
        org=_get("org"),
        user=_get("user"),
        workflow=_get("workflow"),
        workflows_file=_get("workflows_file"),
        pattern=_get("pattern"),
        search=_get("search"),
        auth=_get("auth", "pat"),
        token=_get("token") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        app_id=_get("app_id") or os.environ.get("GH_APP_ID"),
        app_key=_get("app_key") or os.environ.get("GH_APP_KEY_FILE"),
        output=None,  # Lambda always writes to /tmp then uploads
        format=_get("format", "csv"),
        s3_bucket=_get("s3_bucket") or os.environ.get("S3_BUCKET"),
        s3_prefix=_get("s3_prefix", "pipeline-compliance/") or os.environ.get("S3_PREFIX", "pipeline-compliance/"),
        summary=bool(_get("summary", False)),
        mode="lambda",
        verbose=bool(_get("verbose", False)),
        interactive=False,
    )


def handler(event: dict, context: Any) -> dict:
    """
    Lambda handler entry point.

    Returns a dict with:
        statusCode: 200 | 500
        body: JSON string with summary and output location
    """
    try:
        args = _event_to_namespace(event)

        fmt = args.format
        filename = default_output_path(fmt)
        tmp_path = os.path.join(tempfile.gettempdir(), filename)

        # Run the compliance scan
        results = run_scan(args)

        # Write report to /tmp
        generate_report(results, tmp_path, fmt=fmt)

        # Upload to S3
        s3_bucket = args.s3_bucket
        if not s3_bucket:
            raise ValueError(
                "s3_bucket is required in Lambda mode. "
                "Set 's3_bucket' in the event payload or S3_BUCKET env var."
            )

        s3_prefix = args.s3_prefix or "pipeline-compliance/"
        s3_key = f"{s3_prefix.rstrip('/')}/{filename}"
        s3_uri = upload_to_s3(tmp_path, s3_bucket, s3_key)

        summary = calculate_summary(results)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "version": __version__,
                    "output": s3_uri,
                    "summary": summary,
                },
                default=str,
            ),
        }

    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        print(f"[lambda][error] {exc}\n{tb}", file=sys.stderr)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": str(exc),
                    "traceback": tb,
                }
            ),
        }
