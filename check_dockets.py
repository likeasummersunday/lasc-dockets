"""
LASC Docket Checker — Cloud (GitHub Actions) version
Runs on GitHub's servers. Outputs a markdown report viewable in the GitHub app.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ── CASE LIST ─────────────────────────────────────────────────────────────────
CASES = [
    {"number": "24STCV08032", "name": "Doi Case"},
    {"number": "24STCV05152", "name": "Scenic Case"},
    {"number": "24STCV10654", "name": "Jan's Towing Case"},
    {"number": "25STCV06166", "name": "Tesoro Case"},
]

BASE_URL = "https://lacourt.ca.gov/casesummary/v2web3/?casetype=civil"

# Central Time (Austin). Handles approximate DST by using fixed offset note.
CENTRAL = timezone(timedelta(hours=-5))  # CDT; report notes timezone


async def scrape_case(page, case_number, case_name):
    print(f"Checking {case_name} ({case_number})...")
    out = []
    out.append(f"## {case_name} — {case_number}\n")

    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        input_selectors = [
            "input#caseNumber",
            "input[name='caseNumber']",
            "input[placeholder*='case' i]",
            "input[placeholder*='number' i]",
            "input[type='text']",
            "input",
        ]
        case_input = None
        for selector in input_selectors:
            try:
                el = await page.wait_for_selector(selector, timeout=3000)
                if el:
                    case_input = el
                    break
            except PlaywrightTimeoutError:
                continue

        if not case_input:
            out.append("> ⚠️ Could not find case number input field on page.\n")
            return "\n".join(out)

        await case_input.triple_click()
        await case_input.type(case_number, delay=80)
        await page.wait_for_timeout(500)

        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Search')",
            "button:has-text('Go')",
            "button:has-text('Find')",
            "a:has-text('Search')",
        ]
        submitted = False
        for selector in submit_selectors:
            try:
                btn = await page.wait_for_selector(selector, timeout=2000)
                if btn:
                    await btn.click()
                    submitted = True
                    break
            except PlaywrightTimeoutError:
                continue
        if not submitted:
            await case_input.press("Enter")

        await page.wait_for_timeout(4000)

        result_selectors = [
            ".case-summary", "#caseSummary", ".hearing", "#hearings",
            "table", ".case-info", ".result",
            "[class*='case']", "[class*='hearing']", "[id*='case']",
        ]
        for selector in result_selectors:
            try:
                await page.wait_for_selector(selector, timeout=5000)
                break
            except PlaywrightTimeoutError:
                continue

        body_text = await page.evaluate("""() => {
            const skipClasses = ['nav', 'footer', 'disclaimer', 'translate', 'language'];
            function getCleanText(el) {
                let text = '';
                for (const node of el.childNodes) {
                    if (node.nodeType === 3) {
                        text += node.textContent;
                    } else if (node.nodeType === 1) {
                        const tag = node.tagName.toLowerCase();
                        const cls = (node.className || '').toLowerCase();
                        const id = (node.id || '').toLowerCase();
                        const skip = skipClasses.some(s => cls.includes(s) || id.includes(s));
                        if (!skip && !['script','style','noscript'].includes(tag)) {
                            text += getCleanText(node);
                            if (['p','div','tr','li','h1','h2','h3','h4','td','th'].includes(tag)) {
                                text += '\\n';
                            }
                        }
                    }
                }
                return text;
            }
            return getCleanText(document.body);
        }""")

        lines = [line.strip() for line in body_text.split("\n")]
        lines = [l for l in lines if l and len(l) > 2]
        skip_phrases = [
            "google", "translate", "disclaimer", "official language",
            "copyright", "privacy statement", "loading, please wait",
            "language access", "español", "tiếng việt", "한국어",
            "attorney portal", "select a courthouse",
        ]
        filtered = [l for l in lines if not any(p in l.lower() for p in skip_phrases)]

        if filtered:
            out.append("```")
            out.extend(filtered)
            out.append("```\n")
        else:
            out.append("> ⚠️ Page loaded but no case data found. Case number may be invalid or page layout changed.\n")

    except Exception as e:
        out.append(f"> ❌ Error: {e}\n")

    return "\n".join(out)


async def main():
    now = datetime.now(CENTRAL)
    report = []
    report.append("# LASC Active Case Docket Report")
    report.append(f"\n**Generated:** {now.strftime('%A, %B %d, %Y at %I:%M %p')} (Central, approx)")
    report.append("\n**Ryan Levihn-Coon — Pro Per Plaintiff**\n")
    report.append("> ⚠️ Always verify dates against the official record. This is an automated scrape and may contain errors.\n")
    report.append("---\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        for case in CASES:
            report.append(await scrape_case(page, case["number"], case["name"]))
            report.append("---\n")
        await browser.close()

    with open("docket_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print("\nReport written to docket_report.md")


if __name__ == "__main__":
    asyncio.run(main())
