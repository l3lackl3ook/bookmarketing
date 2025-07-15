import requests
import json
import re


def get_instagram_info(username):
    # Endpoint ที่ Instagram ใช้ดึงข้อมูลผู้ใช้แบบ web (GraphQL)
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/113.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459",  # App ID ของ Instagram Web
        "Referer": f"https://www.instagram.com/{username}/",
    }

    # คุณสามารถเพิ่ม cookies ถ้าโดนบล็อก หรือใช้ session จาก browser
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        user_data = data.get("data", {}).get("user", {})
        if user_data:
            result = {
                "username": user_data.get("username"),
                "profile_pic": user_data.get("profile_pic_url_hd"),
                "post_count": user_data.get("edge_owner_to_timeline_media", {}).get("count"),
                "followers_count": user_data.get("edge_followed_by", {}).get("count"),
                "following_count": user_data.get("edge_follow", {}).get("count"),
                "bio": user_data.get("biography"),
                "website": user_data.get("external_url"),
                "category": user_data.get("category_name"),
                "url": f"https://www.instagram.com/{username}/"
            }
            return result
        else:
            print("❌ ไม่พบข้อมูลผู้ใช้ใน JSON")
    else:
        print(f"❌ HTTP Error: {response.status_code}")
        print("💡 อาจต้องใช้ cookies หรือเปลี่ยน User-Agent")

    return None


if __name__ == "__main__":
    username = "chillpainai"  # กรอกชื่อผู้ใช้ Instagram ที่ต้องการ
    data = get_instagram_info(username)
    if data:
        print("✅ ดึงข้อมูลสำเร็จ:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("❌ ดึงข้อมูลไม่สำเร็จ")
