"""
LASC Docket Checker — Cloud version (production, correct selectors)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

CASES = [
    {"number": "24STCV08032", "name": "Doi Case"},
    {"number": "24STCV05152", "name": "Scenic Case"},
    {"number": "24STCV10654", "name": "Jan's Towing Case"},
    {"number": "25STCV06166", "name": "Tesoro Case"},
]

BASE_URL = "https://lacourt.ca.gov/casesummary/v2web3/?casetype=civil"
COURTHOUSE = "Stanley Mosk Courthouse"
CENTRAL = timezone(timedelta(hours=-5))


async def attempt(page, case_number):
    await page.goto(BASE_URL, wait_until="networkidle", timeout=45000)
    await page.wait_for_selector("#txtCaseNumber", timeout=20000)
    await page.wait_for_timeout(3000)

    await page.fill("#txtCaseNumber", case_number)
    await page.wait_for_timeout(600)

    try:
        await page.select_option("#ddlCourthouse", label=COURTHOUSE)
        await page.wait_for_timeout(400)
    except Exception:
        pass

    try:
        async with page.expect_navigation(wait_until="networkidle", timeout=30000):
            await page.click("#submit1")
    except PlaywrightTimeoutError:
        await page.wait_for_timeout(5000)

    await page.wait_for_timeout(3000)

    text = await page.evaluate("() => document.body.innerText")
    success = "an exception occurred" not in text.lower()
    return success, text


def clean(text):
    lines = [l.strip() for l in text.split("\n")]
    lines = [l for l in lines if l and len(l) > 2]
    skip_phrases = [
        "google", "translate", "disclaimer", "official language",
        "copyright", "privacy statement", "loading, please wait",
        "language access", "espanol", "español", "tiếng việt", "한국어", "中文", "հայերեն",
        "attorney portal", "select a courthouse", "landlord tenant",
        "limited jurisdiction", "general jurisdiction", "this site includes",
        "view important information", "does not constitute", "is being provided",
        "not liable", "case-by-case",
    ]
    return [l for l in lines if not any(p in l.lower() for p in skip_phrases)]


async def scrape_case(page, case_number, case_name):
    print(f"Checking {case_name} ({case_number})...")
    out = [f"## {case_name} — {case_number}\n"]
    try:
        success, text = await attempt(page, case_number)
        if not success:
            print("  exception - retrying...")
            await page.wait_for_timeout(2000)
            success, text = await attempt(page, case_number)

        filtered = clean(text)

        if not success:
            out.append("> WARNING: LASC returned 'An exception occurred' even after retry. "
                       "Site may be down or blocking automation. Check manually at lacourt.ca.gov.\n")
        elif filtered:
            out.append("```")
            out.extend(filtered)
            out.append("```\n")
        else:
            out.append("> WARNING: Submitted but no readable case data returned. Verify the case number.\n")
    except Exception as e:
        out.append(f"> ERROR: {e}\n")
    return "\n".join(out)


async def main():
    now = datetime.now(CENTRAL)
    report = [
        "# LASC Active Case Docket Report",
        f"\n**Generated:** {now.strftime('%A, %B %d, %Y at %I:%M %p')} (Central, approx)",
        "\n**Ryan Levihn-Coon - Pro Per Plaintiff**\n",
        "> Always verify dates against the official record. Automated scrape; may contain errors.\n",
        "---\n",
    ]

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
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        for case in CASES:
            report.append(await scrape_case(page, case["number"], case["name"]))
            report.append("---\n")
        await browser.close()

    with open("docket_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("Report written to docket_report.md")


if __name__ == "__main__":
    asyncio.run(main())
