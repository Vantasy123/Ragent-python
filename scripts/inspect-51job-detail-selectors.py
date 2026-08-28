import asyncio
from playwright.async_api import async_playwright
URL='https://jobs.51job.com/beijing-syq/173377782.html'
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]; page=await c.new_page()
  try:
   await page.goto(URL,wait_until='domcontentloaded',timeout=30000); await page.wait_for_timeout(1500)
   for s in ['[class*=job]','[class*=detail]','[class*=tCompany]','main','article']:
    print(s, await page.locator(s).count())
   for i in range(min(20,await page.locator('[class*=job]').count())):
    el=page.locator('[class*=job]').nth(i)
    print(i, await el.get_attribute('class'), (await el.inner_text())[:300])
  finally: await page.close()
asyncio.run(main())
