from playwright.sync_api import sync_playwright
import json
import time
import re
from datetime import datetime
import random

def get_tiktok_posts(url):
    def extract_username(url):
        import re
        match = re.search(r"tiktok\.com/@([\w\.\-]+)", url)
        return match.group(1) if match else None

    username = extract_username(url)
    if not username:
        print("❌ ไม่สามารถแยก username จาก URL")
        return []

    # ปรับ run ให้ใช้ dynamic URL แทน
    return run_with_target_url(f"https://www.tiktok.com/@{username}")

def clean_number(text):
    """Convert shorthand TikTok numbers (k, m) to integers"""
    if not text:
        return 0
    text = text.replace(',', '').strip().lower()
    if 'k' in text:
        return int(float(text.replace('k', '')) * 1000)
    elif 'm' in text:
        return int(float(text.replace('m', '')) * 1000000)
    return int(text) if text.isdigit() else 0


def load_cookies(context, cookies_file):
    """Load cookies into Playwright context"""
    with open(cookies_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    for cookie in cookies:
        if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
            cookie['sameSite'] = 'Lax'
    context.add_cookies(cookies)


def check_captcha_exists(page):
    """ตรวจสอบว่ามี CAPTCHA หรือไม่ โดยไม่รอนาน"""
    try:
        captcha_selectors = [
            '[id*="captcha"]',
            '[class*="captcha"]',
            '.captcha',
            '[data-testid*="captcha"]',
            '.secsdk-captcha-wrapper',
            '#captcha-verify',
            '.captcha-container'
        ]

        for selector in captcha_selectors:
            if page.query_selector(selector):
                return True
        return False
    except:
        return False


def solve_captcha(page, max_wait_time=30):
    """Handle CAPTCHA with timeout - ไม่รอนานเกินไป"""
    if not check_captcha_exists(page):
        return True

    try:
        print("🤖 พบ CAPTCHA - กำลังรอการแก้ไข...")
        print(f"⏳ จะรอสูงสุด {max_wait_time} วินาที หากไม่แก้จะข้ามไป")

        start_time = time.time()

        # รอให้ user แก้ captcha หรือ timeout
        while time.time() - start_time < max_wait_time:
            if not check_captcha_exists(page):
                print("✅ CAPTCHA ผ่านแล้ว")
                time.sleep(2)
                return True
            time.sleep(1)

        print(f"⚠️ CAPTCHA timeout หลัง {max_wait_time} วินาที - ดำเนินการต่อ")
        return False

    except Exception as e:
        print(f"❌ Error handling CAPTCHA: {e}")
        return False


def safe_navigate(page, url, retries=3):
    """Navigate with CAPTCHA handling and retries"""
    for attempt in range(retries):
        try:
            print(f"🔄 กำลังเข้าสู่: {url} (ครั้งที่ {attempt + 1})")
            page.goto(url, timeout=30000)

            # รอให้หน้าโหลด
            page.wait_for_load_state('domcontentloaded', timeout=15000)
            time.sleep(2)

            # ตรวจสอบ CAPTCHA แบบรวดเร็ว
            if check_captcha_exists(page):
                print("🤖 พบ CAPTCHA - พยายามแก้ไข...")
                solved = solve_captcha(page, max_wait_time=20)
                if not solved:
                    if attempt < retries - 1:
                        print("🔄 ลองใหม่...")
                        time.sleep(5)
                        continue
                    else:
                        print("⚠️ ไม่สามารถแก้ CAPTCHA ได้ - ข้ามไป")
                        return False

            return True

        except Exception as e:
            print(f"❌ Navigation error (attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                time.sleep(5)
            else:
                return False

    return False


def get_post_content(page):
    """หา post content พร้อมแฮชแท็กครบถ้วน - ไม่ต้องไปกด sidebar"""

    # ตรวจสอบ CAPTCHA ก่อน
    if check_captcha_exists(page):
        print("⚠️ มี CAPTCHA ในหน้า content - ข้าม")
        return "ไม่สามารถดึงข้อมูลได้ (CAPTCHA)"

    time.sleep(2)

    # เลื่อนเพื่อให้ description แสดงครบ (เลื่อนน้อยลง)
    try:
        page.evaluate("window.scrollTo(0, 150)")
        time.sleep(1)

        # หาปุ่ม "See more" หรือ "ดูเพิ่มเติม" ใน description area เท่านั้น
        description_area = page.query_selector('[data-e2e="browse-video-desc"], [data-e2e="video-desc"]')
        if description_area:
            expand_buttons = description_area.query_selector_all('button, span')
            for button in expand_buttons:
                try:
                    text = button.inner_text().lower()
                    if 'more' in text or 'เพิ่มเติม' in text or '...' in text:
                        button.click()
                        time.sleep(1)
                        break
                except:
                    pass
    except:
        pass

    content = ""

    # Method 1: หาจาก __UNIVERSAL_DATA_FOR_REHYDRATION__
    try:
        universal_data = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script');
                for (let script of scripts) {
                    const text = script.textContent;
                    if (text && text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                        try {
                            const match = text.match(/window\['__UNIVERSAL_DATA_FOR_REHYDRATION__'\]\s*=\s*({.+})/);
                            if (match) {
                                const data = JSON.parse(match[1]);
                                const traverse = (obj) => {
                                    if (typeof obj === 'object' && obj !== null) {
                                        if (obj.desc || obj.description) {
                                            return obj.desc || obj.description;
                                        }
                                        for (let key in obj) {
                                            if (key === 'desc' || key === 'description') {
                                                return obj[key];
                                            }
                                            const result = traverse(obj[key]);
                                            if (result) return result;
                                        }
                                    }
                                    return null;
                                };
                                return traverse(data);
                            }
                        } catch (e) {}
                    }
                }
                return null;
            }
        """)

        if universal_data and len(universal_data.strip()) > 5:
            content = universal_data.strip()
    except:
        pass

    # Method 2: หาจาก SIGI_STATE
    if not content:
        try:
            sigi_data = page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script');
                    for (let script of scripts) {
                        const text = script.textContent;
                        if (text && text.includes('SIGI_STATE')) {
                            try {
                                const match = text.match(/window\['SIGI_STATE'\]\s*=\s*({.+?});/);
                                if (match) {
                                    const data = JSON.parse(match[1]);
                                    if (data.ItemModule) {
                                        for (let key in data.ItemModule) {
                                            const item = data.ItemModule[key];
                                            if (item && item.desc) {
                                                return item.desc;
                                            }
                                        }
                                    }
                                }
                            } catch (e) {}
                        }
                    }
                    return null;
                }
            """)

            if sigi_data and len(sigi_data.strip()) > 5:
                content = sigi_data.strip()
        except:
            pass

    # Method 3: หาจาก DOM elements - ไม่ต้องแก้ hidden elements
    if not content:
        try:
            selectors = [
                '[data-e2e="browse-video-desc"]',
                '[data-e2e="video-desc"]',
                'h1[data-e2e="browse-video-title"]',
                'div[class*="DivVideoInfoContainer"] div[class*="DivText"]',
                'div[class*="video-meta-caption"]',
                'div[data-testid="video-description"]',
                '[class*="StyledVideoDescription"]',
                '[class*="video-description"]',
                'div[class*="browse-video-desc"]'
            ]

            for selector in selectors:
                elements = page.query_selector_all(selector)
                for elem in elements:
                    try:
                        full_text = elem.inner_text().strip()

                        if full_text and len(full_text) > len(content) and len(full_text) > 10:
                            unwanted = ['Following', 'Follower', 'Like', 'Share', 'Comment', 'Subscribe']
                            if not any(word in full_text for word in unwanted):
                                content = full_text
                                break
                    except:
                        continue

                if content:
                    break
        except:
            pass

    return content if content else "ไม่พบเนื้อหา"


def get_saved_count(page):
    """หาจำนวน saved/bookmark - แก้ไขตาม selector ที่ถูกต้อง"""

    # ตรวจสอบ CAPTCHA ก่อน
    if check_captcha_exists(page):
        return 0

    # รอสักครู่ให้ข้อมูลโหลด
    time.sleep(1)

    try:
        # Method 1: หาจาก data-e2e="bookmark-count" หรือ "collect-count"
        selectors = [
            'strong[data-e2e="bookmark-count"]',
            'strong[data-e2e="collect-count"]',
            'strong[data-e2e="undefined-count"]',  # บางครั้ง TikTok ใช้ undefined
            '[data-e2e*="bookmark"] strong',
            '[data-e2e*="collect"] strong',
            '[data-e2e*="save"] strong'
        ]

        for selector in selectors:
            elements = page.query_selector_all(selector)
            for elem in elements:
                try:
                    text = elem.inner_text().strip()
                    if text and text != '0':
                        return clean_number(text)
                except:
                    continue

        # Method 2: หาจาก JavaScript data
        saved_from_js = page.evaluate("""
            () => {
                // หาจาก SIGI_STATE
                const scripts = document.querySelectorAll('script');
                for (let script of scripts) {
                    const text = script.textContent;
                    if (text && text.includes('SIGI_STATE')) {
                        try {
                            const match = text.match(/window\['SIGI_STATE'\]\s*=\s*({.+?});/);
                            if (match) {
                                const data = JSON.parse(match[1]);
                                if (data.ItemModule) {
                                    for (let key in data.ItemModule) {
                                        const item = data.ItemModule[key];
                                        if (item && item.stats) {
                                            return item.stats.collectCount || item.stats.bookmarkCount || 0;
                                        }
                                    }
                                }
                            }
                        } catch (e) {}
                    }
                }

                // หาจาก __UNIVERSAL_DATA_FOR_REHYDRATION__
                for (let script of scripts) {
                    const text = script.textContent;
                    if (text && text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                        try {
                            const match = text.match(/window\['__UNIVERSAL_DATA_FOR_REHYDRATION__'\]\s*=\s*({.+})/);
                            if (match) {
                                const data = JSON.parse(match[1]);
                                const traverse = (obj) => {
                                    if (typeof obj === 'object' && obj !== null) {
                                        if (obj.collectCount !== undefined) return obj.collectCount;
                                        if (obj.bookmarkCount !== undefined) return obj.bookmarkCount;
                                        if (obj.saveCount !== undefined) return obj.saveCount;

                                        for (let key in obj) {
                                            const result = traverse(obj[key]);
                                            if (result !== null && result !== undefined) return result;
                                        }
                                    }
                                    return null;
                                };
                                const result = traverse(data);
                                return result || 0;
                            }
                        } catch (e) {}
                    }
                }

                return 0;
            }
        """)

        if saved_from_js > 0:
            return saved_from_js

    except Exception as e:
        print(f"❌ Error getting saved count: {e}")

    return 0


def get_timestamp(page):
    """หา timestamp ของโพสต์ที่ถูกต้อง"""

    # ตรวจสอบ CAPTCHA ก่อน
    if check_captcha_exists(page):
        return "ไม่สามารถดึงวันที่ได้ (CAPTCHA)"

    # Method 1: หาจาก __UNIVERSAL_DATA_FOR_REHYDRATION__
    try:
        timestamp_from_data = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script');
                for (let script of scripts) {
                    const text = script.textContent;
                    if (text && text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                        try {
                            const match = text.match(/window\['__UNIVERSAL_DATA_FOR_REHYDRATION__'\]\s*=\s*({.+})/);
                            if (match) {
                                const data = JSON.parse(match[1]);

                                const traverse = (obj) => {
                                    if (typeof obj === 'object' && obj !== null) {
                                        if (obj.createTime && typeof obj.createTime === 'number') {
                                            return obj.createTime;
                                        }
                                        for (let key in obj) {
                                            if (key === 'createTime' && typeof obj[key] === 'number') {
                                                return obj[key];
                                            }
                                            const result = traverse(obj[key]);
                                            if (result) return result;
                                        }
                                    }
                                    return null;
                                };

                                const createTime = traverse(data);
                                if (createTime && createTime > 1500000000) { // หลัง 2017
                                    const date = new Date(createTime * 1000);
                                    return date.toLocaleDateString('th-TH', {
                                        day: '2-digit',
                                        month: '2-digit', 
                                        year: 'numeric'
                                    });
                                }
                            }
                        } catch (e) {}
                    }
                }
                return null;
            }
        """)

        if timestamp_from_data:
            return timestamp_from_data
    except:
        pass

    # Method 2: หาจาก SIGI_STATE
    try:
        sigi_timestamp = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script');
                for (let script of scripts) {
                    const text = script.textContent;
                    if (text && text.includes('SIGI_STATE')) {
                        try {
                            const match = text.match(/window\['SIGI_STATE'\]\s*=\s*({.+?});/);
                            if (match) {
                                const data = JSON.parse(match[1]);

                                if (data.ItemModule) {
                                    for (let key in data.ItemModule) {
                                        const item = data.ItemModule[key];
                                        if (item && item.createTime && typeof item.createTime === 'number') {
                                            if (item.createTime > 1500000000) { // หลัง 2017
                                                const date = new Date(item.createTime * 1000);
                                                return date.toLocaleDateString('th-TH', {
                                                    day: '2-digit',
                                                    month: '2-digit',
                                                    year: 'numeric'
                                                });
                                            }
                                        }
                                    }
                                }
                            }
                        } catch (e) {}
                    }
                }
                return null;
            }
        """)

        if sigi_timestamp:
            return sigi_timestamp
    except:
        pass

    # Method 3: หาจาก page source
    try:
        page_source = page.content()

        patterns = [
            r'"createTime"[:\s]*"?(\d{10})"?',
            r'"create_time"[:\s]*"?(\d{10})"?',
            r'"publishTime"[:\s]*"?(\d{10})"?'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, page_source)
            for match in matches:
                timestamp = int(match)
                if 1500000000 <= timestamp <= int(time.time()):
                    dt = datetime.fromtimestamp(timestamp)
                    return dt.strftime('%d/%m/%Y')
    except:
        pass

    # Method 4: หาจาก DOM elements
    try:
        dom_timestamp = page.evaluate("""
            () => {
                const timeElements = document.querySelectorAll('time, [datetime]');
                for (let elem of timeElements) {
                    const datetime = elem.getAttribute('datetime');
                    if (datetime) {
                        try {
                            const date = new Date(datetime);
                            if (date.getFullYear() >= 2017 && date.getFullYear() <= new Date().getFullYear()) {
                                return date.toLocaleDateString('th-TH', {
                                    day: '2-digit',
                                    month: '2-digit',
                                    year: 'numeric'
                                });
                            }
                        } catch (e) {}
                    }
                }

                const allElements = document.querySelectorAll('*');
                for (let elem of allElements) {
                    const text = elem.textContent?.trim();
                    if (text && text.length < 50) {
                        const datePatterns = [
                            /(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})/,
                            /(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/
                        ];

                        for (let pattern of datePatterns) {
                            const match = text.match(pattern);
                            if (match) {
                                return text;
                            }
                        }
                    }
                }

                return null;
            }
        """)

        if dom_timestamp:
            return dom_timestamp
    except:
        pass

    return "ไม่พบวันที่"


def safe_get_metrics(page):
    """ดึงข้อมูล metrics แบบปลอดภัย"""

    # ตรวจสอบ CAPTCHA ก่อน
    if check_captcha_exists(page):
        print("⚠️ มี CAPTCHA - ใช้ค่าเริ่มต้น")
        return 0, 0, 0

    try:
        like_elem = page.query_selector('strong[data-e2e="like-count"]')
        reaction = clean_number(like_elem.inner_text()) if like_elem else 0

        comment_elem = page.query_selector('strong[data-e2e="comment-count"]')
        comment = clean_number(comment_elem.inner_text()) if comment_elem else 0

        share_elem = page.query_selector('strong[data-e2e="share-count"]')
        shared = clean_number(share_elem.inner_text()) if share_elem else 0

        return reaction, comment, shared
    except:
        return 0, 0, 0


def human_like_delay():
    """สร้าง delay แบบมนุษย์"""
    return random.uniform(2, 5)


def run_with_target_url(target_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1366, 'height': 768}
        )
        load_cookies(context, 'C:/Users/blackbook/Desktop/tiktok_cookies.json')
        page = context.new_page()

        # ไปที่โปรไฟล์ด้วย safe navigation
        if not safe_navigate(page, "https://www.tiktok.com/@atlascat_official"):
            print("❌ ไม่สามารถเข้าโปรไฟล์ได้")
            browser.close()
            return []

        # Scroll โหลดโพสต์ด้วยความระมัดระวัง
        for i in range(8):
            try:
                page.mouse.wheel(0, 2000)  # เลื่อนน้อยลง
                time.sleep(human_like_delay())

                # ตรวจสอบ CAPTCHA แบบรวดเร็ว - ถ้าเจอก็ข้าม
                if check_captcha_exists(page):
                    print(f"⚠️ พบ CAPTCHA ขณะ scroll ครั้งที่ {i + 1} - ข้าม")
                    break
            except:
                break

        posts = page.query_selector_all('div[data-e2e="user-post-item"]')
        all_posts = []

        print(f"🔍 กำลังเก็บข้อมูลโพสต์จากหน้าโปรไฟล์...")

        for i, post in enumerate(posts):
            try:
                link_tag = post.query_selector('a')
                post_url = link_tag.get_attribute('href') if link_tag else ''

                if post_url and not post_url.startswith('http'):
                    post_url = 'https://www.tiktok.com' + post_url

                thumb = post.query_selector('img')
                post_thumbnail = thumb.get_attribute('src') if thumb else ''

                if post_thumbnail and not post_thumbnail.startswith('http'):
                    post_thumbnail = 'https:' + post_thumbnail if post_thumbnail.startswith('//') else post_thumbnail

                views_elem = post.query_selector('strong[data-e2e="video-views"]')
                views = clean_number(views_elem.inner_text()) if views_elem else 0

                all_posts.append({
                    "post_url": post_url,
                    "post_thumbnail": post_thumbnail,
                    "views": views
                })

                print(f"📋 โพสต์ที่ {i + 1}: Views: {views:,}")
                print(f"🔗 URL: {post_url}")
                print(f"🖼️ Thumbnail: {post_thumbnail}")
                print("-" * 50)

            except Exception as e:
                print(f"❌ Error collecting post list: {e}")

        print(f"✅ พบโพสต์ทั้งหมด {len(all_posts)} รายการ")
        total_views = sum(post['views'] for post in all_posts)
        print(f"📊 รวม Views ทั้งหมด: {total_views:,}")
        print("=" * 80)

        # เข้าแต่ละโพสต์
        successful_posts = 0
        for i, post in enumerate(all_posts):
            try:
                print(f"🔄 กำลังประมวลผลโพสต์ที่ {i + 1}/{len(all_posts)}")

                # ใช้ safe navigation
                if not safe_navigate(page, post["post_url"]):
                    print(f"⚠️ ไม่สามารถเข้าโพสต์ที่ {i + 1} ได้ - ข้ามไป")
                    # เพิ่มข้อมูลเริ่มต้น
                    post.update({
                        "post_content": "ไม่สามารถดึงข้อมูลได้ (Navigation Error)",
                        "timestamp": "ไม่พบวันที่",
                        "reaction": 0,
                        "comment": 0,
                        "shared": 0,
                        "saved": 0
                    })
                    continue

                # เก็บข้อมูล - แต่ละฟังก์ชันจะตรวจสอบ CAPTCHA เอง
                post_content = get_post_content(page)
                timestamp = get_timestamp(page)
                reaction, comment, shared = safe_get_metrics(page)
                saved = get_saved_count(page)

                # รวมผลลัพธ์
                post.update({
                    "post_content": post_content,
                    "timestamp": timestamp,
                    "reaction": reaction,
                    "comment": comment,
                    "shared": shared,
                    "saved": saved
                })

                # แสดงผลลัพธ์
                print(f"📝 Content: {post_content}")
                print(f"🕐 Timestamp: {timestamp}")
                print(f"👁️ Views: {post['views']:,}")
                print(f"❤️ Likes: {reaction:,}")
                print(f"💬 Comments: {comment:,}")
                print(f"📤 Shares: {shared:,}")
                print(f"🔖 Saved: {saved:,}")
                print(f"🔗 URL: {post['post_url']}")
                print(f"🖼️ Thumbnail: {post['post_thumbnail']}")
                print("=" * 80)

                successful_posts += 1
                time.sleep(human_like_delay())

            except Exception as e:
                print(f"❌ Error in detail page {i + 1}: {e}")
                # เพิ่มข้อมูลเริ่มต้นแม้เกิด error
                post.update({
                    "post_content": "ไม่สามารถดึงข้อมูลได้ (Error)",
                    "timestamp": "ไม่พบวันที่",
                    "reaction": 0,
                    "comment": 0,
                    "shared": 0,
                    "saved": 0
                })
                continue

        # บันทึกผลลัพธ์
        with open('tiktok_data.json', 'w', encoding='utf-8') as f:
            json.dump(all_posts, f, ensure_ascii=False, indent=2)

        print(f"🎉 เสร็จสิ้น! บันทึกข้อมูล {len(all_posts)} โพสต์แล้ว")
        print(f"✅ ดึงข้อมูลสำเร็จ {successful_posts} โพสต์ จากทั้งหมด {len(all_posts)} โพสต์")

        # แสดงตัวอย่างข้อมูลที่จะใช้กับ database
        print("\n📄 ตัวอย่างข้อมูลสำหรับ Database:")
        if all_posts:
            sample = all_posts[0]
            print(json.dumps(sample, ensure_ascii=False, indent=2))

        browser.close()
        return all_posts


if __name__ == "__main__":
    data = run()