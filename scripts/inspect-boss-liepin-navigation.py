import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]
  for url in ['https://www.zhipin.com/','https://www.liepin.com/','https://www.zhipin.com/web/geek/job','https://www.liepin.com/zhaopin/']:
   page=await c.new_page()
   try:
    r=await page.goto(url,wait_until='commit',timeout=30000)
    await page.wait_for_timeout(5000)
    print(url,'response=',r.status if r else None,'url=',page.url,'title=',await page.title(),'body=',(await page.locator('body').inner_text())[:200].replace('\n',' | '))
   except Exception as e: print(url,'ERROR',repr(e),'url=',page.url)
   finally: await page.close()
asyncio.run(main())
