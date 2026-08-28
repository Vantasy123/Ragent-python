import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from app.services.crawlers.dom_extractors import DOMExtractors
from app.services.job_crawler_service import PlatformCityMapper

async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]
  for platform,url in [('liepin',DOMExtractors.get_search_url('liepin','Python',PlatformCityMapper.get_code('liepin','北京'),'social',1)),('boss',DOMExtractors.get_search_url('boss','Python',PlatformCityMapper.get_code('boss','北京'),'social',1)),('nowcoder',DOMExtractors.get_search_url('nowcoder','Python','0','social',1))]:
   page=await c.new_page()
   try:
    await page.goto(url,wait_until='domcontentloaded',timeout=30000); await page.wait_for_timeout(2500)
    print('\nPLATFORM',platform,'TITLE',await page.title(),'URL',page.url)
    print((await page.locator('body').inner_text())[:1200])
    for sel in ['.job-card-pc-container','.job-card-wrapper','.job-list-box','[class*=job-card]','[class*=job-item]','[class*=job-list]']:
     print(sel,await page.locator(sel).count())
   finally: await page.close()
asyncio.run(main())
