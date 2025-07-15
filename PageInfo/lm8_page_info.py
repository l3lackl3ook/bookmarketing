import requests
from bs4 import BeautifulSoup
import re

def get_lemon8_info(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/113.0.0.0 Safari/537.36",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ HTTP Error: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    try:
        profile_pic = soup.select_one(".user-desc-main-avatar")["src"]
        username = soup.select_one(".user-desc-base-name").text.strip()

        # Followers, Following, Likes
        stats = soup.select(".user-desc-main-info-item span")
        following_count = stats[0].text.strip() if len(stats) > 0 else None
        followers_count = stats[2].text.strip() if len(stats) > 2 else None
        likes_count = stats[4].text.strip() if len(stats) > 4 else None

        # Bio
        bio = soup.select_one(".user-desc-base-desc")
        bio_text = bio.text.strip() if bio else None

        # Website
        website_tag = soup.select_one(".user-introduction-link-content p")
        website = website_tag.text.strip() if website_tag else None

        # Age
        age_tag = soup.select_one(".user-desc-base-info span")
        age = age_tag.text.strip() if age_tag else None

        result = {
            "username": username,
            "profile_pic": profile_pic,
            "followers_count": followers_count,
            "likes_count": likes_count,
            "following_count": following_count,
            "bio": bio_text,
            "website": website,
            "age": age,
            "url": url
        }
        return result
    except Exception as e:
        print(f"❌ Error parsing Lemon8: {e}")
        return None

# 🧪 ทดสอบการดึงข้อมูล
if __name__ == "__main__":
    url = "https://www.lemon8-app.com/@adore144p"  # แทน URL จริงของผู้ใช้
    data = get_lemon8_info(url)
    if data:
        print("✅ ดึงข้อมูล Lemon8 สำเร็จ:")
        print(data)
    else:
        print("❌ ดึงข้อมูล Lemon8 ไม่สำเร็จ")
