"""Record trimmed, real samples of every source into fixtures/ for offline tests.

Runs the fetches on Modal (the production runtime) and writes files locally:

    modal run finn/ops/record_fixtures.py

Samples are trimmed to keep the repo small; parsers are tested against these files.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import modal

app = modal.App("finn-record-fixtures")
image = modal.Image.debian_slim(python_version="3.12").pip_install("httpx[http2]>=0.27")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
KEEP = {"TATAPOWER", "HDFCBANK", "HCLTECH", "ETERNAL", "SUNPHARMA", "LT", "INFY", "SBIN"}


def _fixtures_dir() -> Path:
    # Resolved at call time: inside Modal's container this file sits at /root.
    return Path(__file__).resolve().parents[4] / "fixtures"


def _last_weekday_before(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _trim_csv(text: str, symbol_col: int, extra: int = 10) -> str:
    lines = text.splitlines()
    head, rows = lines[0], lines[1:]
    kept = [r for r in rows if r.split(",")[symbol_col].strip() in KEEP]
    return "\n".join([head, *kept, *rows[:extra]]) + "\n"


@app.function(image=image, timeout=300)
def fetch() -> dict[str, str]:
    import httpx

    today = date.today()
    day = _last_weekday_before(today)
    api = httpx.Client(
        headers={"User-Agent": UA, "Accept": "application/json,*/*", "Accept-Language": "en-US"},
        http2=True,
        follow_redirects=True,
        timeout=30,
    )
    files = httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=60)
    base = "https://www.nseindia.com/api"
    out: dict[str, str] = {}

    def j(url: str, **params: Any) -> Any:
        r = api.get(url, params=params)
        r.raise_for_status()
        return r.json()

    fmt = "%d-%m-%Y"
    month_ago = (today - timedelta(days=30)).strftime(fmt)
    out["nse/announcements_TATAPOWER_30d.json"] = json.dumps(
        j(
            f"{base}/corporate-announcements",
            index="equities",
            symbol="TATAPOWER",
            from_date=month_ago,
            to_date=today.strftime(fmt),
        ),
        indent=1,
    )
    market = j(
        f"{base}/corporate-announcements",
        index="equities",
        from_date=day.strftime(fmt),
        to_date=day.strftime(fmt),
    )
    out["nse/announcements_market_1d_sample.json"] = json.dumps(market[:60], indent=1)
    out["nse/results_comparison_HCLTECH.json"] = json.dumps(
        j(f"{base}/results-comparision", symbol="HCLTECH"), indent=1
    )
    out["nse/results_comparison_HDFCBANK.json"] = json.dumps(
        j(f"{base}/results-comparision", symbol="HDFCBANK"), indent=1
    )
    out["nse/financial_results_HCLTECH.json"] = json.dumps(
        j(
            f"{base}/corporates-financial-results",
            index="equities",
            period="quarterly",
            symbol="HCLTECH",
        )[:6],
        indent=1,
    )
    week = (today + timedelta(days=7)).strftime(fmt)
    out["nse/board_meetings_next_7d.json"] = json.dumps(
        j(
            f"{base}/corporate-board-meetings",
            index="equities",
            from_date=today.strftime(fmt),
            to_date=week,
        ),
        indent=1,
    )

    rss = files.get("https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml")
    out["nse/rss_online_announcements.xml"] = rss.text

    eq = files.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv")
    out["nse/EQUITY_L_sample.csv"] = _trim_csv(eq.text, symbol_col=0)
    out["nse/EQUITY_L_rowcount.txt"] = str(len(eq.text.splitlines()) - 1)

    ymd, dmy = day.strftime("%Y%m%d"), day.strftime("%d%m%Y")
    z = files.get(
        f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
    )
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        bhav = zf.read(zf.namelist()[0]).decode("utf-8")
    sym_col = bhav.splitlines()[0].split(",").index("TckrSymb")
    out[f"nse/bhavcopy_udiff_{ymd}_sample.csv"] = _trim_csv(bhav, symbol_col=sym_col)
    deliv = files.get(
        f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{dmy}.csv"
    )
    out[f"nse/sec_bhavdata_full_{dmy}_sample.csv"] = _trim_csv(deliv.text, symbol_col=0)
    return out


@app.local_entrypoint()
def main() -> None:
    root = _fixtures_dir()
    for name, text in fetch.remote().items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"{path.relative_to(root.parent)}  {len(text):>8} chars")
