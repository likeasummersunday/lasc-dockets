"""
Citation Verifier — checks every legal citation in a draft against CourtListener.
Reads draft_to_check.txt (or .md) from the repo, queries CourtListener's
Citation Lookup API, and writes citation_report.md.

VERIFIED means the citation resolves to a real case in CourtListener.
It does NOT mean the proposition it was cited for is accurate. Always read the case.
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("COURTLISTENER_TOKEN", "").strip()
API = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
CENTRAL = timezone(timedelta(hours=-5))
MAX_CHARS = 64000  # API limit per request


def read_draft():
    for name in ("draft_to_check.txt", "draft_to_check.md"):
        if os.path.exists(name):
            with open(name, encoding="utf-8") as f:
                return name, f.read()
    return None, None


def call_api(text):
    data = urllib.parse.urlencode({"text": text}).encode()
    req = urllib.request.Request(
        API, data=data,
        headers={
            "Authorization": f"Token {TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "pro-se-citation-verifier",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def write(lines):
    with open("citation_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote citation_report.md")


def main():
    now = datetime.now(CENTRAL)
    out = [
        "# Citation Verification Report",
        f"\n**Generated:** {now.strftime('%A, %B %d, %Y at %I:%M %p')} (Central)\n",
        "> VERIFIED = the citation resolves to a real case in CourtListener. "
        "It does NOT confirm the case says what the draft claims. Always read the case before filing.\n",
        "---\n",
    ]

    if not TOKEN:
        out.append("> ERROR: No CourtListener token found. "
                   "Add COURTLISTENER_TOKEN as a repository secret.")
        write(out)
        return

    fname, text = read_draft()
    if not text:
        out.append("> ERROR: No draft found. Upload your document as "
                   "`draft_to_check.txt` (or `.md`) to the repo, then run this again.")
        write(out)
        return

    out.append(f"**Document checked:** {fname} ({len(text):,} characters)\n")

    # Chunk if the document exceeds the API limit
    chunks = [text[i:i + MAX_CHARS] for i in range(0, len(text), MAX_CHARS)] or [""]
    results = []
    try:
        for ch in chunks:
            results.extend(call_api(ch))
    except Exception as e:
        out.append(f"> ERROR calling CourtListener: {e}\n"
                   "> Check that your token is valid and try again.")
        write(out)
        return

    if not results:
        out.append("No legal citations were detected in the document.")
        write(out)
        return

    verified, notfound, ambiguous = [], [], []
    seen = set()
    for item in results:
        cite = item.get("citation", "?")
        if cite in seen:
            continue
        seen.add(cite)
        status = item.get("status")
        clusters = item.get("clusters") or []
        if status == 200 and clusters:
            c = clusters[0]
            name = c.get("case_name") or "(unnamed case)"
            url = "https://www.courtlistener.com" + (c.get("absolute_url") or "")
            verified.append((cite, name, url))
        elif clusters and status != 200:
            names = "; ".join((c.get("case_name") or "?") for c in clusters[:3])
            ambiguous.append((cite, names))
        else:
            notfound.append(cite)

    out.append(f"## VERIFIED — {len(verified)}\n")
    for cite, name, url in verified:
        out.append(f"- **{cite}** — {name}  ")
        out.append(f"  {url}")
    if not verified:
        out.append("- (none)")
    out.append("")

    out.append(f"## NOT FOUND — review before filing — {len(notfound)}\n")
    if notfound:
        for cite in notfound:
            out.append(f"- **{cite}** — not found in CourtListener. "
                       "Verify manually: may be misquoted, very recent, unpublished, "
                       "a non-CourtListener reporter, or fabricated.")
    else:
        out.append("- (none)")
    out.append("")

    out.append(f"## AMBIGUOUS / multiple matches — {len(ambiguous)}\n")
    if ambiguous:
        for cite, names in ambiguous:
            out.append(f"- **{cite}** — multiple possible matches: {names}")
    else:
        out.append("- (none)")
    out.append("")

    out.append("---\n")
    out.append(f"**Summary:** {len(verified)} verified, "
               f"{len(notfound)} not found, {len(ambiguous)} ambiguous. "
               "Read every case before relying on it.")

    write(out)


if __name__ == "__main__":
    main()
