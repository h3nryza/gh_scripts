"""
Lambda handler for gh-best-practices-audit.
Written by h3nryza

Deployed as an AWS Lambda function for scheduled or event-driven audits.
Supports S3 output and SNS notifications.

Environment Variables:
  GITHUB_TOKEN     - GitHub PAT for authentication
  S3_BUCKET        - S3 bucket for report output
  S3_PREFIX        - S3 key prefix (optional)
  BENCHMARKS       - Comma-separated benchmarks (default: all)
  SEVERITY         - Minimum severity level (default: low)
  OUTPUT_FORMAT    - Output format: csv|json|html (default: json)
  SNS_TOPIC_ARN    - SNS topic for notifications (optional)
"""

import json
import logging
import os
import tempfile

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """
    Lambda entry point.

    Args:
        event: Lambda event payload. Expected keys:
            - enterprise: str (optional)
            - org: str (optional)
            - repo: str (optional)
            - benchmarks: str (optional, default from env)
            - severity: str (optional, default from env)
            - format: str (optional, default from env)
        context: Lambda context object.

    Returns:
        Dict with audit results summary.
    """
    from gh_best_practices_audit import main as run_audit

    # Build parameters from event + environment
    params = {
        "enterprise": event.get("enterprise", ""),
        "org": event.get("org", ""),
        "repo": event.get("repo", ""),
        "benchmarks": event.get("benchmarks", os.environ.get("BENCHMARKS", "all")),
        "severity": event.get("severity", os.environ.get("SEVERITY", "low")),
        "category": event.get("category", ""),
        "auth": "pat",
        "token": event.get("token", os.environ.get("GITHUB_TOKEN", "")),
        "format": event.get("format", os.environ.get("OUTPUT_FORMAT", "json")),
        "s3_bucket": event.get("s3_bucket", os.environ.get("S3_BUCKET", "")),
        "s3_prefix": event.get("s3_prefix", os.environ.get("S3_PREFIX", "")),
        "custom_rules": event.get("custom_rules", ""),
        "verbose": event.get("verbose", False),
        "summary": event.get("summary", False),
    }

    # Validate that at least one target is specified
    if not any([params["enterprise"], params["org"], params["repo"]]):
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "At least one target (enterprise, org, or repo) is required."
            }),
        }

    # Validate token
    if not params["token"]:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "GITHUB_TOKEN environment variable or token parameter is required."
            }),
        }

    # Set output to temp directory for Lambda
    tmp_dir = tempfile.mkdtemp()
    target = params["enterprise"] or params["org"] or params["repo"]
    params["output"] = os.path.join(
        tmp_dir,
        f"audit_{target.replace('/', '_')}.{params['format']}",
    )

    logger.info("Starting audit for target: %s", target)
    logger.info("Benchmarks: %s, Severity: %s", params["benchmarks"], params["severity"])

    try:
        result = run_audit(event=params)

        # Send SNS notification if configured
        sns_topic = os.environ.get("SNS_TOPIC_ARN", "")
        if sns_topic and result.get("failed", 0) > 0:
            _send_sns_notification(sns_topic, target, result)

        return {
            "statusCode": 200,
            "body": json.dumps(result, default=str),
        }
    except Exception as exc:
        logger.error("Audit failed: %s", str(exc), exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }


def _send_sns_notification(topic_arn: str, target: str, result: dict) -> None:
    """Send an SNS notification with audit summary."""
    try:
        import boto3
        sns = boto3.client("sns")
        subject = f"GitHub Audit Alert: {result.get('failed', 0)} failures for {target}"
        message = (
            f"GitHub Best Practices Audit Results\n"
            f"{'=' * 40}\n"
            f"Target: {target}\n"
            f"Total Rules: {result.get('total', 0)}\n"
            f"Passed: {result.get('passed', 0)}\n"
            f"Failed: {result.get('failed', 0)}\n"
            f"Skipped: {result.get('skipped', 0)}\n"
        )
        if result.get("s3_url"):
            message += f"\nFull report: {result['s3_url']}\n"

        sns.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],  # SNS subject max 100 chars
            Message=message,
        )
        logger.info("SNS notification sent to %s", topic_arn)
    except Exception as exc:
        logger.warning("Failed to send SNS notification: %s", exc)
