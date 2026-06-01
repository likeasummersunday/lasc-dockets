"""
LASC Docket Checker — Cloud version (with readability cleanup)
Official entry URL sets up the session; handles main page or sub-frame;
strips navigation menus and boilerplate while preserving all substantive rows.
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

ENTRY_URL = ("https://www.lacourt.ca.gov/pages/lp/access-a-case/"
             "tp/find-case-information/cp/os-civil-case-access")
CENTRAL = timezone(timedelta(hours=-5))

SKIP = [
    "google", "translate", "disclaimer", "official language",
    "copyright", "privacy statement", "loading, please wait",
    "language access", "espanol", "espa\u00f1ol", "ti\u1ebfng vi\u1ec7t",
    "\ud55c\uad6d\uc5b4", "\u4e2d\u6587", "\u0570\u0561\u0575\u0565\u0580\u0565\u0576",
    "attorney portal", "select a courthouse", "landlord tenant",
    "limited jurisdiction", "general jurisdiction", "this site includes",
    "view important information", "does not constitute", "is being provided",
    "not liable", "case-by-case", "you may also use", "click here to access",
    "if this link fails",
]


async def find_form_frame(page):
    for _ in range(8):
        for fr in page.frames:
            try:
                if await fr.query_selector("#txtCaseNumber"):
                    return fr
            except Exception:
                continue
        await page.wait_for_timeout(2000)
    return None


async def longest_frame_text(page):
    best = ""
    for fr in page.frames:
        try:
            t = await fr.evaluate("() => document.body.innerText")
            if t and len(t) > len(best):
                best = t
        except Exception:
            continue
    return best


def clean(text):
    out = []
    for raw in text.split("\n"):
        l = raw.strip()
        if not l or len(l) < 3:
            continue
        low = l.lower()
        if low == "english":
            continue
        # drop the repeated pipe-delimited navigation menu lines
        if l.count("|") >= 3:
            continue
        if any(p in low for p in SKIP):
            continue
        out.append(l)
    return out


async def scrape_case(page, case_number, case_name):
    print(f"Checking {case_name} ({case_number})...")
    out = [f"## {case_name} \u2014 {case_number}\n"]
    try:
        await page.goto(ENTRY_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)

        frame = await find_form_frame(page)
        if frame is None:
            body = await longest_frame_text(page)
            out.append("> WARNING: Could not find the case-number field. First 800 chars:\n")
            out.append("```\n" + body[:800] + "\n```\n")
            return "\n".join(out)

        await frame.fill("#txtCaseNumber", case_number)
        await page.wait_for_timeout(800)

        btn = await frame.query_selector("#submit1")
        if btn:
            await btn.click()
        else:
            await frame.press("#txtCaseNumber", "Enter")

        await page.wait_for_timeout(7000)
        text = await longest_frame_text(page)

        if "an exception occurred" in text.lower():
            out.append("> WARNING: LASC returned 'An exception occurred'. First 800 chars:\n")
            out.append("```\n" + text[:800] + "\n```\n")
        else:
            filtered = clean(text)
            if filtered:
                out.append("```")
                out.extend(filtered)
                out.append("```\n")
            else:
                out.append("> WARNING: No readable case data. First 800 chars:\n")
                out.append("```\n" + text[:800] + "\n```\n")
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
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = await ctx.new_page()
        for case in CASES:
            report.append(await scrape_case(page, case["number"], case["name"]))
            report.append("---\n")
        await browser.close()

    with open("docket_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("Report written to docket_report.md")


if __name__ == "__main__":
    asyncio.run(main())
