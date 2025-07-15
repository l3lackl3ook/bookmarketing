import json
import re
import asyncio
import time
from pathlib import Path
from pprint import pprint
from typing import Any, Optional, List, Tuple

from playwright.async_api import Playwright, async_playwright, Browser, Page, BrowserContext
from datetime import datetime

class FBPostScraperAsync:
    def __init__(self, cookie_file: str, headless: bool = False,
                 page_url: Optional[str] = None, cutoff_dt: datetime = None,
                 batch_size: int = 10):
        self.cookie_file = cookie_file
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.page_url = page_url
        self.cutoff_dt = cutoff_dt
        self.batch_size = batch_size

        # JavaScript snippet to fetch posts (push all, let Python filter by cutoff)
        JS_FETCH_POSTS = r"""(cutoffMs) => {
            const results = [];
            let olderReached = false;
            const containers = document.querySelectorAll('div[data-pagelet^="TimelineFeedUnit_"]');
            for (const post of containers) {
                const postLink = post.querySelector('a[href*="/posts/"]');
                if (!postLink) continue;
                const abbr = postLink.querySelector('abbr');
                let epochMs = null;
                if (abbr && abbr.dataset && abbr.dataset.utime) {
                    epochMs = parseInt(abbr.dataset.utime, 10) * 1000;
                } else {
                    const tooltip = postLink.getAttribute('aria-label');
                    if (!tooltip) continue;
                    const thaiMonths = {
                        "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
                        "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
                        "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
                    };
                    // (include your existing tooltip parsing logic here)
                    const now = Date.now();
                    const relMatch = tooltip.match(/(\d+)\s*(วินาที|นาที|ชั่วโมง|วัน)/);
                    if (relMatch) {
                        const value = parseInt(relMatch[1], 10);
                        const unit = relMatch[2];
                        if (unit === 'วินาที') {
                            epochMs = now - value * 1000;
                        } else if (unit === 'นาที') {
                            epochMs = now - value * 60 * 1000;
                        } else if (unit === 'ชั่วโมง') {
                            epochMs = now - value * 3600 * 1000;
                        } else if (unit === 'วัน') {
                            epochMs = now - value * 86400 * 1000;
                        }
                    } else {
                        const abs = tooltip.match(/(\d+)\s+([^\s]+)\s+เวลา\s+(\d{1,2}):(\d{2})\s+น\.$/);
                        if (abs) {
                            const d=parseInt(abs[1],10), m=thaiMonths[abs[2]], h=parseInt(abs[3],10), min=parseInt(abs[4],10);
                            const yr=new Date().getFullYear();
                            epochMs=new Date(yr,m-1,d,h,min).getTime();
                        }
                        else {
                            // Handle "DD Month YYYY" without time
                            const absYear = tooltip.match(/(\d+)\s+([^\s]+)\s+(\d{4})$/);
                            if (absYear) {
                                const dayY = parseInt(absYear[1], 10);
                                const monthY = thaiMonths[absYear[2]];
                                const yearY = parseInt(absYear[3], 10);
                                epochMs = new Date(yearY, monthY - 1, dayY).getTime();
                            } else {
                                // Handle "DD Month" without time, assume current year
                                const absNoYear = tooltip.match(/(\d+)\s+([^\s]+)$/);
                                if (absNoYear) {
                                    const dayN = parseInt(absNoYear[1], 10);
                                    const monthN = thaiMonths[absNoYear[2]];
                                    const yearN = new Date().getFullYear();
                                    epochMs = new Date(yearN, monthN - 1, dayN).getTime();
                                }
                            }
                        }
                    }
                }
                if (epochMs !== null) {
                    if (epochMs >= cutoffMs) {
                        // Post is within cutoff window
                        results.push({ id: postLink.href, epoch: epochMs });
                    } else {
                        olderReached = true;
                        continue;
                    }
                }
            }
            return { results, olderReached };
        }"""
        self.JS_FETCH_POSTS = JS_FETCH_POSTS

    async def _scroll_and_eval(self, page, cutoff_ms):
        # Scroll to load more posts, then run the fetch JS
        await page.evaluate("window.scrollBy(0, document.body.scrollHeight);")
        await page.wait_for_timeout(3000)
        return await page.evaluate(self.JS_FETCH_POSTS, cutoff_ms)

    async def _process_cookie(self) -> List[dict]:
        raw = json.loads(Path(self.cookie_file).read_text())
        for cookie in raw:
            s = cookie.get("sameSite")
            if s is None or (isinstance(s, str) and s.lower() == "no_restriction"):
                cookie["sameSite"] = "None"
            elif isinstance(s, str) and s.lower() == "lax":
                cookie["sameSite"] = "Lax"
            elif isinstance(s, str) and s.lower() == "strict":
                cookie["sameSite"] = "Strict"
        return raw

    async def _confirm_login(self, page: Page) -> Optional[str]:
        try:
            # Wait for the navigation role element with aria-label "ทางลัด"
            nav = page.get_by_role("navigation", name="ทางลัด")
            await nav.wait_for(timeout=5000)
            # The first link inside nav is the user profile; its text is the username
            profile_link = nav.get_by_role("link").first
            await profile_link.wait_for(timeout=5000)
            username = (await profile_link.inner_text()).strip()
            return username
        except Exception as e:
            print(f"[confirm_login] failed to confirm login: {e}")
            return None

    def _parse_thai_timestamp(self, text: str) -> datetime:
        thai_months = {
            "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
            "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
            "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
        }
        parts = text.split()
        try:
            # Try parsing "วัน...ที่ DD Month YYYY เวลา hh:mm น."
            if len(parts) >= 5 and parts[3].isdigit():
                day = int(parts[1])
                month_name = parts[2]
                month = thai_months.get(month_name, 0)
                year = int(parts[3])
                time_part = parts[5]
            else:
                # No year provided; use current year
                day = int(parts[1])
                month_name = parts[2]
                month = thai_months.get(month_name, 0)
                year = datetime.now().year
                time_part = parts[4]  # "hh:mm"
            hour_str, minute_str = time_part.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
            return datetime(year, month, day, hour, minute)
        except Exception:
            return datetime(1970, 1, 1)

    def _parse_thai_number(self, text: str) -> int:
        """Convert a Thai-formatted count (e.g. '1.2 พัน', '5 หมื่น') to an integer."""
        import re
        units = {'พัน': 10**3, 'หมื่น': 10**4, 'แสน': 10**5, 'ล้าน': 10**6}
        t = text.strip()
        # Check for known units
        for unit, mul in units.items():
            if t.endswith(unit):
                num_str = t[:-len(unit)].strip()
                try:
                    value = float(num_str)
                except ValueError:
                    value = 1.0
                return int(value * mul)
        # Fallback: strip non-digits and parse
        digits = re.sub(r'[^\d]', '', t)
        return int(digits) if digits else 0

    async def _get_post(self, page: Page, cutoff_dt: datetime, max_posts: int, seen_ids: set) -> Tuple[List[Tuple[str, datetime]], bool]:
        batch: List[Tuple[str, datetime]] = []
        cutoff_ms = 0 if cutoff_dt is None else int(cutoff_dt.timestamp() * 1000)
        older_than_cutoff = False
        empty_fetch_retries = 0
        max_empty_fetch_retries = 3

        # Initial navigation & load
        if not seen_ids:
            await page.goto(self.page_url)
        await page.wait_for_selector('div[data-pagelet^="TimelineFeedUnit_"]', timeout=5000)

        # Loop until we collect enough or hit older posts
        while len(batch) < max_posts and not older_than_cutoff:
            # data = await page.evaluate(self.JS_FETCH_POSTS, cutoff_ms)
            raw = await page.evaluate(self.JS_FETCH_POSTS, cutoff_ms)
            data = raw.get("results", [])
            if raw.get("olderReached"):
                older_than_cutoff = True
            empty_fetch_retries = 0
            if not data:
                if empty_fetch_retries < max_empty_fetch_retries:
                    empty_fetch_retries += 1
                    await page.evaluate("window.scrollBy(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(2000)
                    continue
                else:
                    break

            for entry in data:
                url = entry["id"]
                dt_obj = datetime.fromtimestamp(entry["epoch"] / 1000)
                if cutoff_dt and dt_obj < cutoff_dt:
                    older_than_cutoff = True
                    break
                if url not in seen_ids:
                    batch.append((url, dt_obj))
                    seen_ids.add(url)
                    if len(batch) >= max_posts:
                        break

            if older_than_cutoff or len(batch) >= max_posts:
                break

            # Scroll and retry
            # data_retry = await self._scroll_and_eval(page, cutoff_ms)
            raw_retry = await self._scroll_and_eval(page, cutoff_ms)
            data_retry = raw_retry.get("results", [])
            if raw_retry.get("olderReached"):
                older_than_cutoff = True
            # Merge retry results same as above
            for entry in data_retry:
                url = entry["id"]
                dt_obj = datetime.fromtimestamp(entry["epoch"] / 1000)
                if cutoff_dt and dt_obj < cutoff_dt:
                    older_than_cutoff = True
                    break
                if url not in seen_ids:
                    batch.append((url, dt_obj))
                    seen_ids.add(url)
                    if len(batch) >= max_posts:
                        break

        return batch, older_than_cutoff

    async def _get_post_detail(self, context: BrowserContext, post_url: str) -> Optional[dict]:
        """
        We open a *new tab/page* for each post order to parallelize.
        """
        try:
            # print(f"[get_post_detail] Opening detail page for: {post_url}")
            detail_page = await context.new_page()
            await detail_page.goto(post_url)

            # Wait for the light‐mode container
            light_container = detail_page.locator('div.__fb-light-mode.x1n2onr6.x1vjfegm').first
            try:
                await light_container.wait_for(timeout=10000)
            except Exception as e:
                print(f"[get_post_detail] Timeout waiting for light_container on {post_url}: {e}")
                await detail_page.close()
                return None

            # Hover on the <a href="/posts/..."> to reveal timestamp tooltip
            post_link = light_container.locator('a[href*="/posts/"]').first
            await post_link.hover()

            tooltip_span = detail_page.locator('div[role="tooltip"] span.x193iq5w').first
            try:
                await tooltip_span.wait_for(timeout=10000)
            except Exception as e:
                print(f"[get_post_detail] Timeout waiting for tooltip_span on {post_url}: {e}")
                await detail_page.close()
                return None
            post_timestamp_text = (await tooltip_span.text_content()).strip()
            post_timestamp_dt = self._parse_thai_timestamp(post_timestamp_text)

            # Extract story_message (handle posts with only images)
            story_locator = light_container.locator('div[data-ad-rendering-role="story_message"]').first
            post_content = ""
            try:
                # Only extract if the element exists
                if await story_locator.count():
                    # Expand "ดูเพิ่มเติม" if present to reveal full content
                    more_btn = story_locator.locator('div[role="button"]', has_text="ดูเพิ่มเติม")
                    if await more_btn.count():
                        await more_btn.first.click()
                        await detail_page.wait_for_timeout(500)
                    post_content = (await story_locator.inner_text()).strip()
                else:
                    print(f"[get_post_detail] No text content for {post_url}, skipping content extraction.")
            except Exception as e:
                print(f"[get_post_detail] Error extracting story_message for {post_url}: {e}")

            # Collect image URLs from img tags inside <a href*="/photo/">
            post_imgs = []
            photo_imgs = await light_container.locator('a[href*="/photo/"] img').all()
            for img_elem in photo_imgs:
                src_val = await img_elem.get_attribute("src")
                if src_val:
                    post_imgs.append(src_val)

            # Comment count
            comment_count = 0
            comments = []
            try:
                # Find the button that includes the comment label
                comment_element = light_container.locator('div[role="button"]', has_text='ความคิดเห็น').first
                comment_text = (await comment_element.text_content()).strip()
                # Extract Thai-formatted number and parse
                import re
                comment_match = re.search(r'([\d\.]+\s*(?:พัน|หมื่น|แสน|ล้าน)?)', comment_text)
                if comment_match:
                    comment_count = self._parse_thai_number(comment_match.group(1))
                # Only fetch comments if there are any
                # if comment_count > 0:
                #     comments = await self._get_post_comments(detail_page)
            except Exception:
                pass

            # Share count
            share_count = 0
            try:
                share_element = light_container.locator('div[role="button"]', has_text='แชร์').first
                share_text = (await share_element.text_content()).strip()
                # Extract Thai-formatted number and parse
                share_match = re.search(r'([\d\.]+\s*(?:พัน|หมื่น|แสน|ล้าน)?)', share_text)
                if share_match:
                    share_count = self._parse_thai_number(share_match.group(1))
            except Exception:
                pass

            # Extract just the ID portion from the URL
            raw_id = post_url.split('/posts/')[1]
            post_id = raw_id.split('?')[0]

            reactions = {}
            try:
                # 1) Wait for the reactions bar to show up
                await detail_page.wait_for_selector('.__fb-light-mode.x1n2onr6.x1vjfegm', timeout=10_000)

                # 2) Click the “ความรู้สึกทั้งหมด” button by text
                #    (scoped under that same container so we don’t accidentally hit something else)
                await detail_page.locator(
                    '.__fb-light-mode.x1n2onr6.x1vjfegm >> text="ความรู้สึกทั้งหมด"'
                ).first.click()

                # 3) Wait for the full-reaction overlay and scope to it
                overlay = detail_page.locator('.__fb-light-mode.x1n2onr6.xzkaem6').first
                await overlay.wait_for(state='visible', timeout=10_000)

                # Wait for the specific element inside the overlay
                target_elem = overlay.locator('.xf7dkkf.xv54qhq').first
                await target_elem.wait_for(state='visible', timeout=10_000)

                # Extract each reaction (except "ทั้งหมด")
                reaction_tabs = overlay.locator('div[role="tab"]')
                count_tabs = await reaction_tabs.count()
                for i in range(count_tabs):
                    tab = reaction_tabs.nth(i)
                    # Derive reaction type from aria-label, e.g. 'ถูกใจ', 'รักเลย'
                    aria = await tab.get_attribute('aria-label')
                    label_match = None
                    if aria:
                        m = re.search(r'แสดง\s[\d,\.]+\sคนที่แสดงความรู้สึก\s“?\"?([^\"”]+)\"?\"?', aria)
                        if m:
                            label_match = m.group(1).strip()
                    if not label_match or label_match == 'ทั้งหมด':
                        continue
                    label = label_match
                    # Get the count from the span inside the tab
                    count_text = (await tab.locator('span.x193iq5w').first.text_content()).strip()
                    reactions[label] = self._parse_thai_number(count_text)

            except Exception as exc:
                print(f"[get_post_reactions] failed: {exc}")

            # print(f"[get_post_detail] Successfully fetched details for {post_id}")
            await detail_page.close()

            return {
                'post_url': post_url,
                "post_id": post_id,
                "post_type": "post",
                "post_timestamp_text": post_timestamp_text,
                "post_timestamp_dt": post_timestamp_dt,
                "post_content": post_content,
                "post_imgs": post_imgs,
                "reactions": reactions,
                "comment_count": comment_count,
                "share_count": share_count,
                # "comments": comments,
            }

        except Exception as e:
            print(f"[get_post_detail] ERROR for {post_url}: {e}")
            try:
                await detail_page.close()
            except:
                pass
            return None

    async def _get_post_comments(self, page: Page) -> list:
        comments = []
        try:
            # Wait for and click the comments sort button
            await page.wait_for_selector('div.x6s0dn4.x78zum5.xdj266r.x14z9mp.xat24cr.x1lziwak.xe0p6wg', timeout=10000)
            await page.click('div.x6s0dn4.x78zum5.xdj266r.x14z9mp.xat24cr.x1lziwak.xe0p6wg')
            # Open the full comments dialog
            await page.click('div[role="menuitem"] >> text="ความคิดเห็นทั้งหมด"')
            # 1) Wait for the comments dialog Locator to appear
            dialog = page.locator('div[role="dialog"]').first
            await dialog.wait_for(timeout=10000)
            # Find the actual scrollable element inside the dialog via computed styles
            dialog_handle = await dialog.element_handle()
            scrollable_handle = await page.evaluate_handle(
                """dialog => {
                    const divs = Array.from(dialog.querySelectorAll('div'));
                    return divs.find(el => {
                        const style = window.getComputedStyle(el);
                        return style.overflowY === 'auto' || style.overflowY === 'scroll';
                    }) || dialog;
                }""",
                dialog_handle
            )
            # Scroll until no new comments load
            prev_count = 0
            while True:
                # Count loaded top-level comments
                curr_count = await page.locator('div[role="article"][aria-label^="ความคิดเห็นจาก"]').count()
                if curr_count > prev_count:
                    prev_count = curr_count
                    await scrollable_handle.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                    await page.wait_for_timeout(1000)
                else:
                    break
        except Exception as e:
            print(f"[get_post_comments] Failed to open comments menu: {e}")
            return comments

        # Wait for at least one top-level comment to load
        try:
            await page.wait_for_selector('div[role="article"][aria-label^="ความคิดเห็นจาก"]', timeout=10000)
        except Exception:
            # No top-level comments present; exit gracefully
            return []

        # Select only main comment containers (exclude replies)
        comment_divs = await page.locator('div[role="article"][aria-label^="ความคิดเห็นจาก"]').all()
        for div in comment_divs:
            try:
                image_element = div.locator('svg image').first
                profile_img = await image_element.get_attribute('xlink:href')

                # Extract commenter name and profile URL from the visible name link
                visible_links = div.locator('a[aria-hidden="false"]')
                if await visible_links.count():
                    name_link = visible_links.first
                else:
                    name_link = div.locator('a').first
                await name_link.wait_for(timeout=5000)
                profile_name = (await name_link.text_content()).strip()
                href = await name_link.get_attribute('href')
                profile_url = href.split('?')[0] if href else None

                # Extract just the comment message
                # Look for the nested div with dir="auto" inside the comment body
                msg_locator = div.locator('div.x1lliihq.xjkvuk6.x1iorvi4 div[dir="auto"]').first
                if await msg_locator.count():
                    comment_text = (await msg_locator.inner_text()).strip()
                else:
                    comment_text = ''

                # Hover to reveal timestamp tooltip
                time_link = div.locator('a[href*="?comment_id="]').last
                try:
                    await time_link.hover()
                    await page.wait_for_selector('div[role="tooltip"]', timeout=5000)
                    tooltip = page.locator('div[role="tooltip"]').first
                    time_stamp_text = (await tooltip.inner_text()).strip()
                    time_stamp_dt = self._parse_thai_timestamp(time_stamp_text)
                except:
                    time_stamp_text = None
                    time_stamp_dt = None

                comments.append({
                    "user_name": profile_name,
                    "profile_url": profile_url,
                    "profile_img": profile_img,
                    "comment_text": comment_text,
                    "time_stamp_text": time_stamp_text,
                    "time_stamp_dt": time_stamp_dt,
                })
            except Exception as e:
                print(f"[get_post_comments] Error extracting a comment: {e}")
                print(page.url)
                continue

        return comments

    async def run(self) -> None:
        print("Starting scraper...")
        async with async_playwright() as pw:
            launch_args = {"headless": self.headless}
            self.browser = await pw.chromium.launch(**launch_args)
            print("Browser launched.")
            context_args = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            }
            self.context = await self.browser.new_context(**context_args)
            cookie_list = await self._process_cookie()
            await self.context.add_cookies(cookie_list)

            # ---------------------
            # 1) Confirm login
            # ---------------------
            self.page = await self.context.new_page()
            await self.page.goto("https://www.facebook.com/")
            username = await self._confirm_login(self.page)
            print(f"Login as: {username or 'unknown'}")
            if not username:
                print("Login failed, stopping.")
                return

            # ---------------------
            # 2) Get page name
            # ---------------------
            if self.page_url:
                try:
                    await self.page.goto(self.page_url)
                    title_container = self.page.locator(
                        "div.x9f619.x1n2onr6.x1ja2u2z.x78zum5.xdt5ytf.x2lah0s.x193iq5w.x1cy8zhl.xexx8yu"
                    ).first
                    await title_container.wait_for(timeout=10000)
                    raw_page_name = await title_container.locator("h1.html-h1").text_content()
                    page_name = raw_page_name.split("\u00A0")[0].strip()
                    print(f"Page name: {page_name}")
                    print(f"Cutoff datetime: {self.cutoff_dt}")
                except Exception as e:
                    print(f"Failed to open Facebook Page: {e}")
                    return

                # ---------------------
                # 3) Collect posts and fetch details in batches
                # ---------------------
                seen_ids = set()
                all_results = []

                batch_index = 1
                cutoff_dt = self.cutoff_dt
                empty_batch_retries = 0
                max_empty_batch_retries = 3
                while True:
                    print(f"Collecting batch {batch_index} of posts...")
                    batch_posts, older = await self._get_post(
                        page=self.page,
                        cutoff_dt=cutoff_dt,
                        max_posts=self.batch_size,
                        seen_ids=seen_ids
                    )
                    if not batch_posts:
                        if empty_batch_retries < max_empty_batch_retries:
                            empty_batch_retries += 1
                            print(f"No posts fetched; retrying scroll ({empty_batch_retries}/{max_empty_batch_retries})")
                            await self.page.evaluate("window.scrollBy(0, document.body.scrollHeight);")
                            await self.page.wait_for_timeout(500)
                            continue
                        else:
                            print("No posts fetched after retries; exiting.")
                            break
                    # Reset retry counter when posts are fetched
                    empty_batch_retries = 0

                    print(f"Found {len(batch_posts)} posts in batch {batch_index}.")
                    print("Getting post details for this batch...")

                    # Process fetched posts...
                    tasks = [
                        self._get_post_detail(self.context, post_url)
                        for (post_url, _) in batch_posts
                    ]
                    batch_results = await asyncio.gather(*tasks)
                    for detail in batch_results:
                        if detail:
                            all_results.append(detail)
                            pprint(detail)

                    # After processing, if we hit older posts, exit
                    if older:
                        print("Reached cutoff after processing; exiting.")
                        break

                    batch_index += 1
                    # Scroll down for the next batch
                    print("Scrolling down for next batch...")
                    await self.page.evaluate("window.scrollBy(0, document.body.scrollHeight);")
                    await self.page.wait_for_timeout(500)

                print(f"Fetched all post details. Total posts: {len(all_results)}")

            # ---------------------
            # 5) Cleanup
            # ---------------------
            await self.context.close()
            await self.browser.close()
        print("Scraper finished.")
        return all_results

    def start(self):
        """Synchronous entry point to launch the async run."""
        return asyncio.run(self.run())


if __name__ == "__main__":
    scraper = FBPostScraperAsync(
        cookie_file="cookie.json",
        headless=False,
        page_url="https://www.facebook.com/dairyqueenthailand",
        cutoff_dt=datetime(2025, 5, 1, 0, 0),
        # cutoff_dt= None,
        batch_size = 10
    )
    scraper.start()