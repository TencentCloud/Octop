#!/usr/bin/env python3
"""
Whoop Data Fetcher - Retrieve health data from Whoop API

Usage:
    # Get sleep data (last 7 days by default)
    python3 whoop_data.py sleep [--days N] [--start DATE] [--end DATE]

    # Get recovery data
    python3 whoop_data.py recovery [--days N] [--start DATE] [--end DATE]

    # Get cycles (strain)
    python3 whoop_data.py cycles [--days N] [--start DATE] [--end DATE]

    # Get workouts
    python3 whoop_data.py workouts [--days N] [--start DATE] [--end DATE]

    # Get user profile
    python3 whoop_data.py profile

    # Get body measurements
    python3 whoop_data.py body

    # Get all data summary
    python3 whoop_data.py summary [--days N]

Output: JSON to stdout
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
import urllib.request
import urllib.parse

# Add scripts dir to path for auth import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from whoop_auth import get_valid_token

API_BASE = "https://api.prod.whoop.com/developer/v2"
USER_AGENT = "Clawdbot/1.0 (Whoop Integration)"


def api_get(endpoint, params=None):
    """Make authenticated GET request to Whoop API."""
    token = get_valid_token()
    url = f"{API_BASE}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })

    max_retries = 3
    backoff_seconds = 1
    transient_codes = {429, 500, 502, 503, 504}
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            if e.code in transient_codes and attempt < max_retries:
                time.sleep(backoff_seconds)
                backoff_seconds *= 2
                continue
            print(f"API Error {e.code}: {error_body}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(backoff_seconds)
                backoff_seconds *= 2
                continue
            print(f"API Error: {e}", file=sys.stderr)
            sys.exit(1)


def get_date_range(days=None, start=None, end=None):
    """Calculate start/end dates."""
    now = datetime.now(timezone.utc)
    if start:
        start_dt = _parse_iso_datetime(start)
    elif days:
        start_dt = now - timedelta(days=days)
    else:
        start_dt = now - timedelta(days=7)

    if end:
        end_dt = _parse_iso_datetime(end)
    else:
        end_dt = now

    return start_dt.isoformat(), end_dt.isoformat()


def _parse_iso_datetime(value):
    """Parse ISO date or datetime; date-only gets T00:00:00Z."""
    if len(value) == 10 and "T" not in value:
        value = f"{value}T00:00:00Z"
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def fetch_paginated(endpoint, params, key="records"):
    """Fetch all pages of a paginated endpoint."""
    all_records = []
    max_pages = 50
    pages = 0
    while True:
        pages += 1
        if pages > max_pages:
            print(f"Pagination cap reached ({max_pages} pages) for {endpoint}", file=sys.stderr)
            break
        data = api_get(endpoint, params)
        records = data.get(key, [])
        all_records.extend(records)
        next_token = data.get("next_token")
        if not next_token or not records:
            break
        params["nextToken"] = next_token
    return all_records


def get_sleep(days=None, start=None, end=None):
    """Get sleep data."""
    start_dt, end_dt = get_date_range(days, start, end)
    params = {"start": start_dt, "end": end_dt, "limit": 25}
    records = fetch_paginated("/activity/sleep", params)
    return {"type": "sleep", "count": len(records), "records": records}


def get_recovery(days=None, start=None, end=None):
    """Get recovery data."""
    start_dt, end_dt = get_date_range(days, start, end)
    params = {"start": start_dt, "end": end_dt, "limit": 25}
    records = fetch_paginated("/recovery", params)
    return {"type": "recovery", "count": len(records), "records": records}


def get_cycles(days=None, start=None, end=None):
    """Get cycle (strain) data."""
    start_dt, end_dt = get_date_range(days, start, end)
    params = {"start": start_dt, "end": end_dt, "limit": 25}
    records = fetch_paginated("/cycle", params)
    return {"type": "cycles", "count": len(records), "records": records}


def get_workouts(days=None, start=None, end=None):
    """Get workout data."""
    start_dt, end_dt = get_date_range(days, start, end)
    params = {"start": start_dt, "end": end_dt, "limit": 25}
    records = fetch_paginated("/activity/workout", params)
    return {"type": "workouts", "count": len(records), "records": records}


def get_profile():
    """Get user profile."""
    return api_get("/user/profile/basic")


def get_body():
    """Get body measurements."""
    return api_get("/user/measurement/body")


def get_summary(days=7):
    """Get a combined summary of all data."""
    sleep = get_sleep(days=days)
    recovery = get_recovery(days=days)
    cycles = get_cycles(days=days)
    workouts = get_workouts(days=days)

    # Calculate averages
    summary = {
        "period_days": days,
        "sleep": {
            "count": sleep["count"],
            "avg_performance": None,
            "avg_hours": None,
            "records": sleep["records"],
        },
        "recovery": {
            "count": recovery["count"],
            "avg_score": None,
            "avg_hrv": None,
            "avg_rhr": None,
            "records": recovery["records"],
        },
        "cycles": {
            "count": cycles["count"],
            "avg_strain": None,
            "records": cycles["records"],
        },
        "workouts": {
            "count": workouts["count"],
            "records": workouts["records"],
        },
    }

    # Sleep averages
    sleep_perfs = [r["score"]["sleep_performance_percentage"]
                   for r in sleep["records"]
                   if r.get("score") and r["score"].get("sleep_performance_percentage")]
    sleep_durations = []
    for r in sleep["records"]:
        if r.get("score") and r["score"].get("stage_summary"):
            total = r["score"]["stage_summary"].get("total_in_bed_time_milli", 0)
            awake = r["score"]["stage_summary"].get("total_awake_time_milli", 0)
            sleep_durations.append((total - awake) / 3600000)  # hours

    if sleep_perfs:
        summary["sleep"]["avg_performance"] = round(sum(sleep_perfs) / len(sleep_perfs), 1)
    if sleep_durations:
        summary["sleep"]["avg_hours"] = round(sum(sleep_durations) / len(sleep_durations), 1)

    # Recovery averages
    rec_scores = [r["score"]["recovery_score"]
                  for r in recovery["records"]
                  if r.get("score") and r["score"].get("recovery_score")]
    rec_hrvs = [r["score"]["hrv_rmssd_milli"]
                for r in recovery["records"]
                if r.get("score") and r["score"].get("hrv_rmssd_milli")]
    rec_rhrs = [r["score"]["resting_heart_rate"]
                for r in recovery["records"]
                if r.get("score") and r["score"].get("resting_heart_rate")]

    if rec_scores:
        summary["recovery"]["avg_score"] = round(sum(rec_scores) / len(rec_scores), 1)
    if rec_hrvs:
        summary["recovery"]["avg_hrv"] = round(sum(rec_hrvs) / len(rec_hrvs), 1)
    if rec_rhrs:
        summary["recovery"]["avg_rhr"] = round(sum(rec_rhrs) / len(rec_rhrs), 1)

    # Strain averages
    strains = [r["score"]["strain"]
               for r in cycles["records"]
               if r.get("score") and r["score"].get("strain")]
    if strains:
        summary["cycles"]["avg_strain"] = round(sum(strains) / len(strains), 1)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Fetch Whoop health data")
    sub = parser.add_subparsers(dest="command")

    for cmd in ["sleep", "recovery", "cycles", "workouts"]:
        p = sub.add_parser(cmd)
        p.add_argument("--days", type=int, default=7)
        p.add_argument("--start", help="ISO date (e.g., 2026-01-01)")
        p.add_argument("--end", help="ISO date")

    sub.add_parser("profile")
    sub.add_parser("body")

    summary_p = sub.add_parser("summary")
    summary_p.add_argument("--days", type=int, default=7)

    args = parser.parse_args()

    if args.command == "sleep":
        result = get_sleep(args.days, args.start, args.end)
    elif args.command == "recovery":
        result = get_recovery(args.days, args.start, args.end)
    elif args.command == "cycles":
        result = get_cycles(args.days, args.start, args.end)
    elif args.command == "workouts":
        result = get_workouts(args.days, args.start, args.end)
    elif args.command == "profile":
        result = get_profile()
    elif args.command == "body":
        result = get_body()
    elif args.command == "summary":
        result = get_summary(args.days)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
