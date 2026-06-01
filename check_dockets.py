"""
LASC Page Structure Diagnostic
One-time diagnostic. Maps every input, button, and select on the LASC page
so we can find the correct selectors. Outputs to docket_report.md.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

BASE_URL = "https://lacourt.ca.gov/casesummary/v2web3/?casetype=civil"
CENTRAL = timezone(timedelta(hours=-5))
TEST_CASE = "24STCV08032"


async def main():
    now = datetime.now(CENTRAL)
    report = []
    report.append("# LASC PAGE DIAGNOSTIC")
    report.append(f"\n**Generated:** {now.strftime('%A, %B %d, %Y at %I:%M %p')}\n")
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

        report.append("## STAGE 1 — Initial page (before any input)\n")
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            report.append(f"> Load note: {e}\n")
            await page.wait_for_timeout(3000)

        async def dump_structure():
            return await page.evaluate("""() => {
                const r = { title: document.title, url: location.href,
                            inputs: [], buttons: [], selects: [], clickables: [] };
                document.querySelectorAll('input').forEach((el, i) => {
                    r.inputs.push(`[${i}] id="${el.id}" name="${el.name}" type="${el.type}" placeholder="${el.placeholder}" aria="${el.getAttribute('aria-label')||''}" class="${el.className}" visible=${el.offsetParent!==null}`);
                });
                document.querySelectorAll('button').forEach((el, i) => {
                    r.buttons.push(`[${i}] text="${(el.innerText||'').trim()}" type="${el.type}" id="${el.id}" aria="${el.getAttribute('aria-label')||''}" class="${el.className}" visible=${el.offsetParent!==null}`);
                });
                document.querySelectorAll('select').forEach((el, i) => {
                    r.selects.push(`[${i}] id="${el.id}" name="${el.name}" class="${el.className}"`);
                });
                document.querySelectorAll('a[role=button], [role=button], i[class*=search], span[class*=search], .btn').forEach((el, i) => {
                    r.clickables.push(`[${i}] tag=${el.tagName} text="${(el.innerText||'').trim()}" class="${el.className}"`);
                });
                return r;
            }""")

        s1 = await dump_structure()
        report.append(f"**Title:** {s1['title']}")
        report.append(f"**URL:** {s1['url']}\n")
        report.append(f"**INPUTS ({len(s1['inputs'])}):**\n```")
        report.extend(s1["inputs"] if s1["inputs"] else ["(none found)"])
        report.append("```\n")
        report.append(f"**BUTTONS ({len(s1['buttons'])}):**\n```")
        report.extend(s1["buttons"] if s1["buttons"] else ["(none found)"])
        report.append("```\n")
        report.append(f"**SELECTS ({len(s1['selects'])}):**\n```")
        report.extend(s1["selects"] if s1["selects"] else ["(none found)"])
        report.append("```\n")
        report.append(f"**OTHER CLICKABLES ({len(s1['clickables'])}):**\n```")
        report.extend(s1["clickables"] if s1["clickables"] else ["(none found)"])
        report.append("```\n")
        report.append("---\n")

        report.append("## STAGE 2 — After typing case number into best-guess field\n")
        try:
            filled_info = await page.evaluate("""(caseNum) => {
                const inputs = [...document.querySelectorAll('input')].filter(
                    el => el.offsetParent !== null &&
                    (el.type === 'text' || el.type === '' || !el.type)
                );
                if (inputs.length === 0) return 'NO VISIBLE TEXT INPUT';
                const target = inputs[0];
                target.focus();
                target.value = caseNum;
                target.dispatchEvent(new Event('input', {bubbles:true}));
                target.dispatchEvent(new Event('change', {bubbles:true}));
                return `Filled input: id="${target.id}" name="${target.name}" class="${target.className}"`;
            }""", TEST_CASE)
            report.append(f"> {filled_info}\n")
            await page.wait_for_timeout(1000)

            await page.keyboard.press("Enter")
            await page.wait_for_timeout(5000)

            s2 = await dump_structure()
            report.append(f"**URL after submit:** {s2['url']}\n")

            body = await page.evaluate("""() => {
                return document.body.innerText.substring(0, 3000);
            }""")
            report.append("**VISIBLE TEXT AFTER SUBMIT (first 3000 chars):**\n```")
            report.append(body)
            report.append("```\n")
        except Exception as e:
            report.append(f"> Stage 2 error: {e}\n")

        await browser.close()

    with open("docket_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("Diagnostic written to docket_report.md")


if __name__ == "__main__":
    asyncio.run(main())
