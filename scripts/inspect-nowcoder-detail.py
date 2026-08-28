import asyncio
from playwright.async_api import async_playwright
URL='https://www.nowcoder.com/jobs/detail/462564?pageSource=5026&channel=jobHomePage&deliverSource=26'
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]; page=await c.new_page()
  try:
   await page.goto(URL,wait_until='domcontentloaded',timeout=30000); await page.wait_for_timeout(2000)
   print('title',await page.title(),'url',page.url)
   text=await page.locator('body').inner_text(); print(text[:5000])
   for s in ['[class*=job]','[class*=detail]','[class*=description]','main','article']:
    print(s,await page.locator(s).count())
  finally: await page.close()
asyncio.run(main())
