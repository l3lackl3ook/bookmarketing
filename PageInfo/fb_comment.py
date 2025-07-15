import asyncio
import json
import uuid
from pathlib import Path
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class FBCommentScraper:
    def __init__(self, post_url, cookies_path='cookie.json'):
        self.post_url = post_url
        base_dir = Path(__file__).resolve().parent
        self.cookies_path = base_dir / cookies_path
        self.media_dir = base_dir.parent / 'media' / 'post_screenshots'
        self.media_dir.mkdir(parents=True, exist_ok=True)

    async def load_cookies(self, context):
        with open(self.cookies_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)

    async def click_sort_by_newest(self, page):
        try:
            await page.wait_for_timeout(2000)
            btn_related = page.locator('//span[contains(text(),"เกี่ยวข้องมากที่สุด")]')
            if await btn_related.count() > 0:
                await btn_related.first.click(timeout=15000, force=True)
                await page.wait_for_timeout(1500)
                print("✅ Clicked 'เกี่ยวข้องมากที่สุด'")
            btn_newest = page.locator('//span[contains(text(),"ใหม่ล่าสุด")]')
            if await btn_newest.count() > 0:
                await btn_newest.first.click(timeout=15000, force=True)
                await page.wait_for_timeout(2000)
                print("✅ Clicked 'ใหม่ล่าสุด'")
        except Exception as e:
            print(f"❌ Failed to click 'ใหม่ล่าสุด': {e}")

    async def click_all_buttons(self, page, xpath, desc):
        buttons = await page.locator(xpath).all()
        new_clicks = 0
        for btn in buttons:
            try:
                await btn.scroll_into_view_if_needed(timeout=3000)
                if await btn.is_visible() and await btn.is_enabled():
                    await btn.click(timeout=3000)
                    await page.wait_for_timeout(500)
                    new_clicks += 1
            except Exception as e:
                print(f"⚠️ Failed clicking {desc}: {e}")
        print(f"✅ Clicked {desc}: {new_clicks}")
        return new_clicks

    async def expand_all_see_more(self, page):
        # ✅ กดดูเพิ่มเติมแบบ span
        buttons1 = await page.locator('//span[contains(text(),"ดูเพิ่มเติม")]').all()
        expanded1 = 0
        for btn in buttons1:
            try:
                await btn.scroll_into_view_if_needed(timeout=3000)
                if await btn.is_visible() and await btn.is_enabled():
                    await btn.click(timeout=3000)
                    await page.wait_for_timeout(300)
                    expanded1 += 1
            except:
                continue

        # ✅ กดดูเพิ่มเติมแบบ div role="button"
        buttons2 = await page.locator('//div[@role="button" and contains(text(),"ดูเพิ่มเติม")]').all()
        expanded2 = 0
        for btn in buttons2:
            try:
                await btn.scroll_into_view_if_needed(timeout=3000)
                if await btn.is_visible() and await btn.is_enabled():
                    await btn.click(timeout=3000)
                    await page.wait_for_timeout(300)
                    expanded2 += 1
            except:
                continue

        print(f"✅ Expanded see more span: {expanded1} | div button: {expanded2}")
        return expanded1 + expanded2

    async def scroll_until_fully_loaded(self, page):
        await self.click_sort_by_newest(page)
        round_num = 0
        while True:
            round_num += 1
            print(f"🔁 Scroll round {round_num}")

            expanded = await self.expand_all_see_more(page)

            clicks_see_more_comments = await self.click_all_buttons(page, '//span[contains(text(),"ดูความคิดเห็นเพิ่มเติม")]', "ดูความคิดเห็นเพิ่มเติม")
            clicks_replies = await self.click_all_buttons(page, '//span[contains(text(),"ดู") and contains(text(),"ตอบกลับ")]', "ดูตอบกลับ")
            clicks_all_replies = await self.click_all_buttons(page, '//span[contains(text(),"ดูการตอบกลับทั้งหมด") or contains(text(),"ดูการตอบกลับเพิ่มเติม")]', "ดูการตอบกลับทั้งหมด")

            total_clicks = expanded + clicks_see_more_comments + clicks_replies + clicks_all_replies

            blocks = await page.locator('div[role="article"][aria-label]').all()
            print(f"🔢 Loaded comments so far: {len(blocks)} | Total new clicks this round: {total_clicks}")

            if total_clicks == 0:
                print("✅ No more buttons to click, loading completed.")
                break

            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(1000)

    async def get_hover_timestamp(self, time_el, page):
        try:
            await time_el.hover()
            await page.wait_for_selector('div[role="tooltip"]', timeout=2000)
            tooltip = page.locator('div[role="tooltip"]').first
            if await tooltip.count():
                return (await tooltip.inner_text()).strip()
        except Exception as e:
            print(f"❌ Hover timestamp fail: {e}")
        return None

    async def capture_post_screenshot(self, page):
        try:
            await page.wait_for_timeout(2000)  # รอให้โหลดเนื้อหาเสร็จ
            filename = f"{uuid.uuid4().hex}.png"
            full_path = self.media_dir / filename
            filename = f"{uuid.uuid4().hex}.png"
            await page.screenshot(path=str(full_path), full_page=True)
            print(f"✅ Screenshot saved: {full_path}")
            return f"post_screenshots/{filename}"
        except Exception as e:
            print(f"❌ Screenshot fail: {e}")
            return None

    async def _extract_single_comment(self, div, page):
        comments = []
        try:
            author_el = div.locator('a[aria-hidden="false"]').first
            author = (await author_el.inner_text()).strip() if await author_el.count() else None

            profile_img_url = None
            for tag in await div.locator('image').all():
                href = await tag.get_attribute('xlink:href')
                if href and 'fbcdn.net' in href:
                    profile_img_url = href
                    break

            content_el = div.locator('div[dir="auto"]').first
            content_html = (await content_el.inner_html()).strip() if await content_el.count() else ''
            soup = BeautifulSoup(content_html, 'html.parser')
            content_el = div.locator('div[dir="auto"]').first
            content_html = (await content_el.inner_html()).strip() if await content_el.count() else ''

            content = ''
            if content_html:
                soup = BeautifulSoup(content_html, 'html.parser')
                for img in soup.find_all('img'):
                    alt = img.get('alt')
                    if alt:
                        img.replace_with(alt)

                for br in soup.find_all("br"):
                    br.replace_with("\n")
                content = soup.get_text(separator='\n', strip=True)

            image_url = None
            for tag in await div.locator('img').all():
                src = await tag.get_attribute('src')
                if src and 'scontent' in src:
                    image_url = src
                    break

            time_text = None
            time_el = div.locator('a[href*="?comment_id="]').last
            if await time_el.count():
                time_text = await self.get_hover_timestamp(time_el, page)

            reaction = None
            for span in await div.locator('span.x1fcty0u.x1sibtaa.xuxw1ft').all():
                txt = await span.inner_text()
                if txt.strip().isdigit():
                    reaction = f"ถูกใจ {txt.strip()}"
                    break

            comments.append({
                "author": author,
                "profile_img_url": profile_img_url,
                "content": content,
                "reaction": reaction,
                "timestamp_text": time_text,
                "image_url": image_url,
            })

            reply_blocks = await div.locator('div[role="article"][aria-label]').all()
            for reply_div in reply_blocks:
                nested_comments = await self._extract_single_comment(reply_div, page)
                comments.extend(nested_comments)

        except Exception as e:
            print(f"❌ Extract comment error: {e}")
        return comments

    async def _extract_comments(self, page):
        comments = []
        blocks = await page.locator('div[role="article"][aria-label]').all()
        for div in blocks:
            nested = await self._extract_single_comment(div, page)
            comments.extend(nested)
        return comments

    async def start(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            await self.load_cookies(context)
            page = await context.new_page()
            await page.goto(self.post_url, timeout=60000)
            await page.wait_for_timeout(3000)

            post_img = await self.capture_post_screenshot(page)
            await self.scroll_until_fully_loaded(page)
            all_comments = await self._extract_comments(page)

            return {
                "post_screenshot_path": str(post_img) if post_img else None,
                "comments": all_comments
            }

async def run_fb_comment_scraper(post_url):
    scraper = FBCommentScraper(post_url)
    return await scraper.start()

if __name__ == "__main__":
    url = "https://www.facebook.com/photo/?fbid=122186666168274942&set=a.122113064870274942"
    results = asyncio.run(run_fb_comment_scraper(url))
    print(json.dumps(results, ensure_ascii=False, indent=2))
