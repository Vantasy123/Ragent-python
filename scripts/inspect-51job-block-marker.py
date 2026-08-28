import asyncio
from playwright.async_api import async_playwright
URL='https://jobs.51job.com/beijing-syq/173377782.html'
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]; page=await c.new_page()
  try:
   await page.goto(URL,wait_until='domcontentloaded',timeout=30000); await page.wait_for_timeout(1500)
   text=await page.locator('body').inner_text()
   for marker in ['验证码','security.min.js','acw_tc','请先登录','立即登录','登录后查看']:
    idx=text.lower().find(marker.lower())
    print(marker,idx, text[max(0,idx-100):idx+180] if idx>=0 else '')
   print('title',await page.title(),'len',len(text))
  finally: await page.close()
asyncio.run(main())
