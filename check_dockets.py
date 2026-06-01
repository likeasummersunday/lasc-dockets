"""
LASC Entry-Page Structure Diagnostic (v2)
"""
import asyncio
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

ENTRY_URL = "https://www.lacourt.ca.gov/pages/lp/access-a-case/tp/find-case-information/cp/os-civil-case-access"
CENTRAL = timezone(timedelta(hours=-5))
TEST_CASE = "24STCV08032"


async def main():
    now = datetime.now(CENTRAL)
    rep = ["# LASC ENTRY-PAGE DIAGNOSTIC v2",
           f"\n**Generated:** {now.strftime('%A, %B %d, %Y at %I:%M %p')}\n", "---\n"]

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

        try:
            await page.goto(ENTRY_URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            rep.append(f"> load note: {e
