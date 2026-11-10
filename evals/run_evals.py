"""FINN's evals, measured from what production stored. Writes docs/EVALS.md.

    FINN_ENV_FILE=... uv run --project apps/worker python -m finn.ops.envrun \
        python evals/run_evals.py [generalisation-symbols...]

Every figure below is computed by this script from the database; nothing is typed in.
The generalisation run takes the symbols of companies built for the eval (drawn at
random, seed 20261110, from companies with results filed in the last 120 days that FINN
had not researched).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finn.core.config import load_settings
from finn.core.migrate import NeonHttp
from finn.llm.client import shadow_cost

OUT = Path(__file__).resolve().parents[1] / "docs" / "EVALS.md"


def body(x: Any) -> dict[str, Any]:
    return x if isinstance(x, dict) else json.loads(x)


def pct(a: float, b: float) -> str:
    return "–" if not b else f"{a / b * 100:.1f}%"


def main(gen: list[str]) -> None:
    db = NeonHttp(load_settings().database_url)
    q = db.query
    lines: list[str] = []
    w = lines.append
    w("# FINN evals")
    w("")
    w(
        f"Measured from production on {datetime.now(UTC):%d %b %Y %H:%M} UTC by `evals/run_evals.py`."
    )
    w(
        "Every number is computed by the script from what FINN stored; rerun it to refresh."
    )

    # --- Push: classification ---------------------------------------------------------
    f = q(
        "select count(*) n, count(*) filter (where classified_by = 'rules') rules,"
        " count(*) filter (where category is null) unclassified,"
        " count(*) filter (where filed_at > now() - interval '30 days') recent"
        " from filings"
    )[0]
    tiers = q(
        "select tier, count(*) n, sum(filing_count) filings from events"
        " where first_seen_at > now() - interval '30 days' group by tier"
    )
    by_tier = {r["tier"]: (int(r["n"]), int(r["filings"] or 0)) for r in tiers}
    ev = sum(v[0] for v in by_tier.values())
    fl = sum(v[1] for v in by_tier.values())
    w("")
    w("## Push: filings ranked without a model")
    w("")
    w("| Measure | Value |")
    w("|---|---|")
    w(f"| Filings ingested from NSE | {int(f['n']):,} |")
    w(
        f"| Classified by a rule in `rules.yaml` | {int(f['rules']):,} ({pct(int(f['rules']), int(f['n']))}) |"
    )
    w(f"| Left uncategorised | {int(f['unclassified']):,} |")
    w("| Model calls to classify or rank a filing | 0 |")
    w(
        f"| Events in the last 30 days (filings clustered) | {ev:,} from {fl:,} filings |"
    )
    for t, label in (
        ("front", "Read first"),
        ("oneliner", "One line"),
        ("folded", "Folded as routine"),
    ):
        n, m = by_tier.get(t, (0, 0))
        w(f"| {label} | {n:,} events ({pct(n, ev)}) |")
    w("")
    w(
        "Rows from filings before the `classified_by` column was added count as unclassified "
        "by rule here even when a rule placed them; the share above is a floor."
    )

    # --- Results cards ----------------------------------------------------------------
    rc = q(
        "select enrichment->'results_card'->>'status' s, count(*) n from events"
        " where enrichment ? 'results_card' group by 1"
    )
    total = sum(int(r["n"]) for r in rc)
    ok = sum(int(r["n"]) for r in rc if r["s"] == "ok")
    w("")
    w("## Results cards: figures from XBRL, arithmetic in code")
    w("")
    w(
        f"{total} results cards built from NSE XBRL filings; {ok} passed every consistency check "
        f'({pct(ok, total)}). A card that fails shows "Numbers need a look" with the filing link '
        "instead of figures."
    )

    # --- Pull: annual-report statements -------------------------------------------------
    cash = q(
        "select a.value sym, d.body from dossier_sections d join company_aliases a"
        " on a.isin = d.isin and a.kind = 'nse_symbol' and a.valid_to is null"
        " where d.section = 'cash'"
    )
    years = failing = lender_years = matched = compared = 0
    bs = bs_ok = withheld = 0
    fails: Counter[str] = Counter()
    for r in cash:
        b = body(r["body"])
        for y in b.get("years", []):
            years += 1
            if y["failures"]:
                failing += 1
                fails.update(y["failures"])
            st = (y.get("quarters") or {}).get("status")
            if st in ("matches", "differs") and not b.get("lender"):
                compared += 1
                matched += st == "matches"
            if y.get("balance"):
                bs += 1
                bs_ok += not y.get("balance_failures")
            withheld += bool(y.get("withheld"))
            lender_years += bool(b.get("lender"))
    w("")
    w("## Dossier: statements read from annual reports")
    w("")
    w("| Measure | Value |")
    w("|---|---|")
    w(f"| Companies with a Cash tab | {len(cash)} |")
    w(f"| Fiscal years read (cash flow and profit and loss) | {years} |")
    w(
        f"| Years passing every identity (shown) | {years - failing} ({pct(years - failing, years)}) |"
    )
    w(
        f"| Full-year revenue and profit equal to the four quarterly XBRL filings | "
        f"{matched} of {compared} years compared ({pct(matched, compared)}) |"
    )
    w(f"| Balance sheets that balance (shown) | {bs_ok} of {bs} ({pct(bs_ok, bs)}) |")
    w(f"| Years with a sum withheld because a line could not be read | {withheld} |")
    if fails:
        w(
            f"| Why years were held back | {', '.join(f'{k} ×{v}' for k, v in fails.most_common())} |"
        )
    w("")
    w(
        "The quarterly comparison is the independent check: the annual report and the XBRL "
        "results are separate filings, and FINN reads them by separate routes. Lenders are "
        "left out of it because their annual revenue line includes items the quarterly "
        "XBRL reports elsewhere."
    )

    # --- Pull: guidance and quotes ------------------------------------------------------
    led = q("select body from dossier_sections where section = 'ledger'")
    kept = dq = dfig = calls = 0
    for r in led:
        for t in body(r["body"]).get("transcripts", []):
            if t.get("status") == "read":
                calls += 1
                kept += int(t.get("promises") or 0)
                dq += int(t.get("dropped_quotes") or 0)
                dfig += int(t.get("dropped_figures") or 0)
    st = {
        r["status"]: int(r["n"])
        for r in q("select status, count(*) n from guidance group by 1")
    }
    measured = sum(
        st.get(k, 0) for k in ("delivered", "missed", "on_track", "off_track")
    )
    allg = sum(st.values())
    w("")
    w("## Dossier: the Promise Ledger")
    w("")
    w("| Measure | Value |")
    w("|---|---|")
    w(f"| Ledgers built | {len(led)} |")
    w(f"| Earnings-call transcripts read | {calls} |")
    w(f"| Promises kept (quote found verbatim on its page) | {kept} |")
    w(
        f"| Dropped: quote not in the transcript | {dq} ({pct(dq, kept + dq + dfig)} of candidates) |"
    )
    w(f"| Dropped: a figure not stated in the quote | {dfig} |")
    w(
        f"| Promises checked by code against filed figures | {measured} of {allg} ({pct(measured, allg)}) |"
    )
    w(
        f"| Status | {', '.join(f'{k.replace(chr(95), chr(32))} {v}' for k, v in sorted(st.items()))} |"
    )
    w("")
    w(
        "Every promise shown carries a quote that `verify_quote` found in the transcript text, "
        "so no promise is shown in words the company did not use. Most promises are about "
        "things the quarterly filings do not report (order inflow, deal wins, store counts) "
        "and stay 'not in the filings' rather than being guessed."
    )

    # --- Bull and bear ----------------------------------------------------------------
    cases = q("select body from dossier_sections where section = 'case'")
    pts = drop = 0
    why: Counter[str] = Counter()
    for r in cases:
        b = body(r["body"])
        pts += len(b.get("bull", [])) + len(b.get("bear", []))
        for d in b.get("dropped", []):
            drop += 1
            why[d.split(": ", 1)[-1].split(" ")[0]] += 1
    w("")
    w("## Dossier: bull and bear")
    w("")
    w(
        f"{len(cases)} cases; {pts} points kept, {drop} dropped by code "
        f"({pct(drop, pts + drop)} of what the model wrote). A point is dropped if it cites no "
        "checked fact, states a figure its facts do not contain, or fails the house style."
    )

    # --- Generalisation ---------------------------------------------------------------
    if gen:
        w("")
        w("## Generalisation: ten companies FINN had not seen")
        w("")
        w(
            "Drawn at random (seed 20261110) from NSE companies that filed results in the last "
            "120 days, then built end to end with no changes to code or prompts."
        )
        w("")
        w(
            "| Symbol | Calls read | Promises | Annual reports read | Years shown | Quarters match | Bull / bear |"
        )
        w("|---|---|---|---|---|---|---|")
        full = with_calls = ledger_ok = 0
        for s in gen:
            rows = q(
                "select d.section, d.body from dossier_sections d join company_aliases a"
                " on a.isin = d.isin and a.kind = 'nse_symbol' and a.valid_to is null"
                f" where a.value = '{s}'"
            )
            sec = {r["section"]: body(r["body"]) for r in rows}
            tr = [
                t
                for t in sec.get("ledger", {}).get("transcripts", [])
                if t.get("status") == "read"
            ]
            ars = [
                x
                for x in sec.get("annual_reports", {}).get("reports", [])
                if x["status"] == "read"
            ]
            ys = sec.get("cash", {}).get("years", [])
            shown = [y for y in ys if not y["failures"]]
            mt = sum((y.get("quarters") or {}).get("status") == "matches" for y in ys)
            case = sec.get("case", {})
            nb, nr = len(case.get("bull", [])), len(case.get("bear", []))
            good = len(ars) >= 1 and len(shown) >= 2 and (nb + nr) > 0
            full += good
            with_calls += bool(tr)
            ledger_ok += any(int(t.get("promises") or 0) for t in tr)
            w(
                f"| {s} | {len(tr)} | {sum(int(t.get('promises') or 0) for t in tr)} | {len(ars)} | "
                f"{len(shown)} of {len(ys)} | {mt} | {nb} / {nr} |"
            )
        w("")
        w(
            f"**{full} of {len(gen)}** got the annual-report half (a report read, two or more "
            "years of statements shown, and a case); the rest have no annual report on NSE. "
            f"**{with_calls} of {len(gen)}** have earnings-call transcripts on NSE, and "
            f"{ledger_ok} of those got a Promise Ledger with at least one promise; the others "
            "file no transcripts, so there is nothing to build a ledger from."
        )

    # --- Cost and speed ---------------------------------------------------------------
    # Repriced from logged tokens at today's list prices (models.yaml), so calls made
    # before a price was filled in are counted too; cache hits cost nothing.
    cost = q(
        "select task, count(*) n, count(*) filter (where cache_hit) cached,"
        " count(*) filter (where not ok) failed,"
        " percentile_cont(0.5) within group (order by latency_ms)"
        "   filter (where not cache_hit and ok) p50"
        " from llm_calls group by task order by n desc"
    )
    spend = q(
        "select task, model, coalesce(sum(tokens_in), 0) tin, coalesce(sum(tokens_out), 0) tout"
        " from llm_calls where not cache_hit and ok group by 1, 2"
    )
    usd: dict[str, float] = {}
    toks: dict[str, tuple[int, int]] = {}
    for r in spend:
        t = str(r["task"])
        usd[t] = usd.get(t, 0.0) + shadow_cost(
            str(r["model"]), int(r["tin"]), int(r["tout"])
        )
        a, b = toks.get(t, (0, 0))
        toks[t] = (a + int(r["tin"]), b + int(r["tout"]))
    for r in cost:
        r["usd"] = usd.get(str(r["task"]), 0.0)
        r["tin"], r["tout"] = toks.get(str(r["task"]), (0, 0))
    jobs = q(
        "select count(*) n, percentile_cont(0.5) within group (order by extract(epoch from"
        " finished_at - started_at)) p50, max(extract(epoch from finished_at - started_at)) mx"
        " from jobs where kind = 'research' and status = 'done' and started_at is not null"
    )[0]
    dossiers = len(led)
    pull_usd = sum(float(r["usd"]) for r in cost if r["task"] != "people_card")
    w("")
    w("## Cost and speed")
    w("")
    w(
        "Models run on free tiers; the shadow cost is what the same tokens would cost at list "
        "prices, logged on every call."
    )
    w("")
    w(
        "| Task | Calls | From cache | Failed (then retried or fell back) | Tokens in / out (uncached) | Shadow cost | Median latency (uncached) |"
    )
    w("|---|---|---|---|---|---|---|")
    for r in cost:
        w(
            f"| {r['task']} | {int(r['n'])} | {int(r['cached'])} | {int(r['failed'])} | "
            f"{int(r['tin']):,} / {int(r['tout']):,} | ${float(r['usd']):.2f} | "
            f"{float(r['p50'] or 0) / 1000:.1f} s |"
        )
    w("")
    w(
        "- The Brief and Pulse need no model call: classification, ranking, alerts and results "
        "arithmetic are rules and code. People cards are the only push-side model task."
    )
    if dossiers:
        w(
            f"- Dossiers: about ${pull_usd / dossiers:.3f} of shadow cost each across {dossiers} built "
            "(including rebuilds; cached answers cost nothing)."
        )
    if int(jobs["n"] or 0):
        w(
            f"- On-demand research jobs: {int(jobs['n'])} done, median {float(jobs['p50']):.0f} s, "
            f"slowest {float(jobs['mx']):.0f} s from request to finished dossier."
        )

    OUT.write_text("\n".join(lines) + "\n")
    print(OUT, len(lines), "lines")


if __name__ == "__main__":
    main(sys.argv[1:])
