"""Quarterly results from the XBRL that companies file with NSE under Integrated Filing.

Since 2025 the results XBRL carries only the reported quarter and the year to date, so a
results card needs three filings: this quarter, the one before, and the same quarter a
year earlier. Each is parsed here into `StatementLines` in INR crore; the comparisons
are computed by `finn.push.results_math`, never read from a document.

Facts are matched by element name (the namespace prefix varies by taxonomy version) and
by a context whose period is exactly the quarter, with no dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from xml.etree import ElementTree as ET

from finn.push.results_math import StatementLines

XBRLI = "{http://www.xbrl.org/2003/instance}"
RUPEES_PER_CRORE = 10_000_000.0

# Element names in the Ind AS results taxonomy, first match wins.
FIELDS: dict[str, tuple[str, ...]] = {
    "revenue_from_operations": ("RevenueFromOperations",),
    "other_income": ("OtherIncome",),
    "finance_costs": ("FinanceCosts",),
    "depreciation": (
        "DepreciationDepletionAndAmortisationExpense",
        "DepreciationAndAmortisationExpense",
    ),
    "profit_before_exceptional_and_tax": (
        "ProfitBeforeExceptionalItemsAndTax",
        "ProfitLossBeforeExceptionalItemsAndTax",
    ),
    "exceptional_items": ("ExceptionalItemsBeforeTax", "ExceptionalItems"),
    "profit_before_tax": ("ProfitBeforeTax", "ProfitLossBeforeTax"),
    "tax_expense": ("TaxExpense", "IncomeTaxExpense"),
    "profit_after_tax": ("ProfitLossForPeriod", "ProfitLossForThePeriod"),
    "share_of_associates_jv": (
        "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
    ),
}
REQUIRED = ("revenue_from_operations", "profit_before_tax", "profit_after_tax")
OPTIONAL_ZERO = (
    "other_income",
    "finance_costs",
    "depreciation",
    "exceptional_items",
    "tax_expense",
    "share_of_associates_jv",
)


class XbrlError(ValueError):
    pass


# Banks file in their own taxonomy (Banking Regulation Act formats).
BANK_FIELDS: dict[str, tuple[str, ...]] = {
    "revenue_from_operations": ("Income",),
    "other_income": ("OtherIncome",),
    "finance_costs": ("InterestExpended",),
    "exceptional_items": ("ExceptionalItems",),
    "profit_before_tax": ("ProfitLossFromOrdinaryActivitiesBeforeTax",),
    "tax_expense": ("TaxExpense",),
    "profit_after_tax": (
        "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
        "ProfitLossForThePeriod",
    ),
    "share_of_associates_jv": ("ShareOfProfitLossOfAssociates",),
}


@dataclass(frozen=True, slots=True)
class QuarterResults:
    quarter_start: date
    quarter_end: date
    basis: str  # Consolidated | Standalone
    audited: str | None
    lines: StatementLines
    attributable_to_owners: float | None  # PAT attributable to owners of the parent, crore
    lender: bool = False  # a bank or NBFC: NII and PPOP replace revenue and EBITDA


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def quarter_start_for(quarter_end: date) -> date:
    month = quarter_end.month - 2
    year = quarter_end.year
    if month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def parse_results_xbrl(
    xml_text: str | bytes, quarter_end: date, taxonomy: str = "indas"
) -> QuarterResults:
    """The quarter ending `quarter_end`, read from one Integrated Filing (Financials) XBRL.
    `taxonomy` is indas (companies), nbfc (Ind AS lenders) or banking (banks)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise XbrlError(f"not XML: {exc}") from None
    start = quarter_start_for(quarter_end)

    quarter_contexts: set[str] = set()
    for ctx in root.iter(f"{XBRLI}context"):
        if ctx.find(f"{XBRLI}entity/{XBRLI}segment") is not None:
            continue
        s = ctx.find(f"{XBRLI}period/{XBRLI}startDate")
        e = ctx.find(f"{XBRLI}period/{XBRLI}endDate")
        if s is None or e is None or not s.text or not e.text:
            continue
        if (
            date.fromisoformat(s.text.strip()) == start
            and date.fromisoformat(e.text.strip()) == quarter_end
        ):
            cid = ctx.get("id")
            if cid:
                quarter_contexts.add(cid)
    if not quarter_contexts:
        raise XbrlError(f"no context for the quarter {start} to {quarter_end}")

    facts: dict[str, float] = {}
    text_facts: dict[str, str] = {}
    for el in root:
        ref = el.get("contextRef")
        if ref not in quarter_contexts or el.text is None:
            continue
        name = _local(el.tag)
        value = el.text.strip()
        if el.get("unitRef"):
            try:
                facts.setdefault(name, float(value))
            except ValueError:
                continue
        else:
            text_facts.setdefault(name, value)

    def crore(name: str) -> float | None:
        v = facts.get(name)
        return None if v is None else v / RUPEES_PER_CRORE

    values: dict[str, float] = {}
    for field_name, names in (BANK_FIELDS if taxonomy == "banking" else FIELDS).items():
        for n in names:
            v = crore(n)
            if v is not None:
                values[field_name] = v
                break
    missing = [f for f in REQUIRED if f not in values]
    if missing:
        raise XbrlError(f"missing {', '.join(missing)}")
    for f in OPTIONAL_ZERO:
        values.setdefault(f, 0.0)
    if "profit_before_exceptional_and_tax" not in values:
        values["profit_before_exceptional_and_tax"] = (
            values["profit_before_tax"] - values["exceptional_items"]
        )

    lender = False
    interest = crore("InterestEarned")
    if taxonomy == "banking":
        ppop = crore("OperatingProfitBeforeProvisionAndContingencies")
        if interest is None or ppop is None:
            raise XbrlError("bank results without interest earned or operating profit")
        values["net_interest_income"] = interest - values["finance_costs"]
        values["operating_profit_before_provisions"] = ppop
        lender = True
    elif taxonomy == "nbfc" and interest is not None:
        values["net_interest_income"] = interest - values["finance_costs"]
        values["operating_profit_before_provisions"] = values[
            "profit_before_exceptional_and_tax"
        ] + (crore("ImpairmentOnFinancialInstruments") or 0.0)
        lender = True
    owners = facts.get("ProfitOrLossAttributableToOwnersOfParent")
    return QuarterResults(
        quarter_start=start,
        quarter_end=quarter_end,
        basis=text_facts.get("NatureOfReportStandaloneConsolidated", "").title() or "Unknown",
        audited=text_facts.get("WhetherResultsAreAuditedOrUnaudited"),
        lines=StatementLines(**{k: round(v, 4) for k, v in values.items()}),
        attributable_to_owners=None if owners is None else round(owners / RUPEES_PER_CRORE, 4),
        lender=lender,
    )
