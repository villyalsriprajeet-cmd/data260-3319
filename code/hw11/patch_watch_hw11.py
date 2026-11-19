# HW11 (s3319): applies the Stock Watch extensions to the kit's watch.py (run once)
import sys

PATH = sys.argv[1]
src = open(PATH, encoding="utf-8").read()
if "def cmd_vol(" in src:
    sys.exit("already patched, nothing to do")

EDITS = [
    (
        "  snapshot [--out FILE]        write all state",
        "  vol    [--days N]            HW11: daily-move statistics per live ticker (for policy thresholds)\n"
        "  snapshot [--out FILE]        write all state",
    ),
    (
        'f"Alert threshold is {threshold}%.",',
        'f"Candidate floor is {threshold}%; the notify threshold for {t} is in policy.md.",',
    ),
    (
        "def fetch_source(src, args, allowed_hosts, con, run_id):\n",
        "# HW11 (s3319): since 2026 Stooq may need a free API key (captcha on stooq.com). The key comes from\n"
        "# STOOQ_APIKEY or state/stooq_apikey, never from sources.json, and is never logged or printed.\n"
        "def stooq_key(home):\n"
        '    key = os.environ.get("STOOQ_APIKEY", "").strip()\n'
        '    p = os.path.join(home, "state", "stooq_apikey")\n'
        "    if not key and os.path.exists(p):\n"
        '        with open(p, encoding="utf-8") as f:\n'
        "            key = f.read().strip()\n"
        "    return key\n"
        "\n"
        "\n"
        "def stooq_url(src, tk, home):\n"
        '    q = {"s": tk, "i": "d"}\n'
        "    if stooq_key(home):\n"
        '        q["apikey"] = stooq_key(home)\n'
        '    return src["url"] + "?" + urllib.parse.urlencode(q)\n'
        "\n"
        "\n"
        "def check_csv(text, tk):\n"
        "    # without a valid key Stooq answers with an HTML page; fail loudly instead of finding 0 moves\n"
        '    if not text.lstrip().startswith("Date,"):\n'
        '        raise ValueError(f"Stooq returned no price CSV for {tk} (API key missing or invalid?)")\n'
        "\n"
        "\n"
        "def fetch_source(src, args, allowed_hosts, con, run_id):\n",
    ),
    (
        "                text = http_get(f\"{src['url']}?s={tk}&i=d\", allowed_hosts, con, run_id)\n",
        "                text = http_get(stooq_url(src, tk, args.home), allowed_hosts, con, run_id)\n"
        "            check_csv(text, tk)\n",
    ),
    (
        '    out({\n        "run_id": run_id,\n        "pending_decisions": len(rows),\n'
        '        "duplicates_suppressed": dups,\n',
        '    errs = [json.loads(r["detail"]) for r in con.execute(\n'
        "        \"SELECT detail FROM trace WHERE run_id=? AND step='source_error' ORDER BY rowid\", (run_id,))]\n"
        '    out({\n        "run_id": run_id,\n        "pending_decisions": len(rows),\n'
        '        "duplicates_suppressed": dups,\n'
        '        "source_errors": errs,  # HW11: a failed source is reported, not silently skipped\n',
    ),
    (
        'TABLES = ["runs",',
        "def cmd_vol(a):\n"
        '    """HW11: daily-move statistics per live ticker, to justify per-ticker thresholds in policy.md."""\n'
        "    con = connect(a.home)\n"
        "    cfg, allowed = load_sources(a.home)\n"
        "    res = {}\n"
        '    for src in [s for s in cfg["sources"] if s.get("type") == "stooq" and "live" in s.get("modes", [])]:\n'
        '        for tk in src["tickers"]:\n'
        "            try:\n"
        "                text = http_get(stooq_url(src, tk, a.home), allowed, con, None)\n"
        "                check_csv(text, tk)\n"
        "            except Exception as e:\n"
        '                res[tk] = {"error": str(e)[:200]}\n'
        "                continue\n"
        '            rows = [r.split(",") for r in text.strip().splitlines()[1:] if r.strip()]\n'
        '            closes = [(r[0], float(r[4])) for r in rows if len(r) >= 5 and r[4] not in ("", "N/D")]\n'
        "            closes = closes[-(a.days + 1):]\n"
        "            moves = [abs(c1 / c0 - 1) * 100 for (_, c0), (_, c1) in zip(closes, closes[1:])]\n"
        "            n = len(moves)\n"
        "            mean = sum(moves) / max(1, n)\n"
        "            rms = (sum(m * m for m in moves) / max(1, n)) ** 0.5\n"
        '            res[tk] = {"days": n, "from": closes[0][0] if closes else None,\n'
        '                       "to": closes[-1][0] if closes else None,\n'
        '                       "last_close": closes[-1][1] if closes else None,\n'
        '                       "mean_abs_move_pct": round(mean, 2), "rms_move_pct": round(rms, 2),\n'
        '                       "max_abs_move_pct": round(max(moves, default=0), 2),\n'
        '                       **{f"days_ge_{k}pct": sum(1 for m in moves if m >= k) for k in (2, 3, 5, 7, 10)}}\n'
        "    con.commit()\n"
        '    out({"window_trading_days": a.days, "tickers": res})\n'
        "    return 0\n"
        "\n"
        "\n"
        'TABLES = ["runs",',
    ),
    (
        '    s = sp.add_parser("snapshot"); s.add_argument("--out")\n',
        '    s = sp.add_parser("snapshot"); s.add_argument("--out")\n'
        '    s = sp.add_parser("vol"); s.add_argument("--days", type=int, default=250)\n',
    ),
    (
        '"fetch": cmd_fetch, "snapshot": cmd_snapshot,',
        '"fetch": cmd_fetch, "vol": cmd_vol, "snapshot": cmd_snapshot,',
    ),
]

for i, (old, new) in enumerate(EDITS, 1):
    if src.count(old) != 1:
        sys.exit(f"edit {i} failed: anchor found {src.count(old)} times; watch.py was not changed")
    src = src.replace(old, new)
open(PATH, "w", encoding="utf-8").write(src)
print(f"patched {PATH}: {len(EDITS)} edits applied")
