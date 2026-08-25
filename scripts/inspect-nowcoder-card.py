import asyncio, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from app.services.crawlers.dom_extractors import DOMExtractors
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]
  page=await c.new_page(); await page.goto(DOMExtractors.get_search_url('nowcoder','Python','0','social',1),wait_until='domcontentloaded'); await page.wait_for_timeout(2000)
  cards=page.locator('[class*=job-card]'); print('count',await cards.count())
  if await cards.count(): print((await cards.first.evaluate('e=>e.outerHTML'))[:8000])
  await page.close()
asyncio.run(main())
