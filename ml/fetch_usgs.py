"""Download a USGS continuous water-quality record into one hourly CSV for train_water_model.py.

    python ml/fetch_usgs.py --site 421401121480900 --start 2010-01-01 --end 2025-12-31

Data: U.S. Geological Survey, Water Data API (api.waterdata.usgs.gov, "continuous" collection);
public domain. Calibrated monitors, approved records. Writes data/usgs/<site>.csv with columns
time (UTC, hour), do (mg/L), temp (degC), ph, turbidity (FNU; empty where not measured).
"""
import argparse
import csv
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

API = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"
PARAMS = {"00300": "do", "00010": "temp", "00400": "ph", "63680": "turbidity"}
OUT = Path(__file__).resolve().parents[1] / "data" / "usgs"


def fetch(site: str, code: str, start: str, end: str) -> list[tuple[str, float]]:
    """(time, value) for one parameter, following the API's next links. Missing parameter -> []."""
    out = []
    for year in range(int(start[:4]), int(end[:4]) + 1):  # the API allows at most 1100 days per query
        lo, hi = max(start, f"{year}-01-01"), min(end, f"{year}-12-31")
        query = urllib.parse.urlencode({"monitoring_location_id": f"USGS-{site}", "parameter_code": code,
                                        "time": f"{lo}T00:00:00Z/{hi}T23:59:59Z", "limit": 10000, "f": "json"})
        url = f"{API}?{query}"
        while url:
            with urllib.request.urlopen(url, timeout=120) as r:
                page = json.load(r)
            for f in page.get("features", []):
                p = f["properties"]
                try:
                    out.append((p["time"], float(p["value"])))
                except (TypeError, ValueError):
                    continue  # blank or flagged value
            url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
    return out


def hourly(points: list[tuple[str, float]]) -> dict[str, float]:
    """Mean per UTC hour (monitors log every 15-60 min)."""
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for t, v in points:
        s = sums[t[:13]]  # 'YYYY-MM-DDTHH'
        s[0] += v
        s[1] += 1
    return {h: s / n for h, (s, n) in sums.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True, help="USGS site number, e.g. 421401121480900")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2025-12-31")
    args = ap.parse_args()

    series = {}
    for code, name in PARAMS.items():
        series[name] = hourly(fetch(args.site, code, args.start, args.end))
        print(f"{name:10s} {len(series[name]):7d} hours")
    hours = sorted(set(series["do"]) & set(series["temp"]))  # oxygen and temperature are required
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.site}.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "do", "temp", "ph", "turbidity"])
        for h in hours:
            w.writerow([f"{h}:00:00Z"] + [("" if (v := series[k].get(h)) is None else round(v, 3)) for k in ("do", "temp", "ph", "turbidity")])
    by_year: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for h in hours:
        by_year[h[:4]][0] += 1
        by_year[h[:4]][1] += series["do"][h] < 5
    print(f"saved {path}: {len(hours)} hours with oxygen and temperature")
    for y, (n, low) in sorted(by_year.items()):
        print(f"  {y}: {n:5d} hours, {low:5d} below 5 mg/L")


if __name__ == "__main__":
    main()
