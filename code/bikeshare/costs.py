# HW7 Part 4: cost engine - parses the pricing snapshot and computes costs only through the three MRKL tools
import re

from . import tools

PRICE_PATTERNS = {  # each value must come from a quotable sentence on the pricing page
    "unlock_fee": r"\$\s?(\d+(?:\.\d+)?)\s+to unlock",
    "ppu_classic_per_min": r"\$\s?(\d*\.\d+)\s*/\s*minute for classic",
    "ppu_ebike_per_min": r"\$\s?(\d*\.\d+)\s*/\s*minute for ebikes",
    "monthly_price": r"\$\s?(\d+(?:\.\d+)?)\s*/\s*month",
    "annual_price": r"\$\s?(\d+(?:\.\d+)?)\s*/\s*year",
    "member_included_min": r"unlimited (\d+)-minute (?:rides|trips) on classic|longer than (\d+) minutes and pay",
    "member_overage_per_min": r"(?:longer than \d+ minutes and pay|then)\s+\$\s?(\d*\.\d+)\s*/\s*min",
    "member_ebike_per_min": r"discounted rate of \$\s?(\d*\.\d+)\s*/\s*min on ebikes",
}


def sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind("\n", 0, start), text.rfind(". ", 0, start))
    right = min([i for i in (text.find("\n", end), text.find(". ", end)) if i != -1] or [len(text)])
    return text[left + 1 : right + 1].strip()[:240]


def parse_prices(text: str) -> tuple[dict, dict]:
    prices, quotes = {}, {}
    for key, pattern in PRICE_PATTERNS.items():
        m = re.search(pattern, text, re.I)
        if m:
            prices[key] = float(next(g for g in m.groups() if g))
            quotes[key] = sentence_around(text, m.start(), m.end())
    return prices, quotes


def ride_sql(rider: str, p: dict) -> str:
    mins = "CAST(duration_min AS INT) + (duration_min > CAST(duration_min AS INT))"  # started minutes are billed
    return (
        f"SELECT {rider} AS rider, month, week_start, duration_min, {mins} AS mins, "
        f"(rideable_type LIKE '%electric%') AS ebike, "
        f"{p['unlock_fee']} + CASE WHEN rideable_type LIKE '%electric%' THEN ({mins}) * {p['ppu_ebike_per_min']} "
        f"ELSE ({mins}) * {p['ppu_classic_per_min']} END AS ppu_cost, "
        f"CASE WHEN rideable_type LIKE '%electric%' THEN ({mins}) * {p['member_ebike_per_min']} "
        f"WHEN ({mins}) > {p['member_included_min']} THEN (({mins}) - {p['member_included_min']}) * "
        f"{p['member_overage_per_min']} ELSE 0 END AS member_residual FROM trips"
    )


class Engine:
    def __init__(self, db_path, url, run_tag, record, strict_sql=True, untrusted_label=True):
        self.db, self.url, self.tag, self.record = db_path, url, run_tag, record
        self.strict, self.label = strict_sql, untrusted_label

    def sql(self, query: str, why: str) -> dict:
        out = tools.csv_sql(query, self.db, strict=self.strict)
        self.record("csv_sql", {"sql": query}, out, why)
        if not out["success"]:
            raise RuntimeError(out["error"])
        return out["data"]

    def calc(self, expr: str, units: str, why: str) -> float:
        out = tools.calculator(expr, units)
        self.record("calculator", {"expression": expr, "units": units}, out, why)
        if not out["success"]:
            raise RuntimeError(out["error"])
        return out["data"]["value"]

    def prices(self) -> tuple[dict, dict, dict]:
        query = "membership price per year month unlock fee per minute classic ebike 45 minutes overage"
        out = tools.policy_retriever(self.url, query, k=8, run_tag=self.tag, untrusted_label=self.label)
        self.record("policy_retriever", {"url": self.url, "query": query, "k": 8}, out, "verify prices")
        if not out["success"]:
            raise RuntimeError(out["error"])
        self.passages = out["data"]["passages"]  # kept so the final decide step sees exactly what the tool returned
        snap = tools.snapshot(self.url, self.tag)
        prices, quotes = parse_prices(snap["text"])
        missing = [k for k in PRICE_PATTERNS if k not in prices and k not in ("monthly_price", "annual_price")]
        if missing or not ({"monthly_price", "annual_price"} & set(prices)):
            raise RuntimeError(f"pricing page is missing: {', '.join(missing) or 'a membership price'}")
        return prices, quotes, snap

    def membership_monthly(self, prices: dict) -> tuple[float, str]:
        if "monthly_price" in prices:
            return prices["monthly_price"], "monthly price quoted on the pricing page"
        value = self.calc(f"{prices['annual_price']} / 12", "USD per month", "annual membership spread per month")
        return value, "no monthly price is published, so the annual membership is spread over 12 months"

    def run(self) -> dict:
        prices, quotes, snap = self.prices()
        monthly, monthly_note = self.membership_monthly(prices)
        p = {**prices, "monthly": monthly}
        first = self.sql("SELECT * FROM trips LIMIT 1", "read the columns")["rows"]
        if not first:
            raise RuntimeError("trips table is empty (0 rows left)")
        cols = list(first[0])
        rider = "rider_id" if "rider_id" in cols else "'rider-1'"
        rides = ride_sql(rider, p)
        prof = self.sql(
            f"SELECT COUNT(*) AS trips, COUNT(DISTINCT rider) AS riders, MIN(month) AS first_month, MAX(month) AS "
            f"last_month, SUM(ebike) AS ebike_trips, SUM(duration_min > {p['member_included_min']}) AS over_included, "
            f"ROUND(AVG(duration_min), 1) AS avg_min, SUM(duration_min <= 0) AS bad_durations, "
            f"SUM(duration_min > 1440) AS over_one_day FROM ({rides})",
            "usage profile",
        )["rows"][0]
        agg = self.sql(
            f"SELECT COUNT(*) AS rider_months, SUM(n) AS rides, ROUND(SUM(ppu), 2) AS ppu_total, "
            f"ROUND(SUM(resid), 2) AS member_residual, SUM({monthly} + resid < ppu) AS months_membership_cheaper "
            f"FROM (SELECT rider, month, COUNT(*) AS n, SUM(ppu_cost) AS ppu, SUM(member_residual) AS resid "
            f"FROM ({rides}) GROUP BY rider, month)",
            "cost per rider-month",
        )["rows"][0]
        weekly = self.sql(
            f"SELECT week_start, COUNT(*) AS rides, ROUND(AVG(duration_min), 1) AS avg_min, "
            f"ROUND(SUM(ppu_cost), 2) AS pay_per_use_spend, ROUND(SUM(member_residual), 2) AS member_extra "
            f"FROM ({rides}) GROUP BY week_start ORDER BY week_start",
            "weekly table",
        )["rows"]
        fees = self.calc(f"{agg['rider_months']} * {monthly}", "USD", "membership fees")
        member_total = self.calc(f"{fees} + {agg['member_residual']}", "USD", "membership + residual charges")
        ppu_ride = self.calc(f"{agg['ppu_total']} / {agg['rides']}", "USD per ride", "pay-per-use per ride")
        resid_ride = self.calc(f"{agg['member_residual']} / {agg['rides']}", "USD per ride", "member extra per ride")
        gap = max(ppu_ride - resid_ride, 0.0001)
        breakeven = self.calc(f"{monthly} / {gap:.4f}", "rides per rider-month", "break-even rides")
        actual = self.calc(f"{agg['rides']} / {agg['rider_months']}", "rides per rider-month", "actual rides")
        savings = self.calc(f"{agg['ppu_total']} - {member_total}", "USD", "pay-per-use minus membership")
        decision = "Buy Monthly Membership" if member_total < agg["ppu_total"] else "Pay Per Ride/Minute"
        return {
            "prices": p,
            "quotes": quotes,
            "monthly_note": monthly_note,
            "profile": prof,
            "weekly": weekly,
            "snapshot": {k: snap[k] for k in ("url", "accessed_at_utc", "sha256", "text_file")},
            "costs": {
                "pay_per_use_total": agg["ppu_total"],
                "membership_fees": fees,
                "membership_residual": agg["member_residual"],
                "membership_total": member_total,
                "savings_if_membership": savings,
                "pay_per_use_per_ride": ppu_ride,
                "member_extra_per_ride": resid_ride,
                "breakeven_rides_per_rider_month": breakeven,
                "actual_rides_per_rider_month": actual,
                "rider_months": agg["rider_months"],
                "rider_months_where_membership_cheaper": agg["months_membership_cheaper"],
            },
            "decision_by_numbers": decision,
            "passages": self.passages,
        }
