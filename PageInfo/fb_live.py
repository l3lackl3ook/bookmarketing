import json
import re
import asyncio
import time
from pathlib import Path
from pprint import pprint
from typing import Any, Optional, List, Tuple

from playwright.async_api import Playwright, async_playwright, Browser, Page, BrowserContext
from datetime import datetime


class FBLiveScraperAsync:
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
            // Select each individual live-video card container
            const containers = document.querySelectorAll('div.x1l90r2v.x12qybmz');
            for (const post of containers) {
                // Live URL
                const linkEl = post.querySelector('a[href*="/videos/"]');
                if (!linkEl) continue;
                const href = linkEl.href;

                // Extract description text by matching video ID in href
                let description = null;
                const vidId = href.substring(href.lastIndexOf('/') + 1);
                const captionAnchor = post.querySelector(`a[href*="${vidId}"][aria-label]`);
                if (captionAnchor) {
                    description = captionAnchor.getAttribute('aria-label');
                }
                console.log('Extracted URL:', href);
                console.log('Extracted Des:', description);

                // Thumbnail element
                const imgEl = post.querySelector('img.x1rg5ohu.x5yr21d');
                const thumbnail = imgEl ? imgEl.src : null;

                // Watch count and date element
                const statsEl = post.querySelector('div.x1xmf6yo span abbr');
                const dateText = statsEl ? statsEl.getAttribute('aria-label') : null;


                // Use the dateText (aria-label) for timestamp parsing
                const tooltip = dateText || '';
                let epochMs = null;

                // Thai month mapping
                const thaiMonths = {
                    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
                    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
                    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
                };

                const now = Date.now();
                // Relative times (seconds, minutes, hours, days, years)
                const relMatch = tooltip.match(/(\d+)\s*(วินาที|นาที|ชั่วโมง|วัน|ปีที่แล้ว|ปี)/);
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
                    } else if (unit === 'ปีที่แล้ว' || unit === 'ปี') {
                        epochMs = now - value * 365 * 24 * 3600 * 1000;
                    }
                } else {
                    // Absolute dates: formats "DD Month YYYY เวลา hh:mm น." or "DD Month hh:mm น." or "DD Month YYYY" or "DD Month"
                    let abs = tooltip.match(/(\d+)\s+([^\s]+)\s+เวลา\s+(\d{1,2}):(\d{2})\s+น\.$/);
                    if (abs) {
                        const d = parseInt(abs[1], 10);
                        const m = thaiMonths[abs[2]] || 0;
                        const h = parseInt(abs[3], 10);
                        const min = parseInt(abs[4], 10);
                        const yr = new Date().getFullYear();
                        epochMs = new Date(yr, m - 1, d, h, min).getTime();
                    } else {
                        // "DD Month YYYY"
                        let absYear = tooltip.match(/(\d+)\s+([^\s]+)\s+(\d{4})$/);
                        if (absYear) {
                            const d = parseInt(absYear[1], 10);
                            const m = thaiMonths[absYear[2]] || 0;
                            const y = parseInt(absYear[3], 10);
                            epochMs = new Date(y, m - 1, d).getTime();
                        } else {
                            // "DD Month"
                            let absNoYear = tooltip.match(/(\d+)\s+([^\s]+)$/);
                            if (absNoYear) {
                                const d = parseInt(absNoYear[1], 10);
                                const m = thaiMonths[absNoYear[2]] || 0;
                                const y = new Date().getFullYear();
                                epochMs = new Date(y, m - 1, d).getTime();
                            }
                        }
                    }
                }
                // Fallback for posts where date parsing failed
                if (epochMs === null) {
                    console.log('No epoch parsed, defaulting to now for href:', href, 'tooltip:', tooltip);
                    epochMs = Date.now();
                }
                if (epochMs !== null) {
                    if (epochMs >= cutoffMs) {
                        // include thumbnail and URL and dateText and description
                        results.push({ id: href, epoch: epochMs, thumbnail, dateText, description });
                    } else {
                        olderReached = true;
                        // continue checking others
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
        # Handle dates with only day and month (e.g., '23 กุมภาพันธ์')
        if len(parts) == 2 and parts[0].isdigit():
            day = int(parts[0])
            month = thai_months.get(parts[1], 0)
            year = datetime.now().year
            return datetime(year, month, day)
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
        units = {'พัน': 10 ** 3, 'หมื่น': 10 ** 4, 'แสน': 10 ** 5, 'ล้าน': 10 ** 6}
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

    async def _get_post(self, page: Page, cutoff_dt: datetime, max_posts: int, seen_ids: set) -> Tuple[
        List[Tuple[str, datetime, str, Optional[str]]], bool]:
        batch: List[Tuple[str, datetime, str, Optional[str]]] = []
        cutoff_ms = 0 if cutoff_dt is None else int(cutoff_dt.timestamp() * 1000)
        older_than_cutoff = False
        empty_fetch_retries = 0
        max_empty_fetch_retries = 3

        # Initial navigation & load
        if not seen_ids:
            video_page_url = f"{self.page_url.rstrip('/')}/live_videos"
            await page.goto(video_page_url)
        await page.wait_for_selector('div.x1l90r2v.x12qybmz', timeout=10000)

        # Loop until we collect enough or hit older posts
        while len(batch) < max_posts and not older_than_cutoff:
            prev_seen_count = len(seen_ids)
            # data = await page.evaluate(self.JS_FETCH_POSTS, cutoff_ms)
            raw = await page.evaluate(self.JS_FETCH_POSTS, cutoff_ms)
            data = raw.get("results", [])
            if raw.get("olderReached"):
                older_than_cutoff = True
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
                    batch.append((url, dt_obj, entry.get("thumbnail"), entry.get("description")))
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
                    batch.append((url, dt_obj, entry.get("thumbnail"), entry.get("description")))
                    seen_ids.add(url)
                    if len(batch) >= max_posts:
                        break

            # If no new posts were added in this iteration, break to avoid infinite loop
            if len(seen_ids) == prev_seen_count:
                older_than_cutoff = True
                break

        return batch, older_than_cutoff

    async def _get_post_detail(self, context: BrowserContext, post_url: str, video_thumbnail: str,
                               description: Optional[str]) -> Optional[dict]:
        try:
            # print(f"[get_post_detail] Opening detail page for: {post_url}")
            detail_page = await context.new_page()
            await detail_page.goto(post_url)
            # Click the comment button to trigger URL change back to /videos/
            await detail_page.wait_for_selector('div[aria-label="แสดงความคิดเห็น"]', timeout=5000)
            await detail_page.click('div[aria-label="แสดงความคิดเห็น"]', force=True)
            # Wait for the URL to update to the /videos/ format
            await detail_page.wait_for_url(lambda url: '/videos/' in url, timeout=5000)
            # Disable video autoplay
            await detail_page.evaluate("""
                document.querySelectorAll('video').forEach(v => {
                    v.pause();
                    v.autoplay = false;
                });
            """)

            postRoot = detail_page.locator('div.x78zum5.xdt5ytf.x1iyjqo2.x5yr21d.x1n2onr6').first
            await postRoot.wait_for(state='visible')

            # Extract timestamp from post link first, picking the anchor whose text starts with a digit
            anchors = postRoot.locator('a[role="link"][href*="/videos/"], a[role="link"][href*="/watch/"]')
            post_timestamp_text = ''
            post_timestamp_dt = None
            count = await anchors.count()
            for idx in range(count):
                text = (await anchors.nth(idx).text_content()).strip()
                if re.match(r'^\d+', text):
                    post_timestamp_text = text
                    # print(f"post_timestamp_text: {post_timestamp_text}")
                    post_timestamp_dt = self._parse_thai_timestamp(text)
                    break

            # DEBUG: check for video link presence with fallback to watch URL
            video_locator = postRoot.locator('a[href*="/videos/"], a[href*="/watch/"]')
            const_count = await video_locator.count()
            # print(f"[get_video_detail] video_link count: {const_count} | post_url: {post_url}")
            if const_count == 0:
                # print(f"[get_video_detail] No video link found on {post_url}")
                pass
            else:
                video_link = postRoot.locator('a[href*="/videos/"]').first
                # Ensure the video link is in view and overlays are disabled
                await video_link.scroll_into_view_if_needed()
                await detail_page.evaluate("""
                    // Disable pointer-events on any overlay that might intercept clicks or hovers
                    document.querySelectorAll('div[role="banner"], div.x1gfrnbc, div[role="tooltip"]').forEach(el => {
                        el.style.pointerEvents = 'none';
                        el.style.display = 'none';
                    });
                """)
                # Retry hover to trigger tooltip
                tooltip_span = detail_page.locator('div[role="tooltip"] span.x193iq5w').first
                hover_success = False
                for attempt in range(3):
                    try:
                        await video_link.hover(timeout=5000, force=True)
                        await detail_page.wait_for_timeout(1000)
                        if await tooltip_span.count():
                            hover_success = True
                            break
                    except Exception as e:
                        print(f"[get_video_detail] hover attempt {attempt + 1} failed: {e}")
                if not hover_success:
                    print(f"[get_post_detail] Tooltip hover failed after retries on {post_url}")
                    # Fallback: try clicking the link to reveal timestamp tooltip
                    try:
                        await video_link.click(force=True)
                        await detail_page.wait_for_timeout(1000)
                    except Exception as e:
                        print(f"[get_video_detail] fallback click failed: {e}")
                # Remove early exit: always continue, don't close and return None here
                if not await tooltip_span.count():
                    print(f"[get_post_detail] No tooltip after fallback on {post_url}")

                # Override with tooltip timestamp if available
                if await tooltip_span.count():
                    tooltip_text = (await tooltip_span.text_content()).strip()
                    if tooltip_text:
                        post_timestamp_text = tooltip_text
                        post_timestamp_dt = self._parse_thai_timestamp(tooltip_text)

            # Hide any visible timestamp tooltip so it doesn't block the "ดูเพิ่มเติม" button
            await detail_page.evaluate(
                "document.querySelectorAll('div[role=\"tooltip\"]').forEach(el => el.style.display = 'none');")
            await detail_page.mouse.move(0, 0)

            # # Extract story messages
            # # expand if needed
            # more_btn = postRoot.locator('div.x1gslohp >> div[role="button"][tabindex="0"]')
            # if await more_btn.count():
            #     btn = more_btn.first
            #     try:
            #         # Attempt direct JS click to bypass visibility issues
            #         await detail_page.evaluate("btn => btn.click()", btn)
            #     except Exception:
            #         try:
            #             # Fallback to forced click
            #             await btn.click(force=True)
            #         except Exception:
            #             print(f"[get_post_detail] Could not click 'ดูเพิ่มเติม' button on {post_url}")
            #     finally:
            #         await detail_page.wait_for_timeout(500)
            #
            # # find all the lines of text in the description region
            # message_elements = await postRoot.locator(
            #     'div.xjkvuk6 >> div[dir="auto"]'
            # ).all()
            #
            # texts = []
            # for elem in message_elements:
            #     line = (await elem.inner_text()).strip()
            #     if line:
            #         texts.append(line)
            # post_content = "\n".join(texts)
            post_content = {}
            # Fallback to description if no content lines found
            if not post_content and description:
                post_content = description

            # Comment count and watch count (no share count for video posts)
            comment_count = 0
            watch_count = None
            try:
                stats_bar = postRoot.locator(
                    'div.x6s0dn4.xi81zsa.x78zum5.x6prxxf.x13a6bvl.xvq8zen.xdj266r.xat24cr.x1c1uobl.xyri2b.x80vd3b.x1q0q8m5.xso031l.x1diwwjn.xbmvrgn.x10b6aqq.x1yrsyyn'
                )

                # Fallback for watch count
                watch_elem = stats_bar.locator('span._26fq span.x193iq5w').first
                if await watch_elem.count():
                    raw_watch = (await watch_elem.text_content()).strip()
                    watch_match = re.search(r'([\d\.,]+\s*(?:พัน|หมื่น|แสน|ล้าน)?)', raw_watch)
                    if watch_match:
                        watch_count = self._parse_thai_number(watch_match.group(1))

                # Fallback for comment count: look for the comment-button span
                comment_elem_alt = stats_bar.locator('div[role="button"] span.xdj266r').first
                if await comment_elem_alt.count():
                    raw_comment = (await comment_elem_alt.text_content()).strip()
                    comment_match = re.search(r'([\d\.,]+\s*(?:พัน|หมื่น|แสน|ล้าน)?)', raw_comment)
                    if comment_match:
                        comment_count = self._parse_thai_number(comment_match.group(1))
            except Exception:
                pass

            # Extract just the ID portion from the URL
            if '/posts/' in post_url:
                raw_id = post_url.split('/posts/')[1]
            elif '/videos/' in post_url:
                raw_id = post_url.split('/videos/')[1]
            else:
                raw_id = post_url
            post_id = raw_id.split('?')[0].strip('/')
            # Construct Facebook watch URL
            video_url = post_url
            # Determine post type
            post_type = 'video' if '/videos/' in post_url else 'post'

            # print(f"[get_post_detail] Successfully fetched details for {post_id}")
            await detail_page.close()

            return {
                'post_url': post_url,
                "post_id": post_id,
                "post_type": post_type,
                "post_timestamp_text": post_timestamp_text,
                "post_timestamp_dt": post_timestamp_dt,
                "post_content": post_content,
                "video_thumbnail": video_thumbnail,
                "video_url": video_url,
                # "reactions": reactions,
                "comment_count": comment_count,
                "watch_count": watch_count,
                # "comments": comments,
            }

        except Exception as e:
            print(f"[get_post_detail] ERROR for {post_url}: {e}")
            try:
                await detail_page.close()
            except:
                pass
            return None

    # async def _get_post_comments(self, page: Page) -> list:
    #     comments = []
    #     try:
    #         # Wait for and click the comments sort button
    #         await page.wait_for_selector('div.x6s0dn4.x78zum5.xdj266r.x14z9mp.xat24cr.x1lziwak.xe0p6wg', timeout=10000)
    #         await page.click('div.x6s0dn4.x78zum5.xdj266r.x14z9mp.xat24cr.x1lziwak.xe0p6wg')
    #         # Open the full comments dialog
    #         await page.click('div[role="menuitem"] >> text="ความคิดเห็นทั้งหมด"')
    #         # 1) Wait for the comments dialog Locator to appear
    #         dialog = page.locator('div[role="dialog"]').first
    #         await dialog.wait_for(timeout=10000)
    #         # Find the actual scrollable element inside the dialog via computed styles
    #         dialog_handle = await dialog.element_handle()
    #         scrollable_handle = await page.evaluate_handle(
    #             """dialog => {
    #                 const divs = Array.from(dialog.querySelectorAll('div'));
    #                 return divs.find(el => {
    #                     const style = window.getComputedStyle(el);
    #                     return style.overflowY === 'auto' || style.overflowY === 'scroll';
    #                 }) || dialog;
    #             }""",
    #             dialog_handle
    #         )
    #         # Scroll until no new comments load
    #         prev_count = 0
    #         while True:
    #             # Count loaded top-level comments
    #             curr_count = await page.locator('div[role="article"][aria-label^="ความคิดเห็นจาก"]').count()
    #             if curr_count > prev_count:
    #                 prev_count = curr_count
    #                 await scrollable_handle.evaluate("el => el.scrollTo(0, el.scrollHeight)")
    #                 await page.wait_for_timeout(1000)
    #             else:
    #                 break
    #     except Exception as e:
    #         print(f"[get_post_comments] Failed to open comments menu: {e}")
    #         return comments
    #
    #     # Wait for at least one top-level comment to load
    #     try:
    #         await page.wait_for_selector('div[role="article"][aria-label^="ความคิดเห็นจาก"]', timeout=10000)
    #     except Exception:
    #         # No top-level comments present; exit gracefully
    #         return []
    #
    #     # Select only main comment containers (exclude replies)
    #     comment_divs = await page.locator('div[role="article"][aria-label^="ความคิดเห็นจาก"]').all()
    #     for div in comment_divs:
    #         try:
    #             image_element = div.locator('svg image').first
    #             profile_img = await image_element.get_attribute('xlink:href')
    #
    #             # Extract commenter name and profile URL from the visible name link
    #             visible_links = div.locator('a[aria-hidden="false"]')
    #             if await visible_links.count():
    #                 name_link = visible_links.first
    #             else:
    #                 name_link = div.locator('a').first
    #             await name_link.wait_for(timeout=5000)
    #             profile_name = (await name_link.text_content()).strip()
    #             href = await name_link.get_attribute('href')
    #             profile_url = href.split('?')[0] if href else None
    #
    #             # Extract just the comment message
    #             # Look for the nested div with dir="auto" inside the comment body
    #             msg_locator = div.locator('div.x1lliihq.xjkvuk6.x1iorvi4 div[dir="auto"]').first
    #             if await msg_locator.count():
    #                 comment_text = (await msg_locator.inner_text()).strip()
    #             else:
    #                 comment_text = ''
    #
    #             # Hover to reveal timestamp tooltip
    #             time_link = div.locator('a[href*="?comment_id="]').last
    #             try:
    #                 await time_link.hover()
    #                 await page.wait_for_selector('div[role="tooltip"]', timeout=5000)
    #                 tooltip = page.locator('div[role="tooltip"]').first
    #                 time_stamp_text = (await tooltip.inner_text()).strip()
    #                 time_stamp_dt = self._parse_thai_timestamp(time_stamp_text)
    #             except:
    #                 time_stamp_text = None
    #                 time_stamp_dt = None
    #
    #             comments.append({
    #                 "user_name": profile_name,
    #                 "profile_url": profile_url,
    #                 "profile_img": profile_img,
    #                 "comment_text": comment_text,
    #                 "time_stamp_text": time_stamp_text,
    #                 "time_stamp_dt": time_stamp_dt,
    #             })
    #         except Exception as e:
    #             print(f"[get_post_comments] Error extracting a comment: {e}")
    #             print(page.url)
    #             continue
    #
    #     return comments

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

                    video_page_url = f"{self.page_url.rstrip('/')}/live_videos"
                    await self.page.goto(video_page_url)
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
                # Wait for the video card selector to appear before collecting posts
                await self.page.wait_for_selector('div.x1l90r2v.x12qybmz', timeout=10000)
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
                    self._get_post_detail(self.context, post_url, thumbnail, description)
                    for (post_url, _, thumbnail, description) in batch_posts
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
    scraper = FBLiveScraperAsync(
        cookie_file="cookie.json",
        headless=False,
        page_url="https://www.facebook.com/mealmateTH",
        # cutoff_dt=datetime(2025, 5, 1, 0, 0),
        cutoff_dt=None,
        batch_size=10
    )
    scraper.start()