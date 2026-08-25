import asyncio,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
URL='https://www.nowcoder.com/jobs/detail/462564?pageSource=5026&channel=jobHomePage&deliverSource=26'
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]; page=await c.new_page()
  try:
   await page.goto(URL,wait_until='domcontentloaded',timeout=30000); await page.wait_for_timeout(1200)
   for s in ['main','[class*=detail]','[class*=job-detail]','[class*=content]']:
    print('\n',s,await page.locator(s).count())
    for i in range(min(8,await page.locator(s).count())):
     e=page.locator(s).nth(i); print(i,await e.get_attribute('class'),(await e.inner_text())[:180].replace('\n',' | '))
  finally: await page.close()
asyncio.run(main())
