import asyncio,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from app.services.crawlers.dom_extractors import DOMExtractors
from app.services.job_crawler_service import PlatformCityMapper
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]
  for platform in ['boss','liepin']:
   page=await c.new_page(); url=DOMExtractors.get_search_url(platform,'Python',PlatformCityMapper.get_code(platform,'北京'),'social',1)
   try:
    print('NAV',platform,url)
    r=await page.goto(url,wait_until='commit',timeout=30000)
    print('RESPONSE',r.status if r else None,'URL',page.url)
    await page.wait_for_timeout(8000)
    print('TITLE',await page.title(),'URL',page.url)
    print((await page.locator('body').inner_text())[:3000])
   except Exception as e: print('ERR',repr(e),'URL',page.url)
   finally: await page.close()
asyncio.run(main())
