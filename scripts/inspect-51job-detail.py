import asyncio
from playwright.async_api import async_playwright

URL = "https://jobs.51job.com/all/coA2BQN1M0AzoAYARiAmU.html"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            print("TITLE", await page.title())
            print("URL", page.url)
            print((await page.locator("body").inner_text())[:8000])
            for selector in [".job_msg", ".job_msg .tmsg", ".job_detail", ".job-detail", ".job_detail_list", ".tCompany_job", "[class*=job-detail]", "[class*=job_msg]"]:
                print("SELECTOR", selector, "COUNT", await page.locator(selector).count())
        finally:
            await page.close()

asyncio.run(main())
