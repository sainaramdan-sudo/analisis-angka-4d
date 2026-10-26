"""Monitor two third-party HK 4D archives. Never represent these as HKJC results."""
import datetime as dt
import html
import json
import pathlib
import re
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "hk4d.json"
SOURCES = {
    "Nagasaon archive": "https://nagasaon4d7.net/result-togel-hk/",
    "Raja Hasil archive": "https://w2.rajahasil4d.com/data.php/?slug=hk",
}
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; research-history-monitor/1.0)"})
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise ValueError("HTTP response not OK")
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Response too large")
        return raw.decode("utf-8", "replace")

def parse(page):
    rows = {}
    for tr in re.findall(r"<tr\\b[^>]*>(.*?)</tr>", page, re.I | re.S):
        cells = re.findall(r"<t[dh]\\b[^>]*>(.*?)</t[dh]>", tr, re.I | re.S)
        plain = [html.unescape(re.sub(r"<[^>]+>", " ", x)).strip() for x in cells]
        text = " ".join(plain)
        match = re.search(r"(?<!\\d)(\\d{2})[-/](\\d{2})[-/](\\d{4})(?!\\d)", text)
        if not match:
            continue
        day, month, year = map(int, match.groups())
        try:
            date = dt.date(year, month, day).isoformat()
        except ValueError:
            continue
        numbers = [x for x in plain if re.fullmatch(r"\\d{4}", x)]
        if len(numbers) != 1:
            continue
        if date in rows and rows[date] != numbers[0]:
            raise ValueError("Conflicting rows within one source")
        rows[date] = numbers[0]
    if not rows:
        raise ValueError("No dated 4D rows detected; page format may have changed")
    return rows

def main():
    now = dt.datetime.now(ZoneInfo("Asia/Jakarta"))
    observations, errors = {}, {}
    for name, url in SOURCES.items():
        try:
            observations[name] = parse(fetch(url))
        except Exception as exc:
            errors[name] = str(exc)[:180]
    previous = {"results": []}
    if OUT.exists():
        previous = json.loads(OUT.read_text(encoding="utf-8"))
    stored = {r["date"]: r for r in previous.get("results", []) if re.fullmatch(r"\\d{4}", r.get("number", ""))}
    dates = set().union(*(set(v) for v in observations.values())) if observations else set()
    conflicts = []
    for date in sorted(dates):
        values = {name: rows[date] for name, rows in observations.items() if date in rows}
        if date > now.date().isoformat():
            continue
        if len(values) < len(SOURCES):
            continue
        if len(set(values.values())) != 1:
            conflicts.append({"date": date, "observations": values})
            continue
        number = next(iter(values.values()))
        if date in stored and stored[date]["number"] != number:
            conflicts.append({"date": date, "observations": values, "previously_saved": stored[date]["number"]})
            continue
        stored[date] = {"date": date, "number": number, "sources": list(SOURCES.values()), "status": "two-third-party-sources-agree"}
    payload = {
        "updated_at": now.isoformat(),
        "source_type": "third-party archives; not HKJC official",
        "status": "review-required" if errors or conflicts else "sources-agree",
        "errors": errors,
        "conflicts": conflicts,
        "results": sorted(stored.values(), key=lambda x: x["date"], reverse=True)[:1000],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Agreed records:", len(stored), "errors:", errors, "conflicts:", len(conflicts))

if __name__ == "__main__":
    main()
