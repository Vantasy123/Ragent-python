import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]; page=await c.new_page()
  try:
   await page.goto('https://www.zhipin.com/',wait_until='commit',timeout=30000); await page.wait_for_timeout(5000)
   print('bodylen',len(await page.locator('body').inner_text()))
   print('inputs',await page.locator('input').count(),'textareas',await page.locator('textarea').count())
   print('links', (await page.locator('a').evaluate_all("els=>els.map(a=>({t:(a.innerText||'').trim(),h:a.href})).filter(x=>x.t).slice(0,50)")))
   print('html', (await page.locator('body').inner_text())[:2000])
  finally: await page.close()
asyncio.run(main())
