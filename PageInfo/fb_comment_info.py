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
            btn_related = page.locator('//span[contains(text(),"เกี่ยวข้องมากที่สุด")]')
            if await btn_related.count() > 0:
                await btn_related.first.click(timeout=15000, force=True)
                await page.wait_for_timeout(1500)
                print("✅ คลิก 'เกี่ยวข้องมากที่สุด' สำเร็จ")
            btn_newest = page.locator('//span[contains(text(),"ใหม่ล่าสุด")]')
            if await btn_newest.count() > 0:
                await btn_newest.first.click(timeout=15000, force=True)
                await page.wait_for_timeout(2000)
                print("✅ คลิก 'ใหม่ล่าสุด' สำเร็จ")
        except Exception as e:
            print(f"❌ คลิก 'ใหม่ล่าสุด' ไม่สำเร็จ: {e}")

    async def click_all_buttons(self, page, xpath, desc):
        buttons = await page.locator(xpath).all()
        new_clicks = 0
        for btn in buttons:
            try:
                await btn.scroll_into_view_if_needed(timeout=5000)
                if await btn.is_visible() and await btn.is_enabled():
                    await btn.click(timeout=5000)
                    await page.wait_for_timeout(500)
                    new_clicks += 1
            except:
                continue
        print(f"✅ คลิก {desc}: {new_clicks} ครั้ง")
        return new_clicks

    async def scroll_until_fully_loaded(self, page):
        last_count = 0
        same_count_round = 0
        round_num = 0

        await self.click_sort_by_newest(page)

        while True:
            round_num += 1

            new_clicks = 0
            new_clicks += await self.click_all_buttons(page, '//span[contains(text(),"ดูความเห็นเพิ่มเติม")]', "ดูความเห็นเพิ่มเติม")
            new_clicks += await self.click_all_buttons(page, '//span[contains(text(),"ดู") and contains(text(),"ตอบกลับ")]', "ดูตอบกลับ")
            new_clicks += await self.click_all_buttons(page, '//span[contains(text(),"ดูการตอบกลับทั้งหมด") or contains(text(),"ดูการตอบกลับเพิ่มเติม")]', "ดูการตอบกลับทั้งหมด")

            blocks = await page.locator('div[role="article"][aria-label]').all()
            count = len(blocks)
            print(f"🔁 รอบที่ {round_num} | คอมเมนต์: {count}")

            if count == last_count and new_clicks == 0:
                same_count_round += 1
            else:
                same_count_round = 0
                last_count = count

            if same_count_round >= 4:
                print("✅ โหลดครบแล้ว")
                print(f"📦 รวมทั้งหมด {count} คอมเมนต์")
                break

            if blocks:
                try:
                    await blocks[-1].scroll_into_view_if_needed(timeout=5000)
                except:
                    pass

            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(1200)

    async def capture_post_screenshot(self, page):
        try:
            post = None
            try:
                await page.wait_for_selector('div[role="dialog"] div[role="article"]', timeout=5000)
                post = page.locator('div[role="dialog"] div[role="article"]').first
            except:
                await page.wait_for_selector('div[role="article"]', timeout=10000)
                post = page.locator('div[role="article"]').first

            await page.wait_for_timeout(3000)

            await post.evaluate("""
                (node) => {
                    node.style.transform = "scale(0.75)";
                    node.style.transformOrigin = "top left";
                }
            """)

            await page.wait_for_timeout(1000)

            footer = post.locator('div[aria-label*="ถูกใจ"]').first
            footer_box = await footer.bounding_box()
            post_box = await post.bounding_box()

            cropped_height = (footer_box["y"] + footer_box["height"]) - post_box["y"]
            final_box = {
                "x": post_box["x"],
                "y": post_box["y"],
                "width": post_box["width"],
                "height": cropped_height
            }

            filename = f"{uuid.uuid4().hex}.png"
            full_path = self.media_dir / filename
            await page.screenshot(path=str(full_path), clip=final_box)

            print(f"✅ แคปโพสต์เรียบร้อย: {full_path}")
            return f"post_screenshots/{filename}"

        except Exception as e:
            print(f"❌ แคปโพสต์ล้มเหลว: {e}")
            return None

    async def _extract_single_comment(self, div, parent_id=None):
        comments = []
        try:
            author_el = div.locator('a[aria-hidden="false"]').first
            author = (await author_el.inner_text()).strip() if await author_el.count() else None

            profile_img_url = None
            try:
                for tag in await div.locator('image').all():
                    href = await tag.get_attribute('xlink:href')
                    if href and 'fbcdn.net' in href:
                        profile_img_url = href
                        break
            except:
                pass

            content_el = div.locator('div[dir="auto"]').first
            content_html = (await content_el.inner_html()).strip() if await content_el.count() else ''
            soup = BeautifulSoup(content_html, 'html.parser')

            content_parts = []
            seen = set()
            for el in soup.descendants:
                if el.name == 'img' and el.has_attr('alt'):
                    emoji = el['alt'].strip()
                    if emoji not in seen:
                        content_parts.append(emoji)
                        seen.add(emoji)
                elif el.name == 'a':
                    text = el.get_text(strip=True)
                    if text and text not in seen:
                        content_parts.append(text)
                        seen.add(text)
                elif el.string:
                    text = el.string.strip()
                    if text and text not in seen:
                        content_parts.append(text)
                        seen.add(text)
            content = ' '.join(content_parts)

            image_url = None
            try:
                for tag in await div.locator('img').all():
                    src = await tag.get_attribute('src')
                    if src and 'scontent' in src:
                        image_url = src
                        break
            except:
                pass

            time_text = None
            try:
                time_el = div.locator('a[href*="?comment_id="]').last
                if await time_el.count():
                    time_text = (await time_el.inner_text()).strip()
            except:
                pass

            reaction = None
            try:
                span_react = await div.locator('span.x1fcty0u.x1sibtaa.xuxw1ft').all()
                for span in span_react:
                    txt = await span.inner_text()
                    if txt.strip().isdigit():
                        reaction = f"ถูกใจ {txt.strip()}"
                        break
            except:
                pass

            comment_data = {
                "author": author,
                "profile_img_url": profile_img_url,
                "content": content,
                "reaction": reaction,
                "timestamp_text": time_text,
                "image_url": image_url,
            }
            comments.append(comment_data)

            reply_blocks = await div.locator('div[role="article"][aria-label]').all()
            for reply_div in reply_blocks:
                nested_comments = await self._extract_single_comment(reply_div)
                comments.extend(nested_comments)

        except Exception as e:
            print(f"Error extracting comment: {e}")

        return comments

    async def _extract_comments(self, page):
        comments = []
        blocks = await page.locator('div[role="article"][aria-label]').all()
        for div in blocks:
            nested = await self._extract_single_comment(div)
            comments.extend(nested)
        return comments

    async def start(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
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
    url = "https://www.facebook.com/wittyhomemakers/posts/pfbid0EdqFg9PPnHvq9yX7mkNvKqMjy5xEn3cRFePg8GtHnADJpaFxDrRmyBjk469ACMAnl"
    results = asyncio.run(run_fb_comment_scraper(url))
    print(json.dumps(results, ensure_ascii=False, indent=2))
