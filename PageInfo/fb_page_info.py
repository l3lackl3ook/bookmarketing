from pprint import pprint
from ftplib import FTP
from io import BytesIO
from curl_cffi import requests
from selectolax.parser import HTMLParser
import json
import sys
import re
from typing import Optional, Dict
from urllib.parse import urlparse

def upload_to_sghost(image_url: str) -> str:
    from urllib.parse import urlparse
    import requests
    import os

    FTP_HOST = "ftp.taechins18.sg-host.com"
    FTP_USER = "admin@taechins18.sg-host.com"
    FTP_PASS = "#),51@37f]1i"
    FTP_PATH = "taechins18.sg-host.com/public_html/image"
    BASE_URL = "https://taechins18.sg-host.com/image/"

    filename = os.path.basename(urlparse(image_url).path)

    ftp = FTP()
    ftp.connect(FTP_HOST, 21)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.cwd(FTP_PATH)

    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(image_url, headers=headers)
    response.raise_for_status()

    ftp.storbinary(f"STOR {filename}", BytesIO(response.content))
    ftp.quit()

    return f"{BASE_URL}{filename}"

class RequestHandler:
    def __init__(self):
        self.headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    def fetch_html(self, url: str) -> str:
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return HTMLParser(response.text)
        except Exception as e:
            print(f"Error fetching the page [{url}]: {e}")
            sys.exit(1)

    def parse_json_from_html(self, html_content: HTMLParser, key_to_find: str) -> dict:
        try:
            parser = html_content
            for script in parser.css('script[type="application/json"]'):
                script_text = script.text(strip=True)
                if key_to_find in script_text:
                    return json.loads(script_text)
            print(f"No valid data found for key '{key_to_find}' in the HTML page.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for key '{key_to_find}': {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error parsing JSON for key '{key_to_find}': {e}")
            sys.exit(1)


class PageInfo:
    def __new__(cls, url: str):
        # Instantiate and immediately scrape, returning the data dict
        instance = super().__new__(cls)
        # Initialize required attributes for scrape
        instance.url = cls.normalize_url(url)
        instance.request_handler = RequestHandler()
        instance.general_info = {}
        instance.profile_info = {}
        # Perform the scrape and return the resulting dict
        return instance.scrape()

    def __init__(self, url: str):
        # __init__ is left for clarity but will not be called due to __new__ returning a dict
        self.url = self.normalize_url(url)
        self.request_handler = RequestHandler()
        self.general_info: Dict[str, Optional[str]] = {}
        self.profile_info: Dict[str, Optional[str]] = {}

    @staticmethod
    def normalize_url(input_url: str) -> str:
        base_url = "https://www.facebook.com/"
        if not input_url.startswith(base_url):
            # If it's a username or partial URL, append it to the base Facebook URL
            if input_url.startswith("/"):
                input_url = input_url[1:]  # Remove leading slash
            return base_url + input_url
        return input_url

    def scrape(self) -> Optional[Dict[str, Optional[str]]]:
        html_content = self.request_handler.fetch_html(self.url)

        # Parse general information
        general_info_json = self.request_handler.parse_json_from_html(
            html_content, "username_for_profile"
        )
        self.general_info = self.extract_general_info(general_info_json)

        # Parse profile information
        profile_info_json = self.request_handler.parse_json_from_html(
            html_content, "profile_tile_items"
        )
        self.profile_info = self.extract_profile_info(profile_info_json)

        self.meta_html_info = self.extract_html_data(html_content)

        # Combine both into one dictionary
        if self.general_info and self.profile_info:
            combined_info = {**self.general_info, **self.meta_html_info, **self.profile_info}
            return combined_info
        elif self.general_info:
            return self.general_info
        elif self.profile_info:
            return self.profile_info
        else:
            return None

    def extract_general_info(self, json_data: dict) -> Dict[str, Optional[str]]:
        general_info = {
            "page_name": None,
            "page_url": None,
            "profile_pic": None,
            "page_likes": None,
            "page_followers": None,
            "page_id": None,
            "is_business_page": None
        }

        try:
            requires = json_data.get("require", [])

            if not requires:
                raise ValueError("Missing 'require' key in JSON data.")
            requires = requires[0][3][0].get("__bbox", {}).get("require", [])

            for require in requires:
                if "RelayPrefetchedStreamCache" in require:
                    result = require[3][1].get("__bbox", {}).get("result", {})

                    user = (
                        result.get("data", {})
                        .get("user", {})
                        .get("profile_header_renderer", {})
                        .get("user", {})
                    )

                    general_info["page_name"] = user.get("name")
                    general_info["page_url"] = user.get("url")

                    # extract the username from the URL
                    parsed = urlparse(general_info["page_url"])
                    path = parsed.path.strip("/")
                    general_info["page_username"] = f"@{path}" if path else None

                    general_info["page_id"] = user.get("delegate_page", {}).get("id")

                    general_info["is_business_page"] = user.get("delegate_page", {}).get("is_business_page_active")

                    original_pic = (
                            user.get("profilePicLarge", {}).get("uri")
                            or user.get("profilePicMedium", {}).get("uri")
                            or user.get("profilePicSmall", {}).get("uri")
                    )

                    if original_pic:
                        try:
                            uploaded_url = upload_to_sghost(original_pic)
                            general_info["profile_pic"] = uploaded_url
                        except Exception as e:
                            print(f"❌ Failed to upload profile_pic to sg-host: {e}")
                            general_info["profile_pic"] = original_pic

                    profile_social_contents = user.get(
                        "profile_social_context", {}
                    ).get("content", [])
                    for content in profile_social_contents:
                        uri = content.get("uri", "")
                        text = content.get("text", {}).get("text")
                        if "friends_likes" in uri and not general_info["page_likes"]:
                            general_info["page_likes"] = text
                        elif "followers" in uri and not general_info["page_followers"]:
                            general_info["page_followers"] = text
                        if (
                                general_info["page_likes"]
                                and general_info["page_followers"]
                        ):
                            break
            return general_info
        except (IndexError, KeyError, TypeError, ValueError) as e:
            print(f"Error extracting general page information: {e}")
            return general_info

    def extract_profile_info(self, json_data: dict) -> Dict[str, Optional[str]]:

        matching_types = {
            "INTRO_CARD_INFLUENCER_CATEGORY": "page_category",
            "INTRO_CARD_ADDRESS": "page_address",
            "INTRO_CARD_PROFILE_PHONE": "page_phone",
            "INTRO_CARD_PROFILE_EMAIL": "page_email",
            "INTRO_CARD_WEBSITE": "page_website",
            "INTRO_CARD_BUSINESS_HOURS": "page_business_hours",
            "INTRO_CARD_BUSINESS_PRICE": "page_business_price",
            "INTRO_CARD_RATING": "page_rating",
            "INTRO_CARD_BUSINESS_SERVICES": "page_services",
            "INTRO_CARD_OTHER_ACCOUNT": "page_social_accounts",
        }

        profile_info = {value: None for value in matching_types.values()}

        try:
            requires = json_data.get("require", [])
            if not requires:
                raise ValueError("Missing 'require' key in JSON data.")
            requires = requires[0][3][0].get("__bbox", {}).get("require", [])

            for require in requires:
                if "RelayPrefetchedStreamCache" in require:
                    result = require[3][1].get("__bbox", {}).get("result", {})
                    profile_tile_sections = (
                        result.get("data", {})
                        .get("profile_tile_sections", {})
                        .get("edges", [])
                    )

                    for section in profile_tile_sections:
                        nodes = (
                            section.get("node", {})
                            .get("profile_tile_views", {})
                            .get("nodes", [])
                        )
                        for node in nodes:
                            view_style_renderer = node.get("view_style_renderer")
                            if not view_style_renderer:
                                continue
                            profile_tile_items = (
                                view_style_renderer.get("view", {})
                                .get("profile_tile_items", {})
                                .get("nodes", [])
                            )
                            for item in profile_tile_items:
                                timeline_context_item = item.get("node", {}).get(
                                    "timeline_context_item", {}
                                )
                                item_type = timeline_context_item.get(
                                    "timeline_context_list_item_type"
                                )
                                if item_type in matching_types:
                                    text = (
                                        timeline_context_item.get("renderer", {})
                                        .get("context_item", {})
                                        .get("title", {})
                                        .get("text")
                                    )
                                    if text:
                                        key = matching_types[item_type]
                                        profile_info[key] = text

            return profile_info
        except (IndexError, KeyError, TypeError, ValueError) as e:
            print(f"Error extracting profile information: {e}")
            return profile_info

    def extract_html_data(self, html_content: HTMLParser) -> Dict[str, Optional[str]]:
        meta_data = {
            "page_likes_count": None,
            "page_talking_count": None,
            "page_were_here_count": None,
        }

        try:

            meta_description = html_content.css_first('meta[property="og:description"]').attrs.get(
                "content") if html_content.css_first("meta[name=description]") else None

            if not meta_description:
                return meta_data

            like_pattern = r"(?P<likes>[\d,]+)\s+likes"
            like_match = re.search(like_pattern, meta_description)
            likes = like_match.group("likes") if like_match else None

            talking_pattern = r"(?P<talking>[\d,]+)\s+talking about this"
            talking_match = re.search(talking_pattern, meta_description)
            talking = talking_match.group("talking") if talking_match else None

            were_pattern = r"(?P<were>[\d,]+)\s+were here"
            were_match = re.search(were_pattern, meta_description)
            were = were_match.group("were") if were_match else None

            # extract the text after the counts as page_description
            desc_match = meta_description.rsplit('. ', 1)
            description = desc_match[1] if len(desc_match) > 1 else None

            meta_data["page_likes_count"] = likes
            meta_data["page_talking_count"] = talking
            meta_data["page_were_here_count"] = were
            meta_data["page_description"] = description

            return meta_data

        except Exception as e:
            print(
                f"Unexpected error in (extract_html_data) func: {e}")
            return meta_data

class PageFollowers:
    def __new__(cls, page_id: str):
        # Instantiate and immediately scrape, returning the data dict
        instance = super().__new__(cls)
        # Initialize required attributes for scrape
        instance.url = f'https://www.facebook.com/plugins/page.php?href=https%3A%2F%2Fwww.facebook.com%2F{page_id}&tabs=timeline&width=340&height=500&small_header=false&adapt_container_width=true&hide_cover=false&show_facepile=true&appId&locale=en_us'
        instance.request_handler = RequestHandler()
        instance.page_followers = {}
        # Perform the scrape and return the resulting dict
        return instance.scrape()

    def __init__(self, page_id: str):
        # __init__ is left for clarity but will not be called due to __new__ returning a dict
        self.url = f'https://www.facebook.com/plugins/page.php?href=https%3A%2F%2Fwww.facebook.com%2F{page_id}&tabs=timeline&width=340&height=500&small_header=false&adapt_container_width=true&hide_cover=false&show_facepile=true&appId&locale=en_us'
        self.request_handler = RequestHandler()
        self.page_followers: Dict[str, Optional[str]] = {}

    def scrape(self) -> Optional[Dict[str, Optional[str]]]:
        # Fetch the plugin page HTML
        html_content = self.request_handler.fetch_html(self.url)

        # Find the followers text element
        follower_div = html_content.css_first("div._1drq")
        if follower_div:
            text = follower_div.text(strip=True)
            # Extract numeric part before "followers"
            match = re.search(r"([\d,]+)\s+followers", text, re.IGNORECASE)
            if match:
                page_followers = {'page_followers_count':int(match.group(1).replace(",", ""))}
                return page_followers

        return None


if __name__ == "__main__":
    url = 'https://www.facebook.com/bakingcluboflamsoon'

    page_info = PageInfo(url)
    page_id = page_info['page_id']
    pprint(page_info)

    page_follower = PageFollowers(page_id)
    pprint(page_follower)