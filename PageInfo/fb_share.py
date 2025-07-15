import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright

class FBShareScraper:
    def __init__(self, post_url, cookies_path='cookie.json'):
        self.post_url = post_url
        base_dir = Path(__file__).resolve().parent
        self.cookies_path = base_dir / cookies_path

    async def load_cookies(self, context):
        with open(self.cookies_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)

    async def get_shares(self, page):
        shares = []
        try:
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(2000)

            # ✅ คลิกปุ่มแชร์
            btn_share = page.locator('//div[@role="button"]//i[contains(@style,"background-position: 0px -1218px")]')
            if await btn_share.count() > 0:
                btn = btn_share.first
                await btn.scroll_into_view_if_needed(timeout=5000)
                await btn.click(timeout=10000, force=True)
                await page.wait_for_timeout(4000)
                print("✅ คลิกปุ่มแชร์แล้ว")

                # ✅ popup container
                popup = page.locator('div[role="dialog"][aria-label="คนที่แชร์ลิงก์นี้"]')
                await popup.wait_for(timeout=15000)

                # ✅ focus popup
                box = await popup.bounding_box()
                if box:
                    x = box["x"] + box["width"]/2
                    y = box["y"] + box["height"]/2
                    await page.mouse.click(x, y)
                    await page.wait_for_timeout(1500)

                seen_names = set()
                previous_count = -1
                same_count_times = 0
                scroll_num = 0

                while True:
                    scroll_num += 1

                    # ✅ ดึงชื่อทั้งหมด
                    name_elements = popup.locator('a[role="link"] span')
                    count = await name_elements.count()

                    for i in range(count):
                        el = name_elements.nth(i)
                        name = (await el.inner_text()).strip()

                        # ✅ filter เฉพาะชื่อจริง
                        if not name:
                            continue
                        if name.startswith("#"):
                            continue
                        if "น." in name:
                            continue
                        if re.search(r"\d", name) and len(name) <= 10:
                            continue
                        if name == "·":
                            continue

                        seen_names.add(name)

                    print(f"🔄 Scroll #{scroll_num} - Total names collected: {len(seen_names)}")

                    # ✅ ตรวจสอบถ้าไม่มีชื่อใหม่เพิ่ม 10 รอบติด ให้หยุด (จากเดิม 5 รอบ)
                    if len(seen_names) == previous_count:
                        same_count_times += 1
                        print(f"⚠️ ไม่มีชื่อใหม่เพิ่ม รอบที่ {same_count_times}")
                        if same_count_times >= 10:
                            print("✅ ไม่มีชื่อใหม่เพิ่ม 10 รอบ หยุดเลื่อน")
                            break
                    else:
                        same_count_times = 0  # reset

                    previous_count = len(seen_names)

                    # ✅ Scroll ภายใน popup แบบ human-like lazyload (ไม่เลื่อนสุด)
                    box = await popup.bounding_box()
                    if box:
                        x = box["x"] + box["width"]/2
                        y = box["y"] + box["height"]/2
                        await page.mouse.move(x, y)
                        await page.mouse.wheel(0, 100)  # เลื่อนทีละ 100px
                        await page.wait_for_timeout(2500)  # รอ 2.5s

                shares.extend(list(seen_names))

                # ✅ close popup
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(1000)

            else:
                print("❌ ไม่พบปุ่มแชร์ในโพสต์นี้")

            print(f"✅ ดึงรายชื่อแชร์สำเร็จ: {len(shares)} คน")

        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาด get_shares: {e}")

        return shares

    async def start(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            await self.load_cookies(context)
            page = await context.new_page()
            await page.goto(self.post_url, timeout=60000)
            await page.wait_for_timeout(5000)

            shares = await self.get_shares(page)

            await browser.close()
            return shares

async def run_fb_share_scraper(post_url):
    scraper = FBShareScraper(post_url)
    return await scraper.start()

if __name__ == "__main__":
    url = "https://www.facebook.com/photo/?fbid=122186666168274942&set=a.122113064870274942"
    results = asyncio.run(run_fb_share_scraper(url))
    print(json.dumps(results, ensure_ascii=False, indent=2))
