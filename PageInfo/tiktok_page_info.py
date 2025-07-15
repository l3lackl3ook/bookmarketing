import requests
import re
import json

def get_tiktok_info(url):
    # แยก username จาก URL เช่น https://www.tiktok.com/@atlascat_official
    match = re.search(r"tiktok\.com/@([\w\.\-]+)", url)
    if not match:
        print("❌ URL ไม่ถูกต้องหรือไม่พบ username")
        return None

    username = match.group(1)
    url = f'https://www.tiktok.com/@{username}'

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/113.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        html = response.text

        # หา JSON object ที่ชื่อ 'webapp.user-detail'
        match = re.search(r'"webapp\.user-detail":\s*({.*?})\s*,\s*"webapp', html)
        if match:
            json_text = match.group(1)
            try:
                data = json.loads(json_text)
                user_info = data.get("userInfo", {}).get("user", {})
                stats = data.get("userInfo", {}).get("stats", {})
                if user_info:
                    result = {
                        "username": user_info.get("uniqueId"),
                        "nickname": user_info.get("nickname"),
                        "bio": user_info.get("signature"),
                        "profile_pic": user_info.get("avatarLarger"),
                        "followers": stats.get("followerCount"),
                        "likes": stats.get("heartCount"),
                        "url": url
                    }
                    return result
                else:
                    print("❌ ไม่พบข้อมูล userInfo")
            except Exception as e:
                print(f"❌ Error parsing JSON: {e}")
        else:
            print("❌ ไม่เจอ webapp.user-detail ใน HTML")
    else:
        print(f"❌ HTTP Error: {response.status_code}")

    return None

# ทดสอบการรันตรงนี้
if __name__ == "__main__":
    url = "https://www.tiktok.com/@atlascat_official"  # หรือ URL อื่น
    data = get_tiktok_info(url)
    if data:
        print("✅ ดึงข้อมูลสำเร็จ:")
        print(data)
    else:
        print("❌ ดึงข้อมูลไม่สำเร็จ")
