"""Day-0 spike: which data sources answer from the production runtime?

Run on Modal, not on a laptop, because exchange sites treat cloud IP ranges
differently from home connections:

    modal run finn/ops/spike.py

Prints one JSON object per source: status, latency, bytes, and a short sanity check.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import modal

app = modal.App("finn-spike")
image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "httpx[http2]>=0.27", "yfinance>=0.2"
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
NSE_SYMBOL, BSE_CODE, YAHOO = "TATAPOWER", "500400", "TATAPOWER.NS"


def last_weekday_before(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _timed(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    start = time.monotonic()
    try:
        out = {"source": name, **fn()}
    except Exception as exc:  # a spike reports failures, it does not raise them
        out = {"source": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    out["ms"] = round((time.monotonic() - start) * 1000)
    return out


@app.function(image=image, timeout=300)
def probe() -> list[dict[str, Any]]:
    import httpx
    import yfinance as yf

    day = last_weekday_before(date.today())
    ymd, dmy = day.strftime("%Y%m%d"), day.strftime("%d%m%Y")
    browser = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    nse = httpx.Client(headers=browser, http2=True, follow_redirects=True, timeout=20)
    plain = httpx.Client(headers=browser, follow_redirects=True, timeout=30)

    def nse_rss() -> dict[str, Any]:
        r = plain.get("https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml")
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "bytes": len(r.content),
            "items": r.text.count("<item>"),
        }

    def nse_api() -> dict[str, Any]:
        home = nse.get("https://www.nseindia.com/")
        r = nse.get(
            "https://www.nseindia.com/api/corporate-announcements",
            params={"index": "equities", "symbol": NSE_SYMBOL},
            headers={
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
            },
        )
        rows = (
            r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        )
        return {
            "ok": r.status_code == 200 and isinstance(rows, list),
            "home_status": home.status_code,
            "status": r.status_code,
            "rows": len(rows) if isinstance(rows, list) else None,
        }

    def nse_bhavcopy() -> dict[str, Any]:
        url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
        r = plain.get(url)
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "bytes": len(r.content),
            "trade_date": ymd,
        }

    def nse_delivery() -> dict[str, Any]:
        r = plain.get(
            f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{dmy}.csv"
        )
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "bytes": len(r.content),
            "has_tatapower": NSE_SYMBOL in r.text,
        }

    def bse_api() -> dict[str, Any]:
        r = plain.get(
            "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
            params={
                "pageno": 1,
                "strCat": -1,
                "strPrevDate": ymd,
                "strScrip": BSE_CODE,
                "strSearch": "P",
                "strToDate": ymd,
                "strType": "C",
                "subcategory": -1,
            },
            headers={"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"},
        )
        body = r.json() if "json" in r.headers.get("content-type", "") else None
        table = body.get("Table") if isinstance(body, dict) else None
        return {
            "ok": r.status_code == 200 and table is not None,
            "status": r.status_code,
            "rows": len(table) if isinstance(table, list) else None,
        }

    def screener() -> dict[str, Any]:
        r = plain.get(f"https://www.screener.in/company/{NSE_SYMBOL}/consolidated/")
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "bytes": len(r.content),
            "has_concalls": "Concalls" in r.text,
            "has_annual_reports": "Annual reports" in r.text,
        }

    def yahoo() -> dict[str, Any]:
        df = yf.download(YAHOO, period="1mo", interval="1d", progress=False, auto_adjust=False)
        return {"ok": len(df) > 0, "rows": len(df)}

    results = [
        _timed(name, fn)
        for name, fn in (
            ("nse_rss", nse_rss),
            ("nse_api", nse_api),
            ("nse_bhavcopy", nse_bhavcopy),
            ("nse_delivery", nse_delivery),
            ("bse_api", bse_api),
            ("screener", screener),
            ("yahoo", yahoo),
        )
    ]
    results.append(
        _timed("egress_ip", lambda: {"ok": True, "ip": plain.get("https://api.ipify.org").text})
    )
    return results


@app.local_entrypoint()
def main() -> None:
    for row in probe.remote():
        print(json.dumps(row))
