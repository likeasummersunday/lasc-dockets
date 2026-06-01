"""
Citation Verifier v2.1 — citation existence + quotation checking, with
polite rate-limit handling (retries on HTTP 429).

Reads draft_to_check.txt (or .md). Resolves citations via CourtListener's
Citation Lookup API, then fetches real opinion text to confirm quotations.

LIMITS:
- "Citation verified" = the cite resolves to a real case. Not that it supports your point.
- "Quote found" = the words appear in the opinion text. NOT that the quote is from the
  majority (vs. dissent) or used in fair context. A human must read the case before filing.
"""

import os
import re
import json
import html
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("COURTLISTENER_TOKEN", "").strip()
LOOKUP_API = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
BASE = "https://www.courtlistener.com"
CENTRAL = timezone(timedelta(hours=-5))
MAX_CHARS = 64000
PInterval = 1.5  # polite pause between API calls (seconds)

QUOTE_RE = re.compile(r'["\u201c]([^"\u201c\u201d]{20,}?)["\u201d]', re.DOTALL)


def read_draft():
    # Prefer text pasted into the workflow "Run" box (never stored in the repo)
    pasted = os.environ.get("DRAFT_TEXT", "")
    if pasted.strip():
        return "pasted text", pasted
    # Fall back to an uploaded file (useful for very long briefs)
    for name in ("draft_to_check.txt", "draft_to_check.md"):
        if os.path.exists(name):
            with open(name, encoding="utf-8") as f:
                return name, f.read()
    return None, None


def _request(url=None, data=None):
    headers = {
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "pro-se-citation-verifier",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    target = url or LOOKUP_API
    return urllib.request.Request(target, data=data, headers=headers)


def _call(url=None, data=None, retries=5):
    """GET (url) or POST (data) with retry/backoff on HTTP 429."""
    for attempt in range(retries):
        try:
            req = _request(url=url, data=data)
            with urllib.request.urlopen(req, timeout=90) as r:
                time.sleep(PInterval)  # be polite after every successful call
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if (retry_after and retry_after.isdigit()) else (2 ** attempt) * 5
                time.sleep(min(wait, 65))
                continue
            raise


def citation_lookup(text):
    return _call(data=urllib.parse.urlencode({"text": text}).encode())


def strip_html(s):
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return html.unescape(s)


def get_opinion_text(cluster):
    try:
        sub = cluster.get("sub_opinions")
        if not sub and cluster.get("id"):
            detail = _call(url=f"{BASE}/api/rest/v4/clusters/{cluster['id']}/")
            sub = detail.get("sub_opinions")
        if not sub:
            return "", "no sub_opinions found"
        texts = []
        for item in sub[:4]:
            url = item if isinstance(item, str) else (item.get("resource_uri") or item.get("id"))
            if isinstance(url, int):
                url = f"{BASE}/api/rest/v4/opinions/{url}/"
            if isinstance(url, str) and url.startswith("/"):
                url = BASE + url
            if not url:
                continue
            op = _call(url=url)
            for field in ("plain_text", "html_with_citations", "html",
                          "html_lawbox", "html_columbia", "xml_harvard"):
                val = op.get(field)
                if val:
                    texts.append(val if field == "plain_text" else strip_html(val))
                    break
        if not texts:
            return "", "opinion record had no readable text"
        return "\n".join(texts), ""
    except Exception as e:
        return "", f"error fetching opinion: {e}"


def normalize(s):
    s = s.lower()
    s = re.sub(r"[\u201c\u201d\u2018\u2019'`\"\[\]]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def quote_found(quote, opinion_norm):
    segments = re.split(r"\.\.\.|\u2026|\. \. \.", quote)
    segs = [normalize(s) for s in segments]
    segs = [s for s in segs if len(s) >= 15]
    if not segs:
        q = normalize(quote)
        return (q in opinion_norm) if len(q) >= 12 else None
    return all(s in opinion_norm for s in segs)


def write(lines):
    with open("citation_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote citation_report.md")


def main():
    now = datetime.now(CENTRAL)
    out = [
        "# Citation Verification Report",
        f"\n**Generated:** {now.strftime('%A, %B %d, %Y at %I:%M %p')} (Central)\n",
        "> **What the checkmarks mean.** *Citation verified* = the cite resolves to a real "
        "case. *Quote found* = the words appear in the opinion text. Neither confirms the case "
        "supports your argument, nor that a quote is from the majority or used in fair context. "
        "A human must read the case before filing.\n",
        "---\n",
    ]

    if not TOKEN:
        out.append("> ERROR: No CourtListener token. Add COURTLISTENER_TOKEN as a repo secret.")
        write(out)
        return

    fname, text = read_draft()
    if not text:
        out.append("> ERROR: No draft provided. Paste your draft into the workflow "
                   "\"Run\" box, or upload `draft_to_check.txt`, then rerun.")
        write(out)
        return

    out.append(f"**Document checked:** {fname} ({len(text):,} characters)\n")

    chunks = [text[i:i + MAX_CHARS] for i in range(0, len(text), MAX_CHARS)] or [""]
    results = []
    try:
        for ch in chunks:
            results.extend(citation_lookup(ch))
    except Exception as e:
        out.append(f"> ERROR calling CourtListener: {e}")
        write(out)
        return

    verified, notfound, ambiguous = [], [], []
    cite_cluster = {}
    seen = set()
    for item in results:
        cite = item.get("citation", "?")
        status = item.get("status")
        clusters = item.get("clusters") or []
        if cite not in cite_cluster and status == 200 and clusters:
            cite_cluster[cite] = clusters[0]
        if cite in seen:
            continue
        seen.add(cite)
        if status == 200 and clusters:
            c = clusters[0]
            verified.append((cite, c.get("case_name") or "(unnamed)",
                             BASE + (c.get("absolute_url") or "")))
        elif clusters:
            ambiguous.append((cite, "; ".join((c.get("case_name") or "?") for c in clusters[:3])))
        else:
            notfound.append(cite)

    out.append(f"## Citations — Verified: {len(verified)}  |  Not found: {len(notfound)}  |  Ambiguous: {len(ambiguous)}\n")
    out.append("### VERIFIED\n")
    for cite, name, url in verified:
        out.append(f"- **{cite}** — {name}  \n  {url}")
    if not verified:
        out.append("- (none)")
    out.append("\n### NOT FOUND — review before filing\n")
    for cite in notfound:
        out.append(f"- **{cite}** — not in CourtListener. May be misquoted, very recent, "
                   "unpublished, a non-covered reporter, or fabricated.")
    if not notfound:
        out.append("- (none)")
    out.append("\n### AMBIGUOUS\n")
    for cite, names in ambiguous:
        out.append(f"- **{cite}** — multiple matches: {names}")
    if not ambiguous:
        out.append("- (none)")
    out.append("\n---\n")

    out.append("## Quotation Check\n")

    cite_positions = sorted((text.find(c), c) for c in cite_cluster if text.find(c) >= 0)
    quotes = [(m.group(1).strip(), m.start(), m.end()) for m in QUOTE_RE.finditer(text)]
    quotes = [(q, s, e) for (q, s, e) in quotes if len(q.split()) >= 4]

    if not quotes:
        out.append("No quoted passages (in quotation marks) were detected. "
                   "Indented block quotes without quotation marks are not checked in this version.\n")
        write(out)
        return

    op_cache = {}
    checked = 0
    for quote, qs, qe in quotes:
        following = [(pos, c) for (pos, c) in cite_positions if pos >= qe]
        preceding = [(pos, c) for (pos, c) in cite_positions if pos <= qs]
        assoc = following[0][1] if following else (preceding[-1][1] if preceding else None)

        short = (quote[:90] + "\u2026") if len(quote) > 90 else quote
        if assoc is None:
            out.append(f"- \u201c{short}\u201d\n  \u2192 no nearby verified citation to check against.")
            continue

        if assoc not in op_cache:
            op_cache[assoc] = get_opinion_text(cite_cluster[assoc])
        op_text, note = op_cache[assoc]
        case_name = next((n for (c, n, u) in verified if c == assoc), assoc)

        if not op_text:
            out.append(f"- \u201c{short}\u201d\n  \u2192 paired with **{assoc}** ({case_name}); "
                       f"could not fetch opinion text ({note}). Verify manually.")
            continue

        checked += 1
        res = quote_found(quote, normalize(op_text))
        if res is True:
            out.append(f"- \u2705 \u201c{short}\u201d\n  \u2192 FOUND in **{assoc}** ({case_name}).")
        elif res is False:
            out.append(f"- \u274c \u201c{short}\u201d\n  \u2192 NOT FOUND in **{assoc}** ({case_name}). "
                       "Check the wording, or whether the quote belongs to a different case.")
        else:
            out.append(f"- \u26a0\ufe0f \u201c{short}\u201d\n  \u2192 too short to check reliably; verify manually.")

    out.append(f"\n**Quotes checked against opinion text:** {checked} of {len(quotes)} detected.")
    out.append("\nReminder: a found quote may still be from a dissent or used out of context. Read the case.")
    write(out)


if __name__ == "__main__":
    main()
