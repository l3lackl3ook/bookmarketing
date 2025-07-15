import requests
import re
from bs4 import BeautifulSoup


def get_channel_name(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 🔍 ดึงชื่อเพจจาก <meta property="og:title">
    meta_tag = soup.find('meta', property='og:title')
    if meta_tag and meta_tag.get('content'):
        return meta_tag['content']

    # 🔍 ถ้าไม่มี ลองหา <h1>
    h1 = soup.select_one('h1 span')
    return h1.get_text(strip=True) if h1 else None


def get_profile_pic(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 🔍 ดึง URL รูปโปรไฟล์จาก <meta property="og:image">
    meta_tag = soup.find('meta', property='og:image')
    if meta_tag and meta_tag.get('content'):
        return meta_tag['content']
    return None


def get_continuationCommand_token(url):
    response = requests.get(url)
    response_text = response.text
    pattern = r'"continuationCommand"\s*:\s*\{[^{}]*?"token"\s*:\s*"([^"]*)"'
    match = re.search(pattern, response_text)
    return match.group(1) if match else None


def parse_number(text):
    if not text:
        return 0
    text = text.lower().replace(',', '').strip()
    match = re.match(r"([\d\.]+)([kmb]?)", text)
    if not match:
        return 0
    number = float(match.group(1))
    suffix = match.group(2)
    multiplier = {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}.get(suffix, 1)
    return int(number * multiplier)


def get_youtube_info(url):
    page_name = get_channel_name(url)  # ✅ ดึงชื่อเพจ
    profile_pic = get_profile_pic(url)  # ✅ ดึงโปรไฟล์เพจ

    token = get_continuationCommand_token(url)
    if not token:
        print("❌ Token not found.")
        return None

    headers = {
        'accept': '*/*',
        'content-type': 'application/json',
        'user-agent': 'Mozilla/5.0',
        'x-youtube-client-name': '1',
    }
    json_data = {
        'context': {'client': {'clientName': 'WEB', 'clientVersion': '2.20250530.01.00'}},
        'continuation': token,
    }
    response = requests.post('https://www.youtube.com/youtubei/v1/browse', headers=headers, json=json_data)
    data = response.json()

    try:
        about = data['onResponseReceivedEndpoints'][0]['appendContinuationItemsAction']['continuationItems'][0][
            'aboutChannelRenderer']['metadata']['aboutChannelViewModel']

        result = {
            'page_name': page_name,
            'profile_pic': profile_pic,  # ✅ เพิ่มโปรไฟล์เพจ
            'bio': about.get('description', None),
            'country': about.get('country', None),
            'subscribers_count': parse_number(about.get('subscriberCountText', '0')),
            'total_views': parse_number(about.get('viewCountText', '0').replace(' views', '')),
            'join_date': about.get('joinedDateText', {}).get('content', None),
            'page_url': about.get('canonicalChannelUrl', None),
            'videos_count': parse_number(about.get('videoCountText', '0').replace(' videos', '')),
            'page_website': None
        }

        links = about.get('links', [])
        for link in links:
            title = link['channelExternalLinkViewModel']['title']['content']
            url = link['channelExternalLinkViewModel']['link']['content']
            if title.lower() == 'website':
                result['page_website'] = url

        return result
    except Exception as e:
        print(f"❌ Error extracting data: {e}")
        return None


if __name__ == "__main__":
    url = "https://www.youtube.com/@9arm."
    data = get_youtube_info(url)
    print(data)
