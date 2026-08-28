import asyncio
from playwright.async_api import async_playwright

URL = "https://we.51job.com/pc/search?jobArea=010000&keyword=Python&page=1"
async def main():
 async with async_playwright() as p:
  b=await p.chromium.connect_over_cdp('http://127.0.0.1:9223'); c=b.contexts[0]; page=await c.new_page()
  try:
   await page.goto(URL,wait_until='domcontentloaded',timeout=30000); await page.wait_for_timeout(2500)
   print('title',await page.title(),'url',page.url)
   anchors=await page.locator('a').evaluate_all("els=>els.map(a=>({text:(a.innerText||'').trim(),href:a.href})).filter(x=>x.text).slice(0,100)")
   for a in anchors:
    if '大模型' in a['text'] or 'python' in a['text'].lower() or 'jobs.51job.com' in a['href']:
     print(a)
  finally: await page.close()
asyncio.run(main())
