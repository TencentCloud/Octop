#!/usr/bin/env python3
"""toolkit.py — Unified Huangli toolkit.

Canonical usage (recommended from any project/root directory):
  python3 skills/zhongguo-nongli-huangli-jixiong/toolkit.py by-date YYYY-MM-DD
  python3 skills/zhongguo-nongli-huangli-jixiong/toolkit.py batch START_DATE END_DATE [--filter ACTIVITY]
  python3 skills/zhongguo-nongli-huangli-jixiong/toolkit.py search KEYWORD [--year YYYY | --start YYYY-MM-DD --end YYYY-MM-DD]

Short usage (only when current directory is this installed skill folder):
  python3 toolkit.py by-date YYYY-MM-DD
  python3 toolkit.py batch START_DATE END_DATE [--filter ACTIVITY]
  python3 toolkit.py search KEYWORD [--year YYYY | --start YYYY-MM-DD --end YYYY-MM-DD]
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE_DEFAULT = "https://api.nongli.skill.4glz.com"

GANZHI_STEMS = set("甲乙丙丁戊己庚辛壬癸")
GANZHI_BRANCHES = set("子丑寅卯辰巳午未申酉戌亥")
CONSTELLATIONS = {
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座",
}
LUNAR_DAYS = {
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "二十一", "二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八", "二十九", "三十",
}


def env():
    base = os.environ.get("HUANGLI_BASE", BASE_DEFAULT).rstrip("/")
    token = os.environ.get("HUANGLI_TOKEN", "")
    if not token:
        raise SystemExit(f"Error: HUANGLI_TOKEN is not set. Get token at: https://nongli.skill.4glz.com/dashboard")
    return base, token


def http_json(url: str, token: str, method="GET", payload=None):
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def make_dates(start: date, end: date):
    out = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def cmd_by_date(args):
    base, token = env()
    url = f"{base}/api/lunar/date/{args.date}"
    print(json.dumps(http_json(url, token), ensure_ascii=False, indent=2))


def cmd_batch(args):
    base, token = env()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        raise SystemExit("Error: start date is after end date")
    dates = make_dates(start, end)

    results, requested, missing, quota = [], [], [], None
    for part in chunked(dates, 100):
        payload = http_json(f"{base}/api/lunar/batch", token, method="POST", payload={"dates": part})
        results.extend(payload.get("results", []))
        requested.extend(payload.get("requested_dates", part))
        missing.extend(payload.get("missing_dates", []))
        quota = payload.get("_quota", quota)

    if args.filter:
        results = [r for r in results if args.filter in r.get("suitable_activities", [])]

    out = {
        "count": len(results),
        "requested_dates": requested,
        "missing_dates": missing,
        "data": results,
    }
    if quota is not None:
        out["_quota"] = quota
    print(json.dumps(out, ensure_ascii=False, indent=2))


def classify_keyword(kw):
    if kw in CONSTELLATIONS:
        return "constellation", kw
    if kw in LUNAR_DAYS:
        return "lunar_day_cn", kw
    if len(kw) == 3 and kw[0] in GANZHI_STEMS and kw[1] in GANZHI_BRANCHES and kw[2] == "日":
        return "ganzhi_day", kw
    return "suitable_activities", kw


def cmd_search(args):
    base, token = env()

    if args.year:
        start = date(int(args.year), 1, 1)
        end = date(int(args.year), 12, 31)
    elif args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        y = date.today().year
        start, end = date(y, 1, 1), date(y, 12, 31)

    start = max(start, date(2026, 1, 1))
    end = min(end, date(2035, 12, 31))
    if start > end:
        raise SystemExit("Error: invalid range")

    dates = make_dates(start, end)
    field, value = classify_keyword(args.keyword)

    results = []
    for part in chunked(dates, 100):
        payload = http_json(f"{base}/api/lunar/batch", token, method="POST", payload={"dates": part})
        for item in payload.get("results", []):
            v = item.get(field)
            ok = (value in v) if isinstance(v, list) else (v == value)
            if ok:
                results.append(item)

    print(json.dumps({
        "keyword": args.keyword,
        "field": field,
        "count": len(results),
        "data": results,
    }, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description="Unified Huangli toolkit")
    sp = p.add_subparsers(dest="cmd", required=True)

    p1 = sp.add_parser("by-date")
    p1.add_argument("date")
    p1.set_defaults(func=cmd_by_date)

    p2 = sp.add_parser("batch")
    p2.add_argument("start")
    p2.add_argument("end")
    p2.add_argument("--filter")
    p2.set_defaults(func=cmd_batch)

    p3 = sp.add_parser("search")
    p3.add_argument("keyword")
    p3.add_argument("--year")
    p3.add_argument("--start")
    p3.add_argument("--end")
    p3.set_defaults(func=cmd_search)

    args = p.parse_args()
    try:
        args.func(args)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            raise SystemExit("Error: Unauthorized (check HUANGLI_TOKEN)")
        if e.code == 429:
            raise SystemExit("Error: Quota exceeded (429). Reset in dashboard: https://nongli.skill.4glz.com/dashboard")
        raise SystemExit(f"Error: HTTP {e.code}\n{body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Error: Network failure: {e.reason}")


if __name__ == "__main__":
    main()
