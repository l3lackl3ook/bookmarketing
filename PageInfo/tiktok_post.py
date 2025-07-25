# แก้ไขปัญหาใน tiktok_post.py

from playwright.sync_api import sync_playwright
import json
import time
import re
from datetime import datetime
import random
import os
import logging
from typing import List, Dict, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TikTokPostScraper:
    """
    Enhanced TikTok post scraper class designed for Django integration
    Can scrape posts from any TikTok profile URL dynamically with improved error handling
    """

    def __init__(self, cookies_file: str = None, headless: bool = False, timeout: int = 30000):
        self.cookies_file = cookies_file
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    def __enter__(self):
        """Context manager entry"""
        self.start_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close_browser()

    def start_browser(self):
        """Initialize browser with optimized settings"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-extensions',
                    '--disable-default-apps'
                ]
            )

            self.context = self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1366, 'height': 768},
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
            )

            # Load cookies if available
            if self.cookies_file and os.path.exists(self.cookies_file):
                self.load_cookies()

            self.page = self.context.new_page()
            logger.info("Browser initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    def close_browser(self):
        """Close browser and playwright safely"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def load_cookies(self):
        """Load cookies from file with error handling"""
        try:
            with open(self.cookies_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            # Sanitize cookies
            for cookie in cookies:
                if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                    cookie['sameSite'] = 'Lax'

            self.context.add_cookies(cookies)
            logger.info(f"Loaded {len(cookies)} cookies from {self.cookies_file}")

        except Exception as e:
            logger.warning(f"Could not load cookies from {self.cookies_file}: {e}")

    @staticmethod
    def clean_number(text: str) -> int:
        """Convert TikTok shorthand numbers (k, m, b) to integers"""
        if not text:
            return 0

        text = str(text).replace(',', '').strip().lower()

        try:
            if 'k' in text:
                return int(float(text.replace('k', '')) * 1000)
            elif 'm' in text:
                return int(float(text.replace('m', '')) * 1000000)
            elif 'b' in text:
                return int(float(text.replace('b', '')) * 1000000000)
            else:
                # Remove any non-digit characters
                clean_text = re.sub(r'[^\d]', '', text)
                return int(clean_text) if clean_text.isdigit() else 0
        except (ValueError, TypeError):
            return 0

    def check_captcha_exists(self) -> bool:
        """Check if CAPTCHA is present on the page"""
        try:
            captcha_selectors = [
                '[id*="captcha"]',
                '[class*="captcha"]',
                '.captcha',
                '[data-testid*="captcha"]',
                '.secsdk-captcha-wrapper',
                '#captcha-verify',
                '.captcha-container',
                '[class*="verify"]'
            ]

            for selector in captcha_selectors:
                if self.page.query_selector(selector):
                    return True
            return False

        except Exception:
            return False

    def solve_captcha(self, max_wait_time: int = 30) -> bool:
        """Handle CAPTCHA with timeout - skip and continue if CAPTCHA detected"""
        if not self.check_captcha_exists():
            return True

        try:
            logger.warning(f"⚠️ พบ CAPTCHA - พยายามข้าม...")
            start_time = time.time()

            while time.time() - start_time < max_wait_time:
                if not self.check_captcha_exists():
                    logger.info("✅ CAPTCHA หายไปแล้ว - ดำเนินการต่อ")
                    time.sleep(2)
                    return True
                time.sleep(1)

            logger.warning(f"⚠️ CAPTCHA ยังคงอยู่ - ดำเนินการต่อ")
            return False

        except Exception as e:
            logger.error(f"❌ Error handling CAPTCHA: {e}")
            return False

    def safe_navigate(self, url: str, retries: int = 2) -> bool:
        """Navigate with CAPTCHA handling and retries"""
        for attempt in range(retries):
            try:
                logger.info(f"🔄 Navigating to: {url} (attempt {attempt + 1})")
                self.page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)

                # Wait for page to stabilize
                time.sleep(random.uniform(2, 4))

                if self.check_captcha_exists():
                    logger.info("🤖 CAPTCHA detected during navigation")
                    if not self.solve_captcha(max_wait_time=15):
                        logger.warning("⚠️ CAPTCHA persists - will use default values")
                        return False

                return True

            except Exception as e:
                logger.error(f"❌ Navigation error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(5)
                else:
                    return False

        return False

    def get_post_content(self) -> str:
        """Extract post content with enhanced timeout handling"""
        if self.check_captcha_exists():
            logger.warning("⚠️ CAPTCHA detected - skipping timestamp extraction")
            return "ไม่สามารถดึงข้อมูลได้ (CAPTCHA)"

        try:
            # Wait for content to load with timeout
            logger.info("🔍 Attempting to get content (attempt 1)")
            content_loaded = False
            max_wait = 15  # seconds
            start_time = time.time()

            while time.time() - start_time < max_wait:
                # Check if any content is available
                content_elements = self.page.query_selector_all(
                    '[data-e2e="browse-video-desc"], [data-e2e="video-desc"], h1[data-e2e="browse-video-title"]'
                )

                if content_elements:
                    content_loaded = True
                    break

                time.sleep(1)

            if not content_loaded:
                logger.warning(f"⚠️ Content load timeout after {max_wait}s")
                # Continue anyway and try to extract what we can

            # Scroll to expand description
            try:
                self.page.evaluate("window.scrollTo(0, 150)")
                time.sleep(1)

                # Try to click "See more" buttons
                description_area = self.page.query_selector('[data-e2e="browse-video-desc"], [data-e2e="video-desc"]')
                if description_area:
                    expand_buttons = description_area.query_selector_all('button, span')
                    for button in expand_buttons[:3]:
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

            # Method 1: Extract from __UNIVERSAL_DATA_FOR_REHYDRATION__
            try:
                universal_data = self.page.evaluate("""
                    () => {
                        const scripts = document.querySelectorAll('script');
                        for (let script of scripts) {
                            const text = script.textContent;
                            if (text && text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                                try {
                                    const match = text.match(/window\\['__UNIVERSAL_DATA_FOR_REHYDRATION__'\\]\\s*=\\s*({.+})/);
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

                if universal_data and len(str(universal_data).strip()) > 5:
                    content = str(universal_data).strip()
            except:
                pass

            # Method 2: Extract from SIGI_STATE
            if not content:
                try:
                    sigi_data = self.page.evaluate("""
                        () => {
                            const scripts = document.querySelectorAll('script');
                            for (let script of scripts) {
                                const text = script.textContent;
                                if (text && text.includes('SIGI_STATE')) {
                                    try {
                                        const match = text.match(/window\\['SIGI_STATE'\\]\\s*=\\s*({.+?});/);
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

                    if sigi_data and len(str(sigi_data).strip()) > 5:
                        content = str(sigi_data).strip()
                except:
                    pass

            # Method 3: Extract from DOM elements
            if not content:
                try:
                    logger.info("✅ Content found via DOM elements")
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
                        elements = self.page.query_selector_all(selector)
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

        except Exception as e:
            logger.error(f"❌ Error getting content: {e}")
            return "ไม่สามารถดึงข้อมูลได้ (Error)"

    def get_saved_count(self) -> int:
        """Extract saved/bookmark count with multiple methods"""
        if self.check_captcha_exists():
            return 0

        time.sleep(1)

        try:
            # Method 1: DOM selectors
            selectors = [
                'strong[data-e2e="bookmark-count"]',
                'strong[data-e2e="collect-count"]',
                'strong[data-e2e="undefined-count"]',
                '[data-e2e*="bookmark"] strong',
                '[data-e2e*="collect"] strong',
                '[data-e2e*="save"] strong'
            ]

            for selector in selectors:
                elements = self.page.query_selector_all(selector)
                for elem in elements:
                    try:
                        text = elem.inner_text().strip()
                        if text and text != '0':
                            return self.clean_number(text)
                    except:
                        continue

            # Method 2: JavaScript data extraction
            saved_from_js = self.page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script');

                    // Try SIGI_STATE first
                    for (let script of scripts) {
                        const text = script.textContent;
                        if (text && text.includes('SIGI_STATE')) {
                            try {
                                const match = text.match(/window\\['SIGI_STATE'\\]\\s*=\\s*({.+?});/);
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

                    // Try __UNIVERSAL_DATA_FOR_REHYDRATION__
                    for (let script of scripts) {
                        const text = script.textContent;
                        if (text && text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                            try {
                                const match = text.match(/window\\['__UNIVERSAL_DATA_FOR_REHYDRATION__'\\]\\s*=\\s*({.+})/);
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
            logger.error(f"❌ Error getting saved count: {e}")

        return 0

    def get_timestamp(self) -> Tuple[str, Optional[int], Optional[str]]:
        """
        Extract post timestamp with multiple methods
        Returns: (formatted_date, unix_timestamp, iso_string)
        """
        if self.check_captcha_exists():
            logger.warning("⚠️ CAPTCHA detected - skipping timestamp extraction")
            return "ไม่สามารถดึงวันที่ได้ (CAPTCHA)", None, None

        # Method 1: Extract from __UNIVERSAL_DATA_FOR_REHYDRATION__
        try:
            timestamp_data = self.page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script');
                    for (let script of scripts) {
                        const text = script.textContent;
                        if (text && text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                            try {
                                const match = text.match(/window\\['__UNIVERSAL_DATA_FOR_REHYDRATION__'\\]\\s*=\\s*({.+})/);
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
                                    if (createTime && createTime > 1500000000) {
                                        return {
                                            unix: createTime,
                                            formatted: new Date(createTime * 1000).toLocaleDateString('th-TH', {
                                                day: '2-digit',
                                                month: '2-digit', 
                                                year: 'numeric'
                                            }),
                                            iso: new Date(createTime * 1000).toISOString()
                                        };
                                    }
                                }
                            } catch (e) {}
                        }
                    }
                    return null;
                }
            """)

            if timestamp_data:
                return timestamp_data['formatted'], timestamp_data['unix'], timestamp_data['iso']
        except:
            pass

        # Method 2: Extract from SIGI_STATE
        try:
            sigi_timestamp_data = self.page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script');
                    for (let script of scripts) {
                        const text = script.textContent;
                        if (text && text.includes('SIGI_STATE')) {
                            try {
                                const match = text.match(/window\\['SIGI_STATE'\\]\\s*=\\s*({.+?});/);
                                if (match) {
                                    const data = JSON.parse(match[1]);

                                    if (data.ItemModule) {
                                        for (let key in data.ItemModule) {
                                            const item = data.ItemModule[key];
                                            if (item && item.createTime && typeof item.createTime === 'number') {
                                                if (item.createTime > 1500000000) {
                                                    return {
                                                        unix: item.createTime,
                                                        formatted: new Date(item.createTime * 1000).toLocaleDateString('th-TH', {
                                                            day: '2-digit',
                                                            month: '2-digit',
                                                            year: 'numeric'
                                                        }),
                                                        iso: new Date(item.createTime * 1000).toISOString()
                                                    };
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

            if sigi_timestamp_data:
                return sigi_timestamp_data['formatted'], sigi_timestamp_data['unix'], sigi_timestamp_data['iso']
        except:
            pass

        # Method 3: Extract from page source using regex
        try:
            page_source = self.page.content()
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
                        return dt.strftime('%d/%m/%Y'), timestamp, dt.isoformat()
        except:
            pass

        # Method 4: Extract from DOM elements
        try:
            dom_timestamp_data = self.page.evaluate("""
                () => {
                    const timeElements = document.querySelectorAll('time, [datetime]');
                    for (let elem of timeElements) {
                        const datetime = elem.getAttribute('datetime');
                        if (datetime) {
                            try {
                                const date = new Date(datetime);
                                if (date.getFullYear() >= 2017 && date.getFullYear() <= new Date().getFullYear()) {
                                    return {
                                        unix: Math.floor(date.getTime() / 1000),
                                        formatted: date.toLocaleDateString('th-TH', {
                                            day: '2-digit',
                                            month: '2-digit',
                                            year: 'numeric'
                                        }),
                                        iso: date.toISOString()
                                    };
                                }
                            } catch (e) {}
                        }
                    }
                    return null;
                }
            """)

            if dom_timestamp_data:
                return dom_timestamp_data['formatted'], dom_timestamp_data['unix'], dom_timestamp_data['iso']
        except:
            pass

        return "ไม่พบวันที่", None, None

    def safe_get_metrics(self) -> Tuple[int, int, int]:
        """Extract likes, comments, and shares safely"""
        if self.check_captcha_exists():
            logger.warning("⚠️ CAPTCHA present - using default metrics")
            return 0, 0, 0

        try:
            # Try JavaScript extraction first
            js_metrics = self.page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script');
                    for (let script of scripts) {
                        const text = script.textContent;
                        if (text && text.includes('SIGI_STATE')) {
                            try {
                                const match = text.match(/window\\['SIGI_STATE'\\]\\s*=\\s*({.+?});/);
                                if (match) {
                                    const data = JSON.parse(match[1]);
                                    if (data.ItemModule) {
                                        for (let key in data.ItemModule) {
                                            const item = data.ItemModule[key];
                                            if (item && item.stats) {
                                                return {
                                                    likes: item.stats.diggCount || 0,
                                                    comments: item.stats.commentCount || 0,
                                                    shares: item.stats.shareCount || 0
                                                };
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

            if js_metrics:
                return js_metrics['likes'], js_metrics['comments'], js_metrics['shares']

        except Exception:
            pass

        # Fallback to DOM selectors
        try:
            like_elem = self.page.query_selector('strong[data-e2e="like-count"]')
            reaction = self.clean_number(like_elem.inner_text()) if like_elem else 0

            comment_elem = self.page.query_selector('strong[data-e2e="comment-count"]')
            comment = self.clean_number(comment_elem.inner_text()) if comment_elem else 0

            share_elem = self.page.query_selector('strong[data-e2e="share-count"]')
            shared = self.clean_number(share_elem.inner_text()) if share_elem else 0

            return reaction, comment, shared
        except:
            return 0, 0, 0

    def extract_username_from_url(self, profile_url: str) -> str:
        """Extract username from TikTok profile URL"""
        try:
            # Pattern to match @username in URL
            match = re.search(r'@([^/?]+)', profile_url)
            if match:
                return match.group(1)
        except Exception:
            pass
        return "unknown"

    def human_like_delay(self) -> float:
        """Generate human-like delay"""
        return random.uniform(2, 5)

    def scroll_to_load_all_posts(self, profile_url: str, max_scroll_rounds: int = 50) -> List[Dict]:
        """
        Scroll through profile to load ALL posts before collecting them
        """
        try:
            # Navigate to profile
            if not self.safe_navigate(profile_url):
                logger.error(f"❌ Cannot access profile: {profile_url}")
                return []

            username = self.extract_username_from_url(profile_url)
            logger.info(f"🎯 Loading all posts from @{username}")

            previous_posts_count = 0
            no_change_count = 0
            max_no_change = 5

            logger.info(f"📜 Starting to load all posts (max {max_scroll_rounds} rounds)...")

            for scroll_round in range(max_scroll_rounds):
                try:
                    # Check current number of posts
                    current_posts = self.page.query_selector_all('div[data-e2e="user-post-item"]')
                    current_count = len(current_posts)

                    logger.info(f"📊 Round {scroll_round + 1}: Found {current_count} posts")

                    # Check if we found new posts
                    if current_count == previous_posts_count:
                        no_change_count += 1
                        logger.info(f"⏳ No new posts found ({no_change_count}/{max_no_change})")

                        if no_change_count >= max_no_change:
                            logger.info(f"✅ No new posts for {max_no_change} rounds - stopping scroll")
                            break
                    else:
                        no_change_count = 0
                        logger.info(f"🆕 Found {current_count - previous_posts_count} new posts")

                    previous_posts_count = current_count

                    # Scroll down to load more posts
                    self.page.mouse.wheel(0, 3000)
                    time.sleep(self.human_like_delay())

                    # Check for CAPTCHA during scrolling
                    if self.check_captcha_exists():
                        logger.warning(f"⚠️ CAPTCHA detected during scroll round {scroll_round + 1}")
                        if not self.solve_captcha(max_wait_time=15):
                            logger.warning("⚠️ CAPTCHA persists - continuing scroll")
                        continue

                except Exception as e:
                    logger.error(f"❌ Error during scroll round {scroll_round + 1}: {e}")
                    continue

            # Final collection of all posts
            final_posts = self.page.query_selector_all('div[data-e2e="user-post-item"]')
            logger.info(f"🎉 Finished loading! Total posts found: {len(final_posts)}")

            # Extract basic information from all loaded posts
            all_posts = []
            for i, post in enumerate(final_posts):
                try:
                    link_tag = post.query_selector('a')
                    post_url = link_tag.get_attribute('href') if link_tag else ''

                    if post_url and not post_url.startswith('http'):
                        post_url = 'https://www.tiktok.com' + post_url

                    thumb = post.query_selector('img')
                    post_thumbnail = thumb.get_attribute('src') if thumb else ''

                    if post_thumbnail and not post_thumbnail.startswith('http'):
                        post_thumbnail = 'https:' + post_thumbnail if post_thumbnail.startswith(
                            '//') else post_thumbnail

                    views_elem = post.query_selector('strong[data-e2e="video-views"]')
                    views = self.clean_number(views_elem.inner_text()) if views_elem else 0

                    all_posts.append({
                        "post_url": post_url,
                        "post_thumbnail": post_thumbnail,
                        "views": views,
                        "username": username,
                        "post_index": i + 1
                    })

                except Exception as e:
                    logger.error(f"❌ Error collecting post {i + 1}: {e}")
                    continue

            return all_posts

        except Exception as e:
            logger.error(f"❌ Critical error in scroll_to_load_all_posts: {e}")
            return []

    def scrape_posts_from_profile(self, profile_url: str, max_posts: int = None, scroll_rounds: int = 50) -> List[Dict]:
        """
        Main function to scrape posts from TikTok profile
        First loads all posts, then processes them one by one
        """
        try:
            # Step 1: Load all posts by scrolling
            logger.info("🔄 Step 1: Loading all posts from profile...")
            all_posts = self.scroll_to_load_all_posts(profile_url, scroll_rounds)

            if not all_posts:
                logger.error("❌ No posts found or failed to load posts")
                return []

            # Step 2: Limit posts if max_posts is specified
            posts_to_process = all_posts[:max_posts] if max_posts else all_posts
            logger.info(f"📋 Step 2: Processing {len(posts_to_process)} posts (out of {len(all_posts)} total)")

            # Step 3: Process each post to get detailed information
            logger.info("🔄 Step 3: Extracting detailed information from each post...")
            successful_posts = 0

            for i, post in enumerate(posts_to_process):
                try:
                    logger.info(
                        f"🔄 Processing post {i + 1}/{len(posts_to_process)}: {post.get('post_url', 'Unknown URL')}")

                    # Navigate to individual post
                    if not self.safe_navigate(post["post_url"]):
                        logger.warning(f"⚠️ Cannot access post {i + 1} - using default values")
                        post.update({
                            "post_content": "ไม่สามารถดึงข้อมูลได้ (Navigation Error)",
                            "timestamp": "ไม่พบวันที่",
                            "timestamp_unix": None,
                            "timestamp_iso": None,
                            "reaction": 0,
                            "comment": 0,
                            "shared": 0,
                            "saved": 0
                        })
                        continue

                    # Extract detailed post data
                    post_content = self.get_post_content()
                    timestamp, timestamp_unix, timestamp_iso = self.get_timestamp()
                    reaction, comment, shared = self.safe_get_metrics()
                    saved = self.get_saved_count()

                    # Update post data with extracted information
                    post.update({
                        "post_content": post_content,
                        "timestamp": timestamp,
                        "timestamp_unix": timestamp_unix,
                        "timestamp_iso": timestamp_iso,
                        "reaction": reaction,
                        "comment": comment,
                        "shared": shared,
                        "saved": saved
                    })

                    # Log results
                    logger.info(f"📝 Content: {post_content[:100]}...")
                    logger.info(f"🕐 Timestamp: {timestamp}")
                    logger.info(f"👁️ Views: {post['views']:,}")
                    logger.info(f"❤️ Likes: {reaction:,}")
                    logger.info(f"💬 Comments: {comment:,}")
                    logger.info(f"📤 Shares: {shared:,}")
                    logger.info(f"🔖 Saved: {saved:,}")
                    logger.info("=" * 80)

                    successful_posts += 1
                    time.sleep(self.human_like_delay())

                except Exception as e:
                    logger.error(f"❌ Error processing post {i + 1}: {e}")
                    # Add default values even if error occurs
                    post.update({
                        "post_content": "ไม่สามารถดึงข้อมูลได้ (Processing Error)",
                        "timestamp": "ไม่พบวันที่",
                        "timestamp_unix": None,
                        "timestamp_iso": None,
                        "reaction": 0,
                        "comment": 0,
                        "shared": 0,
                        "saved": 0
                    })
                    continue

            logger.info(f"🎉 Scraping completed!")
            logger.info(f"✅ Successfully processed {successful_posts} posts out of {len(posts_to_process)}")
            logger.info(f"📊 Total posts found: {len(all_posts)}")

            return posts_to_process  # Return processed posts instead of all_posts

        except Exception as e:
            logger.error(f"❌ Critical error in scrape_posts_from_profile: {e}")
            return []


# Django Integration Functions
def scrape_tiktok_posts_for_django(profile_url: str,
                                   cookies_file: str = None,
                                   max_posts: int = 50,
                                   headless: bool = False,
                                   scroll_rounds: int = 50,
                                   timeout: int = 30000) -> Dict:
    """
    Django-compatible function to scrape TikTok posts with enhanced error handling
    """
    result = {
        'success': False,
        'data': [],
        'message': '',
        'stats': {
            'total_posts': 0,
            'processed_posts': 0,
            'successful_posts': 0,
            'total_views': 0,
            'total_likes': 0,
            'total_comments': 0,
            'total_shares': 0,
            'total_saves': 0
        }
    }

    try:
        # Validate URL
        if not profile_url or not profile_url.startswith('https://www.tiktok.com/@'):
            result['message'] = 'Invalid TikTok profile URL. Please use format: https://www.tiktok.com/@username'
            return result

        # Extract username for logging
        username_match = re.search(r'@([^/?]+)', profile_url)
        username = username_match.group(1) if username_match else 'unknown'

        logger.info(f"🎯 Starting Django scrape for @{username}")

        # Initialize scraper
        with TikTokPostScraper(
                cookies_file=cookies_file,
                headless=headless,
                timeout=timeout
        ) as scraper:

            # Scrape posts
            posts_data = scraper.scrape_posts_from_profile(
                profile_url=profile_url,
                max_posts=max_posts,
                scroll_rounds=scroll_rounds
            )

            if posts_data:
                # Ensure all posts have the required fields with safe defaults
                cleaned_posts = []
                for post in posts_data:
                    try:
                        # Ensure post is a dictionary
                        if not isinstance(post, dict):
                            logger.warning(f"⚠️ Invalid post data type: {type(post)}, skipping")
                            continue

                        # Create cleaned post with safe defaults and proper data types
                        cleaned_post = {
                            "post_url": str(post.get("post_url", "")),
                            "post_thumbnail": str(post.get("post_thumbnail", "")),
                            "post_content": str(post.get("post_content", "ไม่พบเนื้อหา")),
                            "timestamp": str(post.get("timestamp", "ไม่พบวันที่")),
                            "timestamp_unix": post.get("timestamp_unix"),  # Keep as None if not available
                            "timestamp_iso": post.get("timestamp_iso"),  # Keep as None if not available
                            "username": str(post.get("username", username)),
                            "views": self._safe_int_convert(post.get("views", 0)),
                            "reaction": self._safe_int_convert(post.get("reaction", 0)),
                            "comment": self._safe_int_convert(post.get("comment", 0)),
                            "shared": self._safe_int_convert(post.get("shared", 0)),
                            "saved": self._safe_int_convert(post.get("saved", 0)),
                            "post_index": self._safe_int_convert(post.get("post_index", len(cleaned_posts) + 1))
                        }

                        cleaned_posts.append(cleaned_post)

                    except Exception as e:
                        logger.error(f"❌ Error cleaning post data: {e}")
                        continue

                # Calculate statistics with safe handling
                stats = result['stats']
                stats['total_posts'] = len(cleaned_posts)
                stats['processed_posts'] = len([p for p in cleaned_posts if p.get('post_content') not in [
                    'ไม่สามารถดึงข้อมูลได้ (Navigation Error)',
                    'ไม่สามารถดึงข้อมูลได้ (Processing Error)',
                    'ไม่สามารถดึงข้อมูลได้ (Error)'
                ]])
                stats['successful_posts'] = len([p for p in cleaned_posts if p.get('post_content') not in [
                    'ไม่สามารถดึงข้อมูลได้ (Navigation Error)',
                    'ไม่สามารถดึงข้อมูลได้ (Processing Error)',
                    'ไม่สามารถดึงข้อมูลได้ (Error)',
                    'ไม่พบเนื้อหา',
                    'ไม่สามารถดึงข้อมูลได้ (CAPTCHA)'
                ]])

                # Safe numeric calculations
                try:
                    stats['total_views'] = sum(self._safe_int_convert(post.get('views', 0)) for post in cleaned_posts)
                    stats['total_likes'] = sum(
                        self._safe_int_convert(post.get('reaction', 0)) for post in cleaned_posts)
                    stats['total_comments'] = sum(
                        self._safe_int_convert(post.get('comment', 0)) for post in cleaned_posts)
                    stats['total_shares'] = sum(self._safe_int_convert(post.get('shared', 0)) for post in cleaned_posts)
                    stats['total_saves'] = sum(self._safe_int_convert(post.get('saved', 0)) for post in cleaned_posts)
                except Exception as e:
                    logger.error(f"❌ Error calculating stats: {e}")

                result.update({
                    'success': True,
                    'data': cleaned_posts,
                    'message': f'Successfully scraped {len(cleaned_posts)} posts from @{username}'
                })

                logger.info(f"✅ Django scrape completed: {len(cleaned_posts)} posts from @{username}")

            else:
                result['message'] = f'No posts found or failed to access profile @{username}'
                logger.warning(f"⚠️ No posts found for @{username}")

    except Exception as e:
        error_msg = f'Scraping failed for {profile_url}: {str(e)}'
        result['message'] = error_msg
        logger.error(f"❌ Django scrape error: {error_msg}")

    return result


def _safe_int_convert(value) -> int:
    """Helper function to safely convert value to integer"""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            # Remove commas and convert K, M suffixes
            clean_value = value.replace(',', '').replace('K', '000').replace('M', '000000').replace('k', '000').replace(
                'm', '000000')
            return int(float(clean_value))
        except (ValueError, AttributeError):
            return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def save_posts_to_json(posts_data: List[Dict], filename: str = None) -> bool:
    """
    Save scraped posts data to JSON file with error handling
    """
    try:
        if not posts_data:
            logger.warning("⚠️ No posts data to save")
            return False

        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            username = posts_data[0].get('username', 'unknown') if posts_data else 'unknown'
            filename = f'tiktok_posts_{username}_{timestamp}.json'

        # Ensure directory exists
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.', exist_ok=True)

        # Ensure all data is JSON serializable
        serializable_data = []
        for post in posts_data:
            try:
                if isinstance(post, dict):
                    # Convert all values to JSON-safe types
                    safe_post = {}
                    for key, value in post.items():
                        if isinstance(value, (str, int, float, bool, type(None))):
                            safe_post[key] = value
                        else:
                            safe_post[key] = str(value)
                    serializable_data.append(safe_post)
            except Exception as e:
                logger.error(f"❌ Error serializing post: {e}")

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(serializable_data, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 Saved {len(serializable_data)} posts to {filename}")
        return True

    except Exception as e:
        logger.error(f"❌ Error saving file: {e}")  # Fixed: removed undefined variable
        return False


def filter_recent_posts(posts_data: List[Dict], days: int = 30) -> List[Dict]:
    """
    Filter posts from the last N days
    """
    try:
        if not posts_data:
            return []

        # If no valid timestamps, return all posts
        valid_timestamp_posts = [p for p in posts_data if p.get('timestamp_unix')]
        if not valid_timestamp_posts:
            logger.info(f"📅 กรองเฉพาะโพสต์ {days} วันแรก")
            return posts_data

        # Filter by timestamp
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_timestamp = cutoff_date.timestamp()

        recent_posts = [
            post for post in posts_data
            if post.get('timestamp_unix', 0) >= cutoff_timestamp
        ]

        logger.info(f"📅 กรองเฉพาะโพสต์ {days} วันแรก")
        return recent_posts

    except Exception as e:
        logger.error(f"❌ Error filtering posts: {e}")
        return posts_data


def get_posts_summary(posts_data: List[Dict]) -> Dict:
    """
    Generate summary statistics from posts data with safe handling
    """
    if not posts_data:
        return {
            'username': 'unknown',
            'total_posts': 0,
            'successful_posts': 0,
            'success_rate': '0%',
            'total_views': 0,
            'total_likes': 0,
            'total_comments': 0,
            'total_shares': 0,
            'total_saves': 0,
            'average_views': 0,
            'average_likes': 0
        }

    try:
        total_posts = len(posts_data)
        successful_posts = len([
            post for post in posts_data
            if isinstance(post, dict) and post.get('post_content', '') not in [
                'ไม่สามารถดึงข้อมูลได้ (Navigation Error)',
                'ไม่สามารถดึงข้อมูลได้ (Processing Error)',
                'ไม่สามารถดึงข้อมูลได้ (Error)',
                'ไม่พบเนื้อหา',
                'ไม่สามารถดึงข้อมูลได้ (CAPTCHA)'
            ]
        ])

        # Safe numeric calculations
        total_views = sum(_safe_int_convert(post.get('views', 0)) for post in posts_data if isinstance(post, dict))
        total_likes = sum(_safe_int_convert(post.get('reaction', 0)) for post in posts_data if isinstance(post, dict))
        total_comments = sum(_safe_int_convert(post.get('comment', 0)) for post in posts_data if isinstance(post, dict))
        total_shares = sum(_safe_int_convert(post.get('shared', 0)) for post in posts_data if isinstance(post, dict))
        total_saves = sum(_safe_int_convert(post.get('saved', 0)) for post in posts_data if isinstance(post, dict))

        return {
            'username': posts_data[0].get('username', 'unknown') if posts_data else 'unknown',
            'total_posts': total_posts,
            'successful_posts': successful_posts,
            'success_rate': f"{(successful_posts / total_posts * 100):.1f}%" if total_posts > 0 else "0%",
            'total_views': total_views,
            'total_likes': total_likes,
            'total_comments': total_comments,
            'total_shares': total_shares,
            'total_saves': total_saves,
            'average_views': total_views // total_posts if total_posts > 0 else 0,
            'average_likes': total_likes // total_posts if total_posts > 0 else 0
        }
    except Exception as e:
        logger.error(f"❌ Error generating summary: {e}")
        return {
            'username': 'error',
            'total_posts': 0,
            'successful_posts': 0,
            'success_rate': '0%',
            'total_views': 0,
            'total_likes': 0,
            'total_comments': 0,
            'total_shares': 0,
            'total_saves': 0,
            'average_views': 0,
            'average_likes': 0
        }


# Standalone execution function (for testing)
def run_standalone_scraper(profile_url: str = None,
                           cookies_file: str = None,
                           max_posts: int = None,
                           save_json: bool = True):
    """
    Standalone function for testing the scraper
    """
    # Default URL for testing (can be changed)
    if not profile_url:
        profile_url = "https://www.tiktok.com/@atlascat_official"

    # Check if cookies file exists
    if cookies_file and not os.path.exists(cookies_file):
        logger.warning(f"Cookies file not found: {cookies_file}")
        cookies_file = None

    print("🚀 Starting Enhanced TikTok Posts Scraper")
    print(f"🎯 Target: {profile_url}")
    print(f"📊 Max posts: {max_posts if max_posts else 'ALL POSTS'}")
    print(f"🍪 Cookies: {'✅' if cookies_file else '❌'}")
    print("=" * 80)

    # Run scraper
    result = scrape_tiktok_posts_for_django(
        profile_url=profile_url,
        cookies_file=cookies_file,
        max_posts=max_posts,
        headless=False,  # Set to True for production
        scroll_rounds=50,
        timeout=30000
    )

    if result['success']:
        posts_data = result['data']

        # Filter recent posts
        filtered_posts = filter_recent_posts(posts_data, days=30)

        # Display summary
        summary = get_posts_summary(filtered_posts)
        print("\n📊 SCRAPING SUMMARY")
        print("=" * 80)
        print(f"👤 Username: @{summary['username']}")
        print(f"📝 Total Posts: {summary['total_posts']}")
        print(f"✅ Successful: {summary['successful_posts']} ({summary['success_rate']})")
        print(f"👁️ Total Views: {summary['total_views']:,}")
        print(f"❤️ Total Likes: {summary['total_likes']:,}")
        print(f"💬 Total Comments: {summary['total_comments']:,}")
        print(f"📤 Total Shares: {summary['total_shares']:,}")
        print(f"🔖 Total Saves: {summary['total_saves']:,}")
        print(f"📈 Avg Views/Post: {summary['average_views']:,}")
        print(f"📈 Avg Likes/Post: {summary['average_likes']:,}")

        # Save to JSON if requested
        if save_json:
            save_posts_to_json(filtered_posts)

        # Display sample post
        if filtered_posts:
            print("\n📄 ตัวอย่างข้อมูลสำหรับ Database:")
            print("=" * 80)
            sample = filtered_posts[0]
            sample_json = json.dumps({k: v for k, v in sample.items()},
                                     ensure_ascii=False, indent=2)
            print(sample_json)

        print(f"\n📋 ดึงข้อมูล {len(filtered_posts)} โพสต์จาก TikTok")
        print("✅ ดึงข้อมูลสำเร็จ")

    else:
        print(f"❌ Error fetching TikTok posts: {result['message']}")


if __name__ == "__main__":
    # Example usage - change URL as needed
    profile_url = "https://www.tiktok.com/@panzylab"  # Change this URL
    cookies_file = "tiktok_cookies.json"  # Optional

    run_standalone_scraper(
        profile_url=profile_url,
        cookies_file=cookies_file if os.path.exists(cookies_file) else None,
        max_posts=None,  # Change this number
        save_json=True
    )