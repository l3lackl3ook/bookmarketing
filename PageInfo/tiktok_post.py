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
    Can scrape posts from any TikTok profile URL dynamically
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
        """Handle CAPTCHA with timeout"""
        if not self.check_captcha_exists():
            return True

        try:
            logger.warning(f"🤖 CAPTCHA detected - waiting up to {max_wait_time} seconds")
            start_time = time.time()

            while time.time() - start_time < max_wait_time:
                if not self.check_captcha_exists():
                    logger.info("✅ CAPTCHA solved successfully")
                    time.sleep(2)
                    return True
                time.sleep(1)

            logger.warning(f"⚠️ CAPTCHA timeout after {max_wait_time} seconds")
            return False

        except Exception as e:
            logger.error(f"❌ Error handling CAPTCHA: {e}")
            return False

    def safe_navigate(self, url: str, retries: int = 3) -> bool:
        """Navigate with CAPTCHA handling and retries"""
        for attempt in range(retries):
            try:
                logger.info(f"🔄 Navigating to: {url} (attempt {attempt + 1})")
                self.page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)

                # Wait for page to stabilize
                time.sleep(random.uniform(2, 4))

                if self.check_captcha_exists():
                    logger.info("🤖 CAPTCHA detected during navigation")
                    if not self.solve_captcha(max_wait_time=20):
                        if attempt < retries - 1:
                            logger.info("🔄 Retrying navigation...")
                            time.sleep(5)
                            continue
                        else:
                            logger.error("❌ Failed to solve CAPTCHA")
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
        """Extract post content with multiple fallback methods"""
        if self.check_captcha_exists():
            logger.warning("⚠️ CAPTCHA present - skipping content extraction")
            return "ไม่สามารถดึงข้อมูลได้ (CAPTCHA)"

        time.sleep(2)

        # Scroll to expand description
        try:
            self.page.evaluate("window.scrollTo(0, 150)")
            time.sleep(1)

            # Try to click "See more" buttons in description area only
            description_area = self.page.query_selector('[data-e2e="browse-video-desc"], [data-e2e="video-desc"]')
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

            if universal_data and len(universal_data.strip()) > 5:
                content = universal_data.strip()
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

                if sigi_data and len(sigi_data.strip()) > 5:
                    content = sigi_data.strip()
            except:
                pass

        # Method 3: Extract from DOM elements
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

    def get_timestamp(self) -> str:
        """Extract post timestamp with multiple methods"""
        if self.check_captcha_exists():
            return "ไม่สามารถดึงวันที่ได้ (CAPTCHA)"

        # Method 1: Extract from __UNIVERSAL_DATA_FOR_REHYDRATION__
        try:
            timestamp_from_data = self.page.evaluate("""
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

        # Method 2: Extract from SIGI_STATE
        try:
            sigi_timestamp = self.page.evaluate("""
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
                        return dt.strftime('%d/%m/%Y')
        except:
            pass

        # Method 4: Extract from DOM elements
        try:
            dom_timestamp = self.page.evaluate("""
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
                    return null;
                }
            """)

            if dom_timestamp:
                return dom_timestamp
        except:
            pass

        return "ไม่พบวันที่"

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

    def scrape_posts_from_profile(self, profile_url: str, max_posts: int = 50, scroll_rounds: int = 8) -> List[Dict]:
        """
        Main function to scrape posts from TikTok profile

        Args:
            profile_url: TikTok profile URL (e.g., "https://www.tiktok.com/@username")
            max_posts: Maximum number of posts to process
            scroll_rounds: Number of scroll rounds to load posts

        Returns:
            List of dictionaries containing post data
        """
        try:
            # Navigate to profile
            if not self.safe_navigate(profile_url):
                logger.error(f"❌ Cannot access profile: {profile_url}")
                return []

            # Extract username for reference
            username = self.extract_username_from_url(profile_url)
            logger.info(f"🎯 Scraping posts from @{username}")

            # Scroll to load more posts
            logger.info(f"📜 Loading posts with {scroll_rounds} scroll rounds...")
            for i in range(scroll_rounds):
                try:
                    self.page.mouse.wheel(0, 2000)
                    time.sleep(self.human_like_delay())

                    # Check for CAPTCHA during scrolling
                    if self.check_captcha_exists():
                        logger.warning(f"⚠️ CAPTCHA detected during scroll {i + 1} - stopping scroll")
                        break
                except Exception as e:
                    logger.error(f"Error during scroll {i + 1}: {e}")
                    break

            # Extract post elements from profile page
            posts = self.page.query_selector_all('div[data-e2e="user-post-item"]')
            all_posts = []

            logger.info(f"🔍 Found {len(posts)} posts on profile page")

            # Collect basic post information
            for i, post in enumerate(posts):
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
                        "username": username
                    })

                    logger.info(f"📋 Post {i + 1}: Views: {views:,}")

                except Exception as e:
                    logger.error(f"❌ Error collecting post {i + 1}: {e}")

            logger.info(f"✅ Collected {len(all_posts)} posts from profile")
            total_views = sum(post['views'] for post in all_posts)
            logger.info(f"📊 Total Views: {total_views:,}")

            # Process each post to get detailed information
            successful_posts = 0
            posts_to_process = all_posts[:max_posts] if max_posts else all_posts

            for i, post in enumerate(posts_to_process):
                try:
                    logger.info(f"🔄 Processing post {i + 1}/{len(posts_to_process)}")

                    # Navigate to individual post
                    if not self.safe_navigate(post["post_url"]):
                        logger.warning(f"⚠️ Cannot access post {i + 1} - using default values")
                        post.update({
                            "post_content": "ไม่สามารถดึงข้อมูลได้ (Navigation Error)",
                            "timestamp": "ไม่พบวันที่",
                            "reaction": 0,
                            "comment": 0,
                            "shared": 0,
                            "saved": 0
                        })
                        continue

                    # Extract detailed post data
                    post_content = self.get_post_content()
                    timestamp = self.get_timestamp()
                    reaction, comment, shared = self.safe_get_metrics()
                    saved = self.get_saved_count()

                    # Update post data
                    post.update({
                        "post_content": post_content,
                        "timestamp": timestamp,
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
                        "post_content": "ไม่สามารถดึงข้อมูลได้ (Error)",
                        "timestamp": "ไม่พบวันที่",
                        "reaction": 0,
                        "comment": 0,
                        "shared": 0,
                        "saved": 0
                    })
                    continue

            logger.info(f"🎉 Scraping completed!")
            logger.info(f"✅ Successfully processed {successful_posts} posts out of {len(posts_to_process)}")

            return all_posts

        except Exception as e:
            logger.error(f"❌ Critical error in scrape_posts_from_profile: {e}")
            return []


# Django Integration Functions
def scrape_tiktok_posts_for_django(profile_url: str,
                                   cookies_file: str = None,
                                   max_posts: int = 50,
                                   headless: bool = False,
                                   scroll_rounds: int = 20,
                                   timeout: int = 30000) -> Dict:
    """
    Django-compatible function to scrape TikTok posts

    Args:
        profile_url: TikTok profile URL (e.g., "https://www.tiktok.com/@username")
        cookies_file: Path to cookies JSON file (optional)
        max_posts: Maximum number of posts to process
        headless: Run browser in headless mode
        scroll_rounds: Number of scroll rounds to load posts
        timeout: Page load timeout in milliseconds

    Returns:
        Dictionary with 'success', 'data', 'message', and 'stats' keys
    """
    result = {
        'success': False,
        'data': [],
        'message': '',
        'stats': {
            'total_posts': 0,
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
                # Calculate statistics
                stats = result['stats']
                stats['total_posts'] = len(posts_data)
                stats['successful_posts'] = sum(1 for post in posts_data
                                                if post.get('post_content',
                                                            '') != 'ไม่สามารถดึงข้อมูลได้ (Navigation Error)'
                                                and post.get('post_content', '') != 'ไม่สามารถดึงข้อมูลได้ (Error)')
                stats['total_views'] = sum(post.get('views', 0) for post in posts_data)
                stats['total_likes'] = sum(post.get('reaction', 0) for post in posts_data)
                stats['total_comments'] = sum(post.get('comment', 0) for post in posts_data)
                stats['total_shares'] = sum(post.get('shared', 0) for post in posts_data)
                stats['total_saves'] = sum(post.get('saved', 0) for post in posts_data)

                result.update({
                    'success': True,
                    'data': posts_data,
                    'message': f'Successfully scraped {len(posts_data)} posts from @{username}'
                })

                logger.info(f"✅ Django scrape completed: {len(posts_data)} posts from @{username}")

            else:
                result['message'] = f'No posts found or failed to access profile @{username}'
                logger.warning(f"⚠️ No posts found for @{username}")

    except Exception as e:
        error_msg = f'Scraping failed for {profile_url}: {str(e)}'
        result['message'] = error_msg
        logger.error(f"❌ Django scrape error: {error_msg}")

    return result


def save_posts_to_json(posts_data: List[Dict], filename: str = None) -> bool:
    """
    Save scraped posts data to JSON file

    Args:
        posts_data: List of post dictionaries
        filename: Output filename (auto-generated if None)

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            username = posts_data[0].get('username', 'unknown') if posts_data else 'unknown'
            filename = f'tiktok_posts_{username}_{timestamp}.json'

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(posts_data, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 Saved {len(posts_data)} posts to {filename}")
        return True

    except Exception as e:
        logger.error(f"❌ Error saving to JSON: {e}")
        return False


def get_posts_summary(posts_data: List[Dict]) -> Dict:
    """
    Generate summary statistics from posts data

    Args:
        posts_data: List of post dictionaries

    Returns:
        Dictionary with summary statistics
    """
    if not posts_data:
        return {}

    total_posts = len(posts_data)
    successful_posts = sum(1 for post in posts_data
                           if post.get('post_content', '') not in [
                               'ไม่สามารถดึงข้อมูลได้ (Navigation Error)',
                               'ไม่สามารถดึงข้อมูลได้ (Error)',
                               'ไม่พบเนื้อหา'
                           ])

    return {
        'username': posts_data[0].get('username', 'unknown'),
        'total_posts': total_posts,
        'successful_posts': successful_posts,
        'success_rate': f"{(successful_posts / total_posts * 100):.1f}%" if total_posts > 0 else "0%",
        'total_views': sum(post.get('views', 0) for post in posts_data),
        'total_likes': sum(post.get('reaction', 0) for post in posts_data),
        'total_comments': sum(post.get('comment', 0) for post in posts_data),
        'total_shares': sum(post.get('shared', 0) for post in posts_data),
        'total_saves': sum(post.get('saved', 0) for post in posts_data),
        'average_views': sum(post.get('views', 0) for post in posts_data) // total_posts if total_posts > 0 else 0,
        'average_likes': sum(post.get('reaction', 0) for post in posts_data) // total_posts if total_posts > 0 else 0
    }


# Standalone execution function (for testing)
def run_standalone_scraper(profile_url: str = None,
                           cookies_file: str = None,
                           max_posts: int = 20,
                           save_json: bool = True):
    """
    Standalone function for testing the scraper

    Args:
        profile_url: TikTok profile URL to scrape
        cookies_file: Path to cookies JSON file
        max_posts: Maximum number of posts to process
        save_json: Whether to save results to JSON file
    """

    # Default URL for testing (can be changed)
    if not profile_url:
        profile_url = "https://www.tiktok.com/@atlascat_official"

    # Check if cookies file exists
    if cookies_file and not os.path.exists(cookies_file):
        logger.warning(f"Cookies file not found: {cookies_file}")
        cookies_file = None

    print("🚀 Starting TikTok Posts Scraper")
    print(f"🎯 Target: {profile_url}")
    print(f"📊 Max posts: {max_posts}")
    print(f"🍪 Cookies: {'✅' if cookies_file else '❌'}")
    print("=" * 80)

    # Run scraper
    result = scrape_tiktok_posts_for_django(
        profile_url=profile_url,
        cookies_file=cookies_file,
        max_posts=max_posts,
        headless=False,  # Set to True for production
        scroll_rounds=8,
        timeout=30000
    )

    if result['success']:
        posts_data = result['data']

        # Display summary
        summary = get_posts_summary(posts_data)
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
            save_posts_to_json(posts_data)

        # Display sample post
        if posts_data:
            print("\n📄 SAMPLE POST DATA")
            print("=" * 80)
            sample = posts_data[0]
            sample_json = json.dumps({k: v for k, v in sample.items()},
                                     ensure_ascii=False, indent=2)
            print(sample_json)

    else:
        print(f"❌ Scraping failed: {result['message']}")


# Example Django views.py integration
"""
# In your Django views.py:

from .tiktok_post import scrape_tiktok_posts_for_django
from django.http import JsonResponse
from django.shortcuts import render

def scrape_tiktok_view(request):
    if request.method == 'POST':
        profile_url = request.POST.get('profile_url')
        max_posts = int(request.POST.get('max_posts', 20))

        # Run scraper
        result = scrape_tiktok_posts_for_django(
            profile_url=profile_url,
            cookies_file='path/to/your/cookies.json',  # Optional
            max_posts=max_posts,
            headless=True  # Use headless for production
        )

        if result['success']:
            # Save to database or return data
            return JsonResponse({
                'status': 'success',
                'data': result['data'],
                'stats': result['stats']
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message']
            })

    return render(request, 'scrape_form.html')
"""

if __name__ == "__main__":
    # Example usage - change URL as needed
    profile_url = "https://www.tiktok.com/@atlascat_official"  # Change this URL
    cookies_file = "tiktok_cookies.json"  # Optional - set path to your cookies file

    run_standalone_scraper(
        profile_url=profile_url,
        cookies_file=cookies_file if os.path.exists(cookies_file) else None,
        max_posts=None,  # Adjust as needed
        save_json=True
    )