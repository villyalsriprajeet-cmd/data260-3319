# HW11 (s3319): second extension of the kit's watch.py, run once after patch_watch_hw11.py.
# From the Muse cloud computer (Nov 2026) Stooq answers with a JavaScript bot check and the
# legacy SEC browse-edgar Atom URL answers HTTP 400. This adds two live source types:
#   "yahoo"      daily closes from the Yahoo Finance chart API (no key), turned into the kit's CSV
#   "edgar_json" 8-K filings from the SEC's official data.sec.gov submissions API
# Fixtures keep the kit's Stooq CSV and EDGAR Atom formats, so the golden set is unaffected.
import sys

PATH = sys.argv[1]
src = open(PATH, encoding="utf-8").read()
if "def cmd_vol(" not in src:
    sys.exit("run patch_watch_hw11.py first")
if "def yahoo_csv(" in src:
    sys.exit("already patched, nothing to do")

NEW_FUNCS = '''
# HW11 (s3319): live sources that work from the Muse cloud computer ---------------------
ITEM_NAMES = {
    "1.01": "Entry into a Material Definitive Agreement", "1.02": "Termination of a Material Agreement",
    "1.05": "Material Cybersecurity Incident", "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition", "2.03": "Creation of a Direct Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities", "2.06": "Material Impairments",
    "3.01": "Notice of Delisting", "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders", "4.01": "Change in Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements", "5.01": "Change in Control",
    "5.02": "Departure/Appointment of Directors or Officers", "5.03": "Amendments to Articles or Bylaws",
    "5.07": "Submission of Matters to a Vote of Security Holders", "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events", "9.01": "Financial Statements and Exhibits",
}


def yahoo_url(src, tk, rng="1mo"):
    return src["url"].rstrip("/") + "/" + urllib.parse.quote(tk) + "?" + urllib.parse.urlencode(
        {"range": rng, "interval": "1d"})


def yahoo_csv(json_text, tk, drop_open_day=True):
    """Yahoo chart JSON -> the kit's CSV (Date,Open,High,Low,Close,Volume); a missing close -> N/D.
    While the market is still open the last bar is a partial day, so it is dropped."""
    try:
        res = json.loads(json_text)["chart"]["result"][0]
        meta, ts = res["meta"], res.get("timestamp") or []
        q = res["indicators"]["quote"][0]
    except Exception:
        raise ValueError(f"Yahoo returned no price data for {tk}")
    off = int(meta.get("gmtoffset", 0))
    end = (meta.get("currentTradingPeriod") or {}).get("regular", {}).get("end", 0)
    rows = ["Date,Open,High,Low,Close,Volume"]
    for i, t in enumerate(ts):
        if drop_open_day and i == len(ts) - 1 and time.time() < end and t >= end - 86400:
            continue
        d = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%d")
        o, h, lo, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        rows.append(",".join([d, "" if o is None else f"{o:.4f}", "" if h is None else f"{h:.4f}",
                              "" if lo is None else f"{lo:.4f}", "N/D" if c is None else f"{c:.4f}",
                              str(v or "")]))
    return "\\n".join(rows) + "\\n"


def edgar_json_items(json_text, tk, cik, form="8-K", n=5):
    """data.sec.gov submissions JSON -> feed items like the kit's EDGAR Atom parser makes."""
    d = json.loads(json_text)
    r = d["filings"]["recent"]
    items = []
    for i, fm in enumerate(r["form"]):
        if not fm.startswith(form):
            continue
        acc = r["accessionNumber"][i]
        codes = [c.strip() for c in (r.get("items", [""] * len(r["form"]))[i] or "").split(",") if c.strip()]
        names = "; ".join(f"Item {c} {ITEM_NAMES.get(c, '')}".strip() for c in codes) or "items not listed"
        doc = r.get("primaryDocument", [""] * len(r["form"]))[i]
        items.append({
            "guid": acc,
            "title": f"{tk}: {fm} - Current report{', amendment' if fm.endswith('/A') else ''} ({', '.join(codes)})",
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}",
            "published": r.get("acceptanceDateTime", r["filingDate"])[i] or r["filingDate"][i],
            "summary": f"{d.get('name', tk)} filed {fm} on {r['filingDate'][i]} (accession {acc}). {names}.",
        })
        if len(items) >= n:
            break
    return items


def fetch_source(src, args, allowed_hosts, con, run_id):'''

EDITS = [
    ("def fetch_source(src, args, allowed_hosts, con, run_id):", NEW_FUNCS.lstrip("\n")),
    (
        '    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})\n',
        '    ua = f"Mozilla/5.0 (compatible; {UA})" if host.endswith("finance.yahoo.com") else UA  # HW11\n'
        '    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})\n',
    ),
    (
        "        return items\n    if args.fixtures:\n",
        "        return items\n"
        '    if typ == "yahoo":  # HW11: live daily closes\n'
        "        items = []\n"
        '        for tk in src["tickers"]:\n'
        "            text = yahoo_csv(http_get(yahoo_url(src, tk), allowed_hosts, con, run_id), tk)\n"
        '            items += price_events(tk.upper(), text, src.get("threshold_pct", 2.0),\n'
        '                                  f"https://finance.yahoo.com/quote/{tk}", src.get("lookback_days", 3))\n'
        "        return items\n"
        '    if typ == "edgar_json":  # HW11: live 8-K filings from data.sec.gov\n'
        "        items = []\n"
        '        for tk, cik in src["ciks"].items():\n'
        '            url = src["url"].rstrip("/") + f"/CIK{int(cik):010d}.json"\n'
        "            items += edgar_json_items(http_get(url, allowed_hosts, con, run_id), tk, cik,\n"
        '                                      src.get("form", "8-K"), src.get("per_company", 5))\n'
        "        return items\n"
        "    if args.fixtures:\n",
    ),
    (
        '    for src in [s for s in cfg["sources"] if s.get("type") == "stooq" and "live" in s.get("modes", [])]:\n'
        '        for tk in src["tickers"]:\n'
        "            try:\n"
        "                text = http_get(stooq_url(src, tk, a.home), allowed, con, None)\n"
        "                check_csv(text, tk)\n",
        '    for src in [s for s in cfg["sources"]\n'
        '                if s.get("type") in ("stooq", "yahoo") and "live" in s.get("modes", [])]:\n'
        '        for tk in src["tickers"]:\n'
        "            try:\n"
        '                if src["type"] == "yahoo":\n'
        '                    rng = "2y" if a.days > 240 else "1y"\n'
        "                    text = yahoo_csv(http_get(yahoo_url(src, tk, rng), allowed, con, None), tk)\n"
        "                else:\n"
        "                    text = http_get(stooq_url(src, tk, a.home), allowed, con, None)\n"
        "                check_csv(text, tk)\n",
    ),
]

for i, (old, new) in enumerate(EDITS, 1):
    if src.count(old) != 1:
        sys.exit(f"edit {i} failed: anchor found {src.count(old)} times; watch.py was not changed")
    src = src.replace(old, new)
open(PATH, "w", encoding="utf-8").write(src)
print(f"patched {PATH}: {len(EDITS)} edits applied")
