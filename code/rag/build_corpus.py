# HW3 Part 2 - build the Domain 7 (community sports league fixtures) corpus.
# Pulls rendered HTML of public Wikipedia fixture/season articles, converts to text
import os, re, json, hashlib, datetime, urllib.parse, urllib.request
from html.parser import HTMLParser
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
CORPUS_DIR = os.path.join(ROOT, "data", "corpus")
REPORT_DIR = os.path.join(ROOT, "reports", "hw03")
ARTICLES = [
    "2023–24 Premier League",
    "2024 Major League Soccer season",
    "2023–24 La Liga",
    "2023–24 EFL Championship",
    "2024–25 UEFA Champions League",
]
WIKI_API = "https://en.wikipedia.org/w/api.php"
UA = "DATA260-HW3-corpus-builder/1.0 (student project)"
class _TextExtractor(HTMLParser):  # rendered HTML to readable text (tables kept)
    SKIP = {"script", "style", "sup"}
    BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "br", "table", "section", "caption"}
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, t, a):
        if t in self.SKIP: self.skip += 1
        if t in self.BLOCK: self.parts.append("\n")
        if t in ("td", "th"): self.parts.append(" | ")
    def handle_endtag(self, t):
        if t in self.SKIP and self.skip > 0: self.skip -= 1
        if t in self.BLOCK: self.parts.append("\n")
    def handle_data(self, d):
        if self.skip == 0: self.parts.append(d)
def html_to_text(html):
    p = _TextExtractor(); p.feed(html); txt = "".join(p.parts)
    txt = re.sub(r"\[\d+\]", "", txt)          
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n\n", txt)
    return txt.strip()
def slug(title):
    s = title.replace("–", "-").replace("—", "-")
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
def wiki_url(title):
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
def fetch_text(title):  # rendered HTML via the parse API, then converted to text
    params = {"action": "parse", "page": title, "prop": "text",
              "redirects": "1", "format": "json", "formatversion": "2"}
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        html = json.load(r)["parse"]["text"]
    return html_to_text(html)
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
def main():
    os.makedirs(CORPUS_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    manifest, total = [], 0
    lines = ["# SOURCES — Domain 7: Community Sports League Fixtures", "",
             f"Corpus downloaded {today}. All documents are public Wikipedia articles (rendered text).", ""]
    for title in ARTICLES:
        print(f"Fetching: {title} ...")
        text = fetch_text(title)
        fname = slug(title) + ".txt"
        fpath = os.path.join(CORPUS_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(text)
        size = os.path.getsize(fpath); total += size
        rel = os.path.relpath(fpath, ROOT)
        manifest.append({"title": title, "local_file": rel, "url": wiki_url(title),
                         "access_date": today, "bytes": size, "sha256": sha256(fpath)})
        lines.append(f"- **{title}** — {wiki_url(title)} (accessed {today}) → `{rel}` ({size} bytes)")
        print(f"  saved {rel} ({size} bytes)")
    with open(os.path.join(REPORT_DIR, "CORPUS_MANIFEST.json"), "w") as f:
        json.dump({"domain_id": 7, "domain": "Community sports league fixtures",
                   "generated": today, "total_bytes": total, "documents": manifest}, f, indent=2)
    with open(os.path.join(REPORT_DIR, "SOURCES.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nTotal corpus size: {total} bytes ({total/1024:.1f} KB)")
    print("OK: corpus >= 200 KB." if total >= 200 * 1024 else "!!! Under 200 KB — add articles to ARTICLES and re-run.")
    try:
        ts = "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
        tp = os.path.join(ROOT, "data", "tinyshakespeare.txt")
        with urllib.request.urlopen(urllib.request.Request(ts, headers={"User-Agent": UA}), timeout=60) as r:
            open(tp, "wb").write(r.read())
        print(f"Warm-up saved: {os.path.relpath(tp, ROOT)} ({os.path.getsize(tp)} bytes)")
    except Exception as e:
        print("Warm-up skipped:", e)
if __name__ == "__main__":
    main()