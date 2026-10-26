"""Fetch the user's chosen third-party HK/SGP/SDY results table.
This is not an official source. Fail closed if expected table headers/data change.
"""
import datetime as dt
import html
import json
import pathlib
import re
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "hk4d.json"
SOURCE = "https://togel-hongkong.org/"

def clean(raw):
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()

def fetch():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "Mozilla/5.0 (compatible; HK4D-history-monitor/1.0)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise ValueError("HTTP response not OK")
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Response too large")
        return raw.decode("utf-8", "replace")

def parse(page, today):
    tables = re.findall(r"<table\b[^>]*>(.*?)</table>", page, re.I | re.S)
    rows_by_date = {}
    weekdays = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", "SABTU", "MINGGU"]
    for table in tables:
        rows = []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, re.I | re.S):
            cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.I | re.S)
            rows.append([clean(c) for c in cells])
        header_index = None
        indices = {}
        for i, cells in enumerate(rows):
            headers = [re.sub(r"[^A-Z]", "", c.upper()) for c in cells]
            if all(key in headers for key in ("TANGGAL", "HK", "SGP", "SDY")):
                header_index = i
                indices = {key: headers.index(key) for key in ("TANGGAL", "HK", "SGP", "SDY")}
                if "HARI" in headers:
                    indices["HARI"] = headers.index("HARI")
                break
        if header_index is None:
            continue
        for cells in rows[header_index + 1:]:
            try:
                raw_date = cells[indices["TANGGAL"]]
                match = re.search(r"(?<!\d)(\d{2})[-/](\d{2})[-/](\d{4})(?!\d)", raw_date)
                if not match:
                    continue
                day, month, year = map(int, match.groups())
                date_obj = dt.date(year, month, day)
                if date_obj > today or date_obj < today - dt.timedelta(days=1100):
                    continue
                def result(name):
                    val = cells[indices[name]].strip()
                    if val == "-" or val == "—":
                        return "-"
                    return val if re.fullmatch(r"\d{4}", val) else None
                hk, sgp, sdy = result("HK"), result("SGP"), result("SDY")
                if None in (hk, sgp, sdy):
                    continue
                day_name = weekdays[date_obj.weekday()]
                if "HARI" in indices:
                    supplied_day = re.sub(r"[^A-Z]", "", cells[indices["HARI"]].upper())
                    if supplied_day and supplied_day[:3] not in day_name and day_name[:3] not in supplied_day:
                        continue
                item = {"date": date_obj.isoformat(), "day": day_name, "hk": hk, "sgp": sgp, "sdy": sdy, "source": SOURCE}
                if item["date"] in rows_by_date and rows_by_date[item["date"]] != item:
                    raise ValueError("Conflicting duplicate date in source")
                rows_by_date[item["date"]] = item
            except (IndexError, ValueError):
                continue
    if not rows_by_date:
        raise ValueError("Could not find a TANGGAL/HARI/HK/SGP/SDY table with valid rows; source format may have changed")
    return sorted(rows_by_date.values(), key=lambda x: x["date"], reverse=True)

def main():
    now = dt.datetime.now(ZoneInfo("Asia/Jakarta"))
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    errors = {}
    try:
        fresh = parse(fetch(), now.date())
        # Replace records for dates returned by the chosen source; retain older history.
        history = {item.get("date"): item for item in previous.get("results", []) if item.get("date")}
        for item in fresh:
            history[item["date"]] = item
        results = sorted(history.values(), key=lambda x: x["date"], reverse=True)[:1100]
        status = "source-table-parsed"
    except Exception as exc:
        errors[SOURCE] = str(exc)[:240]
        results = previous.get("results", [])
        status = "source-error-previous-data-retained"
        if not results:
            results = []
    payload = {
        "updated_at": now.isoformat(),
        "source": SOURCE,
        "source_type": "third-party website; not verified as an official lottery source",
        "status": status,
        "errors": errors,
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Source:", SOURCE, "| status:", status, "| records:", len(results), "| errors:", errors)
    if errors:
        raise SystemExit("Source update failed; prior data retained, see error above")

if __name__ == "__main__":
    main()
