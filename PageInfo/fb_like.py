import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

class FBLikeScraper:
    def __init__(self, post_url, cookies_path='cookie.json'):
        self.post_url = post_url
        base_dir = Path(__file__).resolve().parent
        self.cookies_path = base_dir / cookies_path

    async def load_cookies(self, context):
        with open(self.cookies_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)

    async def get_likes(self, page):
        likes = []
        try:
            # ✅ Scroll เพื่อให้ปุ่มปรากฏ
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(2000)

            # ✅ คลิกปุ่ม "คุณ และ คนอื่นๆ อีก xxx คน"
            btn_people = page.locator('span:has-text("คนอื่นๆ อีก")')
            if await btn_people.count():
                await btn_people.first.scroll_into_view_if_needed(timeout=5000)
                await btn_people.first.click(timeout=10000, force=True)
                await page.wait_for_timeout(3000)

                # ✅ ระบุ popup container
                popup = page.locator('div[role="dialog"]:has-text("เพิ่มเพื่อน")')
                await popup.wait_for(timeout=5000)

                # ✅ คลิกตรงกลาง container 1 ครั้งเพื่อ focus
                box = await popup.bounding_box()
                if box:
                    x = box["x"] + box["width"]/2
                    y = box["y"] + box["height"]/2
                    await page.mouse.click(x, y)
                    await page.wait_for_timeout(1000)

                seen_names = set()
                retries = 0
                max_retries = 5

                while True:
                    # ✅ ดึงชื่อใน popup
                    name_elements = popup.locator('a.x1i10hfl.xjbqb8w.x1ejq31n')
                    count = await name_elements.count()
                    for i in range(count):
                        el = name_elements.nth(i)
                        name = (await el.inner_text()).strip()
                        if name:
                            seen_names.add(name)

                    prev_count = len(seen_names)

                    # ✅ Scroll ภายใน popup ลงด้วย mouse.wheel ตำแหน่ง popup
                    box = await popup.bounding_box()
                    if box:
                        x = box["x"] + box["width"]/2
                        y = box["y"] + box["height"]/2
                        await page.mouse.move(x, y)
                        await page.mouse.wheel(0, 3000)
                        await page.wait_for_timeout(1500)

                    # ✅ ตรวจสอบว่ามีชื่อใหม่เพิ่มหรือไม่
                    name_elements = popup.locator('a.x1i10hfl.xjbqb8w.x1ejq31n')
                    count = await name_elements.count()
                    for i in range(count):
                        el = name_elements.nth(i)
                        name = (await el.inner_text()).strip()
                        if name:
                            seen_names.add(name)

                    new_count = len(seen_names)

                    if new_count == prev_count:
                        retries += 1
                    else:
                        retries = 0

                    if retries >= max_retries:
                        break


                likes.extend(list(seen_names))

                # ✅ ปิด popup
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(1000)

            print(f"✅ ดึงรายชื่อไลค์สำเร็จ: {len(likes)} คน")

        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาด get_likes: {e}")

        return likes

    async def start(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            await self.load_cookies(context)
            page = await context.new_page()
            await page.goto(self.post_url, timeout=60000)
            await page.wait_for_timeout(5000)

            # ✅ เรียกฟังก์ชันดึง likes
            likes = await self.get_likes(page)

            await browser.close()
            return likes

async def run_fb_like_scraper(post_url):
    scraper = FBLikeScraper(post_url)
    return await scraper.start()

if __name__ == "__main__":
    url = "https://www.facebook.com/photo/?fbid=122186666168274942&set=a.122113064870274942"
    results = asyncio.run(run_fb_like_scraper(url))
    print(json.dumps(results, ensure_ascii=False, indent=2))
