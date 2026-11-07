"""Search deployed logs for seeded personal data (#35). Exit code 1 means a leak was found.

    python scripts/check_log_leaks.py --environment staging --hours 2

Before running, process a synthetic document that contains the CANARIES below, for example
samples/S01_invoice.pdf with its contact lines. Every Meridian log group is searched for each canary
with CloudWatch Logs Insights. Needs AWS credentials that can run Logs Insights queries.
"""
from __future__ import annotations

import argparse
import sys
import time

# Values printed on the synthetic samples. None may ever appear in a log line or trace.
CANARIES = [
    "Priya Raman", "priya.raman@kestrel-exports.example", "98450 12345",
    "Arjun Nair", "arjun.nair@bluefin.example", "99001 23456",
    "Anil Kapoor", "93222 41187",
]


def query(client, groups: list[str], text: str, start: int, end: int) -> int:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    started = client.start_query(logGroupNames=groups, startTime=start, endTime=end,
                                 queryString=f"fields @timestamp | filter @message like '{escaped}' | limit 5")
    while True:
        result = client.get_query_results(queryId=started["queryId"])
        if result["status"] in ("Complete", "Failed", "Cancelled", "Timeout"):
            if result["status"] != "Complete":
                raise RuntimeError(f"query {result['status']}")
            return len(result["results"])
        time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True, choices=["staging", "production"])
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--region", default="ap-south-1")
    args = parser.parse_args()
    import boto3

    logs = boto3.client("logs", region_name=args.region)
    prefix = f"/meridian/{args.environment}/"
    groups = [g["logGroupName"] for page in logs.get_paginator("describe_log_groups").paginate(logGroupNamePrefix=prefix)
              for g in page["logGroups"]]
    if not groups:
        print(f"No log groups under {prefix}")
        return 2
    end = int(time.time())
    start = end - args.hours * 3600
    leaks = {canary: query(logs, groups, canary, start, end) for canary in CANARIES}
    found = {canary: count for canary, count in leaks.items() if count}
    # Print only which canary matched, never the matching lines.
    print("LEAK FOUND: " + ", ".join(found) if found else f"No canaries in {len(groups)} log groups over {args.hours}h")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
