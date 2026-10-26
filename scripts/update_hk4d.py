"""Update HK/SGP/SDY history from public third-party archive tables.
Sources are not official. Preserve existing data if every source fails validation.
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
SOURCES = [
    "https://livehksdy.com/riwayat/index.php/",
    "https://togel-hongkong.org/",
]
MONTHS = {
    "JANUARI": 1, "JANUARY": 1, "FEBRUARI": 2, "FEBRUARY": 2,
    "MARET": 3, "MARCH": 3, "APRIL": 4, "MEI": 5, "MAY": 5,
    "JUNI": 6, "JUNE": 6, "JULI": 7, "JULY": 7, "AGUSTUS": 8,
    "AUGUST": 8, "SEPTEMBER": 9, "OKTOBER": 10, "OCTOBER": 10,
    "NOVEMBER": 11, "DESEMBER": 12, "DECEMBER": 12,
}
WEEKDAYS = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", "SABTU", "MINGGU"]

def clean(raw):
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; HK4D-history-monitor/1.1)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise ValueError("HTTP response not OK")
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Response too large")
        return raw.decode("utf-8", "replace")

def parse_date(raw):
    match = re.search(r"(?<!\d)(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?!\d)", raw)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    match = re.search(r"(?:Senin|Selasa|Rabu|Kamis|Jumat|Sabtu|Minggu)?\s*,?\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw, re.I)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name.upper())
    if not month:
        return None
    try:
        return dt.date(int(year), month, int(day))
    except ValueError:
        return None

def parse(page, today, source):
    tables = re.findall(r"<table\b[^>]*>(.*?)</table>", page, re.I | re.S)
    rows_by_date = {}
    for table in tables:
        rows = []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, re.I | re.S):
            cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.I | re.S)
            rows.append([clean(c) for c in cells])
        indices = {}
        header_index = None
        for i, cells in enumerate(rows):
            headers = [re.sub(r"[^A-Z]", "", c.upper()) for c in cells]
            date_idx = next((j for j, h in enumerate(headers) if h in ("TANGGAL", "HARITANGGAL", "TANGGALHARI")), None)
            found = {key: next((j for j, h in enumerate(headers) if h == key), None) for key in ("HK", "SGP", "SDY")}
            if date_idx is not None and all(v is not None for v in found.values()):
                header_index = i
                indices = {"DATE": date_idx, **found}
                break
        if header_index is None:
            continue
        for cells in rows[header_index + 1:]:
            if max(indices.values()) >= len(cells):
                continue
            date_obj = parse_date(cells[indices["DATE"]])
            if not date_obj or date_obj > today or date_obj < today - dt.timedelta(days=1100):
                continue
            def result(name):
                val = re.sub(r"\s+", "", cells[indices[name]]).strip()
                if val in ("-", "—", "–", ""):
                    return "-"
                return val if re.fullmatch(r"\d{4}", val) else None
            values = {key: result(key) for key in ("HK", "SGP", "SDY")}
            if any(value is None for value in values.values()):
                continue
            item = {
                "date": date_obj.isoformat(),
                "day": WEEKDAYS[date_obj.weekday()],
                **{key.lower(): value for key, value in values.items()},
                "source": source,
            }
            existing = rows_by_date.get(item["date"])
            if existing and any(existing[k] != item[k] for k in ("hk", "sgp", "sdy")):
                raise ValueError("Conflicting duplicate date in source table")
            rows_by_date[item["date"]] = item
    if not rows_by_date:
        raise ValueError("No valid date + HK/SGP/SDY table found; source HTML may have changed or requires JavaScript")
    return sorted(rows_by_date.values(), key=lambda item: item["date"], reverse=True)

def main():
    now = dt.datetime.now(ZoneInfo("Asia/Jakarta"))
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    except Exception:
        previous = {}
    errors = {}
    fresh = None
    selected_source = None
    for source in SOURCES:
        try:
            fresh = parse(fetch(source), now.date(), source)
            selected_source = source
            break
        except Exception as exc:
            errors[source] = str(exc)[:240]
            print("Source failed:", source, "|", errors[source])
    if fresh is None:
        results = previous.get("results", [])
        payload = {
            "updated_at": now.isoformat(),
            "source": previous.get("source", SOURCES[0]),
            "source_type": "third-party website; not verified as an official source",
            "status": "source-error-previous-data-retained",
            "errors": errors,
            "results": results,
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("All sources failed; prior records retained:", len(results))
        return  # Persist failure status while retaining previous validated results
    # Replace only dates returned by the validated source; preserve all other history.
    history = {item.get("date"): item for item in previous.get("results", []) if item.get("date")}
    for item in fresh:
        history[item["date"]] = item
    results = sorted(history.values(), key=lambda item: item["date"], reverse=True)[:1100]
    payload = {
        "updated_at": now.isoformat(),
        "source": selected_source,
        "source_type": "third-party website; not verified as an official source",
        "status": "source-table-parsed",
        "errors": errors,
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Source:", selected_source, "| status: source-table-parsed | fresh records:", len(fresh), "| total records:", len(results), "| fallback errors:", errors)

if __name__ == "__main__":
    main()
