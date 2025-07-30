from datetime import datetime, timedelta, timezone  # ใส่ไว้บนสุดของ views.py ด้วย
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Prefetch
from django.conf import settings
from django.db import connection
from django.db.models import Count
from django.utils import timezone
from django.core.files import File
from .seeding_utils import is_seeding
from urllib.parse import unquote
from urllib.parse import urlparse
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from .forms import FacebookCommentForm  # ✅ import form ที่คุณสร้างแล้ว
from .forms import CommentDashboardForm  # ✅ อย่าลืม import
from .models import FacebookComment, FBCommentDashboard, CommentCampaignGroup
from .models import PageGroup, PageInfo, FollowerHistory
from .models import FacebookPost, TikTokPost
from .forms import PageGroupForm, PageURLForm, CommentDashboardForm
from .fb_comment_info import run_fb_comment_scraper
from .fb_page_info import PageInfo as FBPageInfo
from .fb_page_info import PageFollowers  # ✅ เพิ่มบรรทัดนี้
from .tiktok_page_info import get_tiktok_info  # แก้เป็น import get_tiktok_info
from .ig_page_info import get_instagram_info
from .lm8_page_info import get_lemon8_info  # ✅ เพิ่มบรรทัดนี้
from .yt_page_info import get_youtube_info
from .fb_post import FBPostScraperAsync
from .fb_video import FBVideoScraperAsync
from .fb_comment_info import run_fb_comment_scraper as run_seeding_comment_scraper
from .fb_comment import run_fb_comment_scraper as run_activity_comment_scraper
from .fb_like import run_fb_like_scraper
from .fb_share import run_fb_share_scraper
from .fb_reel import FBReelScraperAsync
from .fb_live import FBLiveScraperAsync
from collections import Counter
from collections import defaultdict
import asyncio
import calendar
import re
import os
import json  # 👈 ต้อง import นี้

def parse_timestamp(post):
    if isinstance(post.get('post_timestamp_dt'), datetime):
        return post['post_timestamp_dt']
    try:
        # กรณี TikTok ที่ใช้ string เช่น '23/07/2025'
        return datetime.strptime(post.get('post_timestamp_text') or post.get('post_timestamp', ''), '%d/%m/%Y')
    except:
        return None

def page_campaign_dashboard(request):
    if request.method == 'POST':
        form = PageGroupForm(request.POST)
        if form.is_valid():
            form.save()  # บันทึกกลุ่มใหม่
            return redirect('index')  # ไปที่หน้า index หรือหน้าอื่นที่ต้องการ
    else:
        form = PageGroupForm()  # กรณี GET ให้แสดงฟอร์มเปล่า
    return render(request, 'index.html', {'form': form})  # ส่งฟอร์มไปยังเทมเพลต

def posts_campaign(request, group_name):
    try:
        # หา CommentCampaignGroup ตาม group_name
        campaign_group = CommentCampaignGroup.objects.get(group_name=group_name)
    except CommentCampaignGroup.DoesNotExist:
        return HttpResponse("❌ ไม่พบแคมเปญนี้", status=404)

    # ดึงข้อมูล dashboard ที่เกี่ยวข้อง
    comment_dashboards = FBCommentDashboard.objects.filter(campaign_group=campaign_group)

    # ส่งข้อมูลไปยังเทมเพลต
    return render(request, 'PageInfo/posts_campaign.html', {
        'campaign_group': campaign_group,
        'comment_dashboards': comment_dashboards
    })

def comment_campaign_detail(request, pk):
    campaign = get_object_or_404(CommentCampaignGroup, pk=pk)

    return render(request, 'PageInfo/comment_campaign_detail.html', {
        'campaign': campaign
    })

def comment_dashboard_detail(request, dashboard_id):
    # ดึงข้อมูล dashboard โดยใช้ id ที่ได้รับจาก URL
    dashboard = get_object_or_404(FBCommentDashboard, id=dashboard_id)

    # ดึงข้อมูลคอมเมนต์ที่เกี่ยวข้องกับ dashboard_id
    comments = FacebookComment.objects.filter(dashboard=dashboard)

    # นับจำนวน sentiment สำหรับแสดงผลในกราฟ
    positive_count = comments.filter(sentiment="Positive").count()
    neutral_count = comments.filter(sentiment="neutral").count()
    negative_count = comments.filter(sentiment="negative").count()

    # เตรียมข้อมูลให้กับกราฟ
    comments_by_sentiment = {
        'positive': list(comments.filter(sentiment="Positive").values('author', 'content', 'sentiment')),
        'neutral': list(comments.filter(sentiment="neutral").values('author', 'content', 'sentiment')),
        'negative': list(comments.filter(sentiment="negative").values('author', 'content', 'sentiment')),
    }

    # เตรียมข้อมูลที่จำเป็นในการแสดงในกราฟ
    category_qs = comments.values('category').annotate(count=Count('category')).order_by('-count')
    category_labels = [item['category'] if item['category'] else 'ไม่ระบุ' for item in category_qs]
    category_counts = [item['count'] for item in category_qs]

    keyword_group_qs = comments.values('keyword_group').annotate(count=Count('keyword_group')).order_by('-count')[:10]
    keyword_group_labels = [item['keyword_group'] if item['keyword_group'] else 'ไม่ระบุ' for item in keyword_group_qs]
    keyword_group_counts = [item['count'] for item in keyword_group_qs]

    # กรองคอมเมนต์ seeding และ organic
    seeding_comments = [c for c in comments if is_seeding(c.author)]
    organic_comments = [c for c in comments if not is_seeding(c.author)]

    # คำนวณแยกคอมเมนต์ประเภท Seeding และ Organic
    seeding_comments = sorted(seeding_comments, key=lambda x: x.created_at, reverse=True)
    organic_comments = sorted(organic_comments, key=lambda x: x.created_at, reverse=True)

    # ส่งข้อมูลไปยังเทมเพลต
    context = {
        "dashboard": dashboard,
        "comments": comments,
        "positive_count": positive_count,
        "neutral_count": neutral_count,
        "negative_count": negative_count,
        "comments_by_sentiment_json": json.dumps(comments_by_sentiment, ensure_ascii=False),
        "category_labels": json.dumps(category_labels, ensure_ascii=False),
        "category_counts": json.dumps(category_counts),
        "keyword_group_labels": json.dumps(keyword_group_labels, ensure_ascii=False),
        "keyword_group_counts": json.dumps(keyword_group_counts),
        "seeding_comments": seeding_comments,
        "organic_comments": organic_comments,
    }

    return render(request, 'PageInfo/comment_dashboard.html', context)

def create_comment_campaign(request):
    if request.method == 'POST':
        group_name = request.POST.get('group_name')
        if group_name:
            CommentCampaignGroup.objects.create(group_name=group_name)
    return redirect('index')

@require_POST
def edit_comment(request, comment_id):
    comment = get_object_or_404(FacebookComment, id=comment_id)

    comment.content = request.POST.get("content")
    comment.sentiment = request.POST.get("sentiment")
    comment.category = request.POST.get("category")
    comment.keyword_group = request.POST.get("keyword_group")
    comment.reason = request.POST.get("reason")
    comment.save()

    # 🔁 redirect กลับไปหน้าเดิม
    return redirect(request.META.get('HTTP_REFERER', '/'))

def clean_reaction(value):
    """
    คืนค่า reaction เป็น integer
    ถ้าเป็น string เช่น 'ถูกใจ 5' จะดึงเลข 5
    ถ้าไม่มีตัวเลข จะคืน 0
    """
    if not value:
        return 0
    if isinstance(value, int):
        return value
    value_str = str(value)
    digits = ''.join(c for c in value_str if c.isdigit())
    return int(digits) if digits else 0

async def run_activity_pipeline(post_url, dashboard):
    # ✅ ดึงคอมเมนต์
    comment_result = await run_fb_comment_scraper(post_url)
    comments = comment_result.get("comments", [])

    # ✅ ดึง likes
    likes = await run_fb_like_scraper(post_url)

    # ✅ ดึง shares
    shares = await run_fb_share_scraper(post_url)

    # ✅ สร้าง set ของชื่อเพื่อเช็คเร็ว
    like_names = set(likes)
    share_names = set(shares)

    # ✅ เก็บใน DB พร้อมอัปเดต status
    for c in comments:
        author = c.get("author")
        if not author:
            continue

        like_status = "liked" if author in like_names else "not_liked"
        share_status = "shared" if author in share_names else "not_shared"

        FacebookComment.objects.create(
            post_url=post_url,
            dashboard=dashboard,
            author=author,
            profile_img_url=c.get("profile_img_url"),
            content=c.get("content"),
            reaction=c.get("reaction"),
            timestamp_text=c.get("timestamp_text"),
            image_url=c.get("image_url"),
            reply=c.get("reply"),
            like_status=like_status,
            share_status=share_status,
        )

def add_activity_dashboard(request):
    if request.method == "POST":
        post_url = request.POST.get("post_url")
        dashboard_name = request.POST.get("dashboard_name")

        if not post_url:
            return HttpResponse("❌ ไม่พบ post_url", status=400)

        # ✅ สร้าง dashboard ก่อน
        dashboard = FBCommentDashboard.objects.create(
            link_url=post_url,
            dashboard_name=dashboard_name or post_url,
            dashboard_type="activity"
        )

        # ✅ เรียกฟังก์ชัน pipeline
        asyncio.run(run_activity_pipeline(post_url, dashboard))

        return redirect(f"/comment-dashboard/?post_url={post_url}")

def extract_post_id(url):
    patterns = [
        r'permalink/(\d+)',
        r'posts/([a-zA-Z0-9]+)',
        r'story_fbid=(\d+)',
        r'/videos/(\d+)',
        r'fbid=(\d+)',
        r'comment_id=(\d+)'  # สำหรับคอมเมนต์ URL
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def normalize_url(url):
    return urlparse(url)._replace(query="", fragment="").geturl().rstrip('/')

def normalize_post(post):
    is_facebook = getattr(post, 'post_type', None) is not None

    return {
        'post_id': getattr(post, 'post_id', None) or '',
        'post_content': post.post_content,
        'post_imgs': post.post_imgs if is_facebook else [post.post_imgs] if post.post_imgs else [],
        'post_timestamp_dt': post.post_timestamp_dt if is_facebook else None,
        'post_timestamp_text': post.post_timestamp_text if is_facebook else post.post_timestamp,
        'reactions': post.reactions if is_facebook else {'reaction': post.reaction},
        'comment_count': post.comment_count or 0,
        'share_count': post.share_count or 0,
        'content_pillar': getattr(post, 'content_pillar', None),
        'platform': post.platform if hasattr(post, 'platform') else 'facebook',
        'page_name': post.page.page_name if post.page else '',
        'page_profile_pic': post.page.profile_pic if post.page else '',
        'page': post.page
    }

from django.db.models import Count
import json

def comment_dashboard_view(request):
    target_post_url = request.GET.get("post_url")

    if not target_post_url or target_post_url == "None":
        raw_url = request.GET.get("url", "")
        target_post_url = unquote(raw_url)

    if not target_post_url:
        return HttpResponse("❌ ไม่พบ post_url", status=400)

    dashboard = FBCommentDashboard.objects.filter(link_url__icontains=target_post_url).order_by("-created_at").first()

    if not dashboard:
        return HttpResponse("❌ ไม่พบ dashboard", status=404)

    all_comments = FacebookComment.objects.filter(post_url=target_post_url).exclude(
        timestamp_text__isnull=True).exclude(timestamp_text="").order_by("-created_at")

    # ✅ ถ้า POST -> update ค่า
    if request.method == "POST":
        for comment in all_comments:
            cid = str(comment.id)
            new_content = request.POST.get(f"content_{cid}")
            new_sentiment = request.POST.get(f"sentiment_{cid}")
            new_keyword_group = request.POST.get(f"keyword_group_{cid}")
            new_category = request.POST.get(f"category_{cid}")

            # ✅ อัปเดตค่าใน db
            comment.content = new_content
            comment.sentiment = new_sentiment
            comment.keyword_group = new_keyword_group
            comment.category = new_category
            comment.save()

        # ✅ หลัง save redirect กลับเพื่อ refresh หน้าและป้องกันการ resubmit
        return redirect(request.path + f"?post_url={target_post_url}")

    activity_comments = all_comments

    # ✅ นับจำนวน sentiment
    positive_count = all_comments.filter(sentiment="Positive").count()
    neutral_count = all_comments.filter(sentiment="neutral").count()
    negative_count = all_comments.filter(sentiment="negative").count()

    # ✅ ดึงคอมเมนต์แต่ละ sentiment สำหรับ popup modal
    positive_comments = list(all_comments.filter(sentiment="Positive").values(
        'profile_img_url', 'author', 'content', 'image_url', 'sentiment', 'reason'
    ))
    neutral_comments = list(all_comments.filter(sentiment="neutral").values(
        'profile_img_url', 'author', 'content', 'image_url', 'sentiment', 'reason'
    ))
    negative_comments = list(all_comments.filter(sentiment="negative").values(
        'profile_img_url', 'author', 'content', 'image_url', 'sentiment', 'reason'
    ))

    comments_by_sentiment = {
        'positive': positive_comments,
        'neutral': neutral_comments,
        'negative': negative_comments,
    }

    # ✅ นับจำนวน category
    category_qs = all_comments.values('category').annotate(count=Count('category')).order_by('-count')
    category_labels = [item['category'] if item['category'] else 'ไม่ระบุ' for item in category_qs]
    category_counts = [item['count'] for item in category_qs]

    # ✅ นับจำนวน keyword_group
    keyword_group_qs = all_comments.values('keyword_group').annotate(count=Count('keyword_group')).order_by('-count')[:10]
    keyword_group_labels = [item['keyword_group'] if item['keyword_group'] else 'ไม่ระบุ' for item in keyword_group_qs]
    keyword_group_counts = [item['count'] for item in keyword_group_qs]

    # ✅ comments by category
    category_comments = {}
    for cat in category_labels:
        comments = all_comments.filter(category=cat).values(
            'profile_img_url', 'author', 'content', 'image_url', 'sentiment', 'reason', 'category', 'keyword_group'
        )
        category_comments[cat] = list(comments)

    # ✅ comments by keyword_group
    keyword_group_comments = {}
    for kg in keyword_group_labels:
        comments = all_comments.filter(keyword_group=kg).values(
            'profile_img_url', 'author', 'content', 'image_url', 'sentiment', 'reason', 'keyword_group', 'category'
        )
        keyword_group_comments[kg] = list(comments)

    # ✅ prepare context
    context = {
        "dashboard": dashboard,
        "decoded_url": target_post_url,
        "activity_comments": activity_comments,
        "positive_count": positive_count,
        "neutral_count": neutral_count,
        "negative_count": negative_count,
        "comments_by_sentiment_json": json.dumps(comments_by_sentiment, ensure_ascii=False),
        "category_labels": json.dumps(category_labels, ensure_ascii=False),
        "category_counts": json.dumps(category_counts),
        "keyword_group_labels": json.dumps(keyword_group_labels, ensure_ascii=False),
        "keyword_group_counts": json.dumps(keyword_group_counts),
        "category_comments_json": json.dumps(category_comments, ensure_ascii=False),
        "keyword_group_comments_json": json.dumps(keyword_group_comments, ensure_ascii=False),
    }

    if dashboard.dashboard_type == "seeding":
        seeding_comments = [c for c in all_comments if is_seeding(c.author)]
        organic_comments = [c for c in all_comments if not is_seeding(c.author)]

        seeding_comments = sorted(seeding_comments, key=lambda x: clean_reaction(x.reaction), reverse=True)
        organic_comments = sorted(organic_comments, key=lambda x: clean_reaction(x.reaction), reverse=True)

        context.update({
            "seeding_comments": seeding_comments,
            "organic_comments": organic_comments,
        })

    elif dashboard.dashboard_type == "activity":
        liked_comments = [c for c in all_comments if c.like_status == "ถูกใจแล้ว"]
        unliked_comments = [c for c in all_comments if c.like_status != "ถูกใจแล้ว"]

        context.update({
            "comments": activity_comments,
            "liked_comments": liked_comments,
            "unliked_comments": unliked_comments,
        })

    return render(request, "PageInfo/comment_dashboard.html", context)

def add_comment_url(request):
    # รับค่าจาก request POST หรือ GET
    if request.method == "POST":
        link_url = request.POST.get("post_url")
        dashboard_name = request.POST.get("dashboard_name") or extract_post_id(link_url)
        dashboard_type = request.POST.get("dashboard_type") or "seeding"

        # รับ campaign_group_id จากฟอร์ม
        campaign_group_id = request.POST.get("post_campaign_id")

        # ตรวจสอบว่า campaign_group_id ได้ถูกส่งมาหรือไม่
        if not campaign_group_id:
            return HttpResponse("❌ ไม่พบ campaign_group_id", status=400)

        # ดึงข้อมูล CommentCampaignGroup จาก ID ที่ได้รับ
        try:
            campaign_group = CommentCampaignGroup.objects.get(id=campaign_group_id)
        except CommentCampaignGroup.DoesNotExist:
            return HttpResponse("❌ ไม่พบ campaign_group", status=404)

    elif request.method == "GET":
        link_url = request.GET.get("url")
        dashboard_name = extract_post_id(link_url) if link_url else None
        dashboard_type = request.GET.get("dashboard_type") or "seeding"
        campaign_group = None  # ในกรณีนี้ไม่มี campaign_group_id

    else:
        return redirect('index')

    if not link_url:
        return HttpResponse("❌ ไม่พบ URL", status=400)

    # ตรวจสอบ URL ให้ถูกต้อง
    validate = URLValidator()
    try:
        validate(link_url)
    except ValidationError:
        return HttpResponse("❌ URL ไม่ถูกต้อง", status=400)

    normalized_link_url = normalize_url(link_url)

    # สร้าง dashboard
    dashboard = FBCommentDashboard.objects.create(
        post_id=normalized_link_url,  # ใช้ post_id แทน link_url
        dashboard_name=dashboard_name[:255] if dashboard_name else "",
        dashboard_type=dashboard_type,
        campaign_group=campaign_group  # เชื่อมโยงกับ campaign_group
    )

    # ถ้าเป็น dashboard_type = "seeding"
    if dashboard_type == "seeding":
        result = asyncio.run(run_seeding_comment_scraper(link_url))
        comments = result.get("comments", [])
        screenshot_path = result.get("post_screenshot_path")

        for c in comments:
            FacebookComment.objects.create(
                post_url=normalized_link_url,
                dashboard=dashboard,
                author=c.get("author"),
                profile_img_url=c.get("profile_img_url"),
                content=c.get("content"),
                reaction=c.get("reaction"),
                timestamp_text=c.get("timestamp_text"),
                image_url=c.get("image_url"),
                reply=c.get("reply"),
            )

        if screenshot_path:
            abs_path = os.path.join("media", screenshot_path)
            if os.path.exists(abs_path):
                with open(abs_path, "rb") as f:
                    dashboard.screenshot_path.save(os.path.basename(abs_path), File(f), save=True)

    # ถ้าเป็น dashboard_type = "activity"
    elif dashboard_type == "activity":
        result = asyncio.run(run_activity_comment_scraper(link_url))
        comments = result.get("comments", [])
        likes = asyncio.run(run_fb_like_scraper(link_url))
        shares = asyncio.run(run_fb_share_scraper(link_url))

        like_names = set(likes)
        share_names = set(shares)

        for c in comments:
            name = c.get("author")
            FacebookComment.objects.create(
                post_url=normalized_link_url,
                dashboard=dashboard,
                author=name,
                profile_img_url=c.get("profile_img_url"),
                content=c.get("content"),
                reaction=c.get("reaction"),
                timestamp_text=c.get("timestamp_text"),
                image_url=c.get("image_url"),
                reply=c.get("reply"),
                like_status="ถูกใจแล้ว" if name in like_names else "ยังไม่ถูกใจ",
                share_status="แชร์แล้ว" if name in share_names else "ยังไม่แชร์",
            )

    # รีไดเร็กต์ไปยังหน้าแสดงข้อมูลของ campaign_group
    return redirect(f"/posts-campaign/{campaign_group.id}/")



def get_pillar_summary_from_pages(page_ids):
    from django.db import connection
    if not page_ids:
        return []

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT content_pillar, COUNT(*) AS post_count
            FROM "PageInfo_facebookpost"
            WHERE page_id = ANY(%s)
            GROUP BY content_pillar
            ORDER BY post_count DESC
        """, [page_ids])
        return [{'pillar': row[0], 'post_count': row[1]} for row in cursor.fetchall()]


def extract_top_hashtags(posts, top_n=50):
    hashtag_counter = Counter()
    for post in posts:
        content = getattr(post, 'post_content', '') or ''
        hashtags = re.findall(r"#\S+", content)
        for tag in hashtags:
            hashtag_counter[tag.lower()] += 1
    return hashtag_counter.most_common(top_n)

def clean_number(value):
    if isinstance(value, str):
        value = value.lower().replace(',', '').replace(' videos', '').replace(' views', '').replace(' subscribers', '').strip()
        if 'k' in value:
            return int(float(value.replace('k', '')) * 1_000)
        elif 'm' in value:
            return int(float(value.replace('m', '')) * 1_000_000)
        elif 'b' in value:
            return int(float(value.replace('b', '')) * 1_000_000_000)
        try:
            return int(value)
        except ValueError:
            return 0
    elif isinstance(value, (int, float)):
        return int(value)
    else:
        return 0

async def run_fb_post_video_reel_live_scraper(url, cookie_path, cutoff_dt):
    posts_scraper = FBPostScraperAsync(cookie_file=cookie_path, headless=False, page_url=url, cutoff_dt=cutoff_dt)
    videos_scraper = FBVideoScraperAsync(cookie_file=cookie_path, headless=False, page_url=url, cutoff_dt=cutoff_dt)
    reels_scraper = FBReelScraperAsync(cookie_file=cookie_path, headless=False, page_url=url, cutoff_dt=cutoff_dt)
    lives_scraper = FBLiveScraperAsync(cookie_file=cookie_path, headless=False, page_url=url, cutoff_dt=cutoff_dt)

    posts = await posts_scraper.run()
    videos = await videos_scraper.run()
    reels = await reels_scraper.run()
    lives = await lives_scraper.run()

    return (posts or []) + (videos or []) + (reels or []) + (lives or [])


def add_page(request, group_id):
    group = PageGroup.objects.get(id=group_id)

    if request.method == 'POST':
        form = PageURLForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['url']
            platform = form.cleaned_data['platform']
            allowed_fields = {f.name for f in PageInfo._meta.get_fields()}

            if platform == 'facebook':
                fb_data = FBPageInfo(url)
                if 'page_id' in fb_data:
                    follower_data = PageFollowers(fb_data['page_id'])
                    if follower_data:
                        fb_data.update(follower_data)

                filtered_data = {k: v for k, v in fb_data.items() if k in allowed_fields}
                for key in ['page_likes_count', 'page_followers_count']:
                    value = filtered_data.get(key)
                    if isinstance(value, str):
                        filtered_data[key] = int(value.replace(',', ''))
                filtered_data['platform'] = 'facebook'

                # ✅ สร้าง PageInfo ก่อน
                page_obj = PageInfo.objects.create(page_group=group, **filtered_data)

                try:
                    cutoff_date = datetime.now() - timedelta(days=30)
                    cookie_path = os.path.join(settings.BASE_DIR, 'PageInfo', 'cookie.json')
                    posts = asyncio.run(run_fb_post_video_reel_live_scraper(url, cookie_path, cutoff_date))

                    for post in posts or []:
                        post_type = post.get("post_type", "post")
                        post_url = post.get("video_url") if post_type in ["video", "reel", "live"] else post.get(
                            "post_url")
                        post_imgs = (post.get("post_imgs") or []) + (
                            [post.get("video_thumbnail")] if post.get("video_thumbnail") else [])

                        # ✅ Fallback เวลา: ใช้ post_timestamp_dt หรือ post_date
                        post_timestamp_dt = post.get("post_timestamp_dt") or post.get("post_date")
                        if post_timestamp_dt and timezone.is_naive(post_timestamp_dt):
                            post_timestamp_dt = timezone.make_aware(post_timestamp_dt)

                        # ✅ สร้างข้อความเวลา หากไม่มี
                        post_timestamp_text = post.get("post_timestamp_text")
                        if not post_timestamp_text and post_timestamp_dt:
                            try:
                                post_timestamp_text = post_timestamp_dt.strftime("วัน%Aที่ %-d %B %Y เวลา %H:%M น.")
                            except:
                                post_timestamp_text = post_timestamp_dt.strftime("วัน%Aที่ %d %B %Y เวลา %H:%M น.")

                        FacebookPost.objects.update_or_create(
                            post_id=post["post_id"],
                            defaults={
                                'page': page_obj,
                                'post_url': post_url,
                                'post_type': post_type,
                                'post_timestamp_dt': post_timestamp_dt,
                                'post_timestamp_text': post_timestamp_text or "",
                                'post_content': post.get('post_content', ""),
                                'post_imgs': post_imgs,
                                'reactions': post.get('reactions', {}),
                                'comment_count': post.get('comment_count', 0),
                                'share_count': post.get('share_count', 0),
                                'watch_count': post.get('watch_count'),
                            }
                        )
                except Exception as e:
                    print("❌ Error fetching posts:", e)

            elif platform == 'tiktok':
                # ✅ ดึงข้อมูลโปรไฟล์ก่อน
                tiktok_data = get_tiktok_info(url)
                if not tiktok_data:
                    form.add_error(None, "❌ ไม่สามารถดึงข้อมูล TikTok ได้ กรุณาตรวจสอบ URL หรือรอสักครู่")
                    return render(request, 'PageInfo/add_page.html', {'form': form, 'group': group})

                # ✅ สร้าง PageInfo สำหรับ TikTok
                filtered_data = {
                    'page_username': tiktok_data.get('username'),
                    'page_name': tiktok_data.get('nickname'),
                    'page_followers': tiktok_data.get('followers', 0),
                    'page_likes': tiktok_data.get('likes', 0),
                    'following_count': tiktok_data.get('following', 0),
                    'page_videos_count': tiktok_data.get('video_count', 0),
                    'page_description': tiktok_data.get('bio'),
                    'profile_pic': tiktok_data.get('profile_pic'),
                    'page_url': tiktok_data.get('url'),
                    'verified': tiktok_data.get('verified', False),
                    'platform': 'tiktok'
                }

                # ✅ กรองเฉพาะ field ที่มีใน model
                filtered_data = {k: v for k, v in filtered_data.items() if k in allowed_fields}

                # ✅ สร้าง PageInfo ก่อน
                page_obj = PageInfo.objects.create(page_group=group, **filtered_data)
                print(f"✅ สร้าง PageInfo สำหรับ TikTok สำเร็จ: {page_obj.page_username}")

                # ✅ ดึงข้อมูลโพสต์ TikTok
                try:
                    from .tiktok_post import scrape_tiktok_posts_for_django, filter_recent_posts

                    # กำหนดพาธไฟล์ cookies ที่บันทึกไว้
                    cookie_path = os.path.join(settings.BASE_DIR, 'PageInfo', 'tiktok_cookies.json')

                    # เรียก scraper และรับผลลัพธ์เป็น dict
                    scrape_result = scrape_tiktok_posts_for_django(
                        profile_url=url,
                        cookies_file=cookie_path,
                        max_posts=None,
                        headless=True,
                        scroll_rounds=50,
                        timeout=30000
                    )

                    # ตรวจสอบว่าการดึงข้อมูลสำเร็จหรือไม่
                    if not scrape_result.get('success'):
                        print(f"❌ Error fetching TikTok posts: {scrape_result.get('message')}")
                        # ถึงแม้จะ error ก็ยังคง PageInfo ไว้
                        pass
                    else:
                        posts_data = scrape_result.get('data', [])
                        # หากต้องการกรองเฉพาะโพสต์ช่วง 30 วันที่ผ่านมา สามารถใช้ filter_recent_posts
                        posts_data = filter_recent_posts(posts_data, days=30)
                        print(f"📋 ดึงข้อมูล {len(posts_data)} โพสต์จาก TikTok")

                        for post in posts_data:
                            # ✅ แปลงวันที่จาก timestamp_unix หรือ string เป็น datetime object
                            post_timestamp_dt = None
                            post_timestamp_text = post.get('timestamp', '')
                            # ใช้ timestamp_unix ถ้ามี
                            ts_unix = post.get('timestamp_unix')
                            if ts_unix:
                                try:
                                    # แปลง unix timestamp เป็น datetime (UTC) แล้วแปลงเป็นเขตเวลาปัจจุบัน
                                    dt_utc = datetime.fromtimestamp(int(ts_unix), tz=timezone.utc)
                                    post_timestamp_dt = dt_utc.astimezone(timezone.get_default_timezone())
                                except Exception as e:
                                    print(f"⚠️ ไม่สามารถแปลง timestamp_unix '{ts_unix}': {e}")
                                    post_timestamp_dt = None
                            # หากไม่มี timestamp_unix ลอง parse จาก string 'dd/mm/YYYY'
                            if post_timestamp_dt is None and post_timestamp_text and post_timestamp_text != 'ไม่พบวันที่':
                                try:
                                    dt = datetime.strptime(post_timestamp_text, '%d/%m/%Y')
                                    if timezone.is_naive(dt):
                                        post_timestamp_dt = timezone.make_aware(dt)
                                    else:
                                        post_timestamp_dt = dt
                                except ValueError as e:
                                    print(f"⚠️ ไม่สามารถแปลงวันที่ '{post_timestamp_text}': {e}")
                                    post_timestamp_dt = None

                            # ✅ สร้างหรืออัปเดต TikTokPost (ตัดทอนค่า URL ไม่เกิน max_length)
                            TikTokPost.objects.update_or_create(
                                post_url=(post.get('post_url') or '')[:500],
                                defaults={
                                    'page': page_obj,
                                    'post_content': post.get('post_content', ''),
                                    'post_imgs': (post.get('post_thumbnail') or '')[:500],
                                    'post_timestamp': post_timestamp_text,
                                    'post_timestamp_dt': post_timestamp_dt,
                                    'like_count': post.get('reaction', 0),
                                    'comment_count': post.get('comment', 0),
                                    'share_count': post.get('shared', 0),
                                    'save_count': post.get('saved', 0),
                                    'view_count': post.get('views', 0),
                                    'platform': 'tiktok'
                                }
                            )

                        print(f"✅ บันทึกข้อมูล {len(posts_data)} โพสต์ TikTok สำเร็จ")

                except Exception as e:
                    print(f"❌ Error fetching TikTok posts: {e}")
                    # ✅ ถึงแม้จะ error ก็ยังคง PageInfo ไว้
                    pass

            elif platform == 'instagram':
                match = re.search(r"instagram\.com/([\w\.\-]+)/?", url)
                if match:
                    username = match.group(1)
                    ig_data = get_instagram_info(username)
                    if ig_data:
                        filtered_data = {
                            'page_username': ig_data.get('username'),
                            'page_name': ig_data.get('username'),
                            'page_followers': ig_data.get('followers_count'),
                            'page_website': ig_data.get('website'),
                            'page_category': ig_data.get('category'),
                            'post_count': ig_data.get('post_count'),
                            'page_description': ig_data.get('bio'),
                            'profile_pic': ig_data.get('profile_pic'),
                            'page_url': ig_data.get('url'),
                            'platform': 'instagram'
                        }
                        filtered_data = {k: v for k, v in filtered_data.items() if k in allowed_fields}
                        PageInfo.objects.create(page_group=group, **filtered_data)
                    else:
                        form.add_error(None, "❌ ไม่สามารถดึงข้อมูล Instagram ได้ กรุณาตรวจสอบ URL หรือรอสักครู่")
                        return render(request, 'PageInfo/add_page.html', {'form': form, 'group': group})
                else:
                    form.add_error(None, "❌ URL Instagram ไม่ถูกต้อง")
                    return render(request, 'PageInfo/add_page.html', {'form': form, 'group': group})

            elif platform == 'lemon8':
                lm8_data = get_lemon8_info(url)
                if lm8_data:
                    allowed_fields = {f.name for f in PageInfo._meta.get_fields()}
                    filtered_data = {
                        'page_username': lm8_data.get('username'),
                        'page_name': lm8_data.get('username'),
                        'page_followers': lm8_data.get('followers_count'),
                        'page_likes': lm8_data.get('likes_count'),
                        'following_count': lm8_data.get('following_count'),
                        'age': lm8_data.get('age'),
                        'page_description': lm8_data.get('bio'),
                        'page_website': lm8_data.get('website'),
                        'profile_pic': lm8_data.get('profile_pic'),
                        'page_url': lm8_data.get('url'),
                        'platform': 'lemon8'
                    }
                    filtered_data = {k: v for k, v in filtered_data.items() if k in allowed_fields}
                    PageInfo.objects.create(page_group=group, **filtered_data)
                else:
                    form.add_error(None, "❌ ไม่สามารถดึงข้อมูล Lemon8 ได้ กรุณาตรวจสอบ URL หรือรอสักครู่")
                    return render(request, 'PageInfo/add_page.html', {'form': form, 'group': group})

            elif platform == 'youtube':
                from .yt_page_info import get_youtube_info
                yt_data = get_youtube_info(url)
                if yt_data:
                    allowed_fields = {f.name for f in PageInfo._meta.get_fields()}
                    yt_data['subscribers_count'] = clean_number(yt_data.get('subscribers_count'))
                    yt_data['videos_count'] = clean_number(yt_data.get('videos_count'))
                    yt_data['total_views'] = clean_number(yt_data.get('total_views'))
                    filtered_data = {
                        'page_username': yt_data.get('username'),
                        'page_name': yt_data.get('page_name'),
                        'page_followers': yt_data.get('subscribers_count'),
                        'profile_pic': yt_data.get('profile_pic'),
                        'page_url': yt_data.get('page_url'),
                        'page_description': yt_data.get('bio'),
                        'page_address': yt_data.get('country'),
                        'page_join_date': yt_data.get('join_date'),
                        'page_videos_count': yt_data.get('videos_count'),
                        'page_total_views': yt_data.get('total_views'),
                        'page_website': yt_data.get('page_website'),
                        'platform': 'youtube'
                    }
                    filtered_data = {k: v for k, v in filtered_data.items() if k in allowed_fields}
                    PageInfo.objects.create(page_group=group, **filtered_data)
                else:
                    form.add_error(None, "❌ ไม่สามารถดึงข้อมูล YouTube ได้ กรุณาตรวจสอบ URL หรือรอสักครู่")
                    return render(request, 'PageInfo/add_page.html', {'form': form, 'group': group})

            return redirect('group_detail', group_id=group.id)

    else:
        form = PageURLForm()

    return render(request, 'PageInfo/add_page.html', {'form': form, 'group': group})



def create_group(request):
    if request.method == 'POST':
        form = PageGroupForm(request.POST)
        if form.is_valid():
            page_group = form.save()
            return redirect('group_detail', group_id=page_group.id)
    else:
        form = PageGroupForm()

    return render(request, 'index.html', {'form': form})

    # ส่งฟอร์มไปยัง template
    return render(request, 'PageInfo/index.html', {'form': form})

def group_detail(request, group_id):
    group = get_object_or_404(PageGroup, id=group_id)
    pages = group.pages.all().order_by('-page_followers_count')
    # ดึงโพสต์ Facebook ทั้งหมดของเพจในกลุ่ม
    posts = FacebookPost.objects.filter(page__in=pages)

    # ดึงโพสต์ TikTok ของเพจในกลุ่ม (ถ้ามี) เพื่อแสดงในหน้า group_detail
    tiktok_posts = TikTokPost.objects.filter(page__in=pages).order_by('-post_timestamp_dt')
    # 👇 Ensure TikTok posts have a datetime for timestamp
    # Some TikTok posts may only have a date string (e.g. "dd/mm/YYYY"), so parse it into a datetime
    from datetime import datetime
    from django.utils import timezone as dj_tz
    parsed_tiktok_posts = []
    for p in tiktok_posts:
        if not p.post_timestamp_dt:
            ts_str = p.post_timestamp
            if ts_str and ts_str != 'ไม่พบวันที่':
                try:
                    naive_dt = datetime.strptime(ts_str, '%d/%m/%Y')
                    aware_dt = dj_tz.make_aware(naive_dt)
                    p.post_timestamp_dt = aware_dt
                except Exception:
                    # leave as None
                    pass
        parsed_tiktok_posts.append(p)
    # Use parsed_tiktok_posts instead of original queryset for charts
    tiktok_posts = parsed_tiktok_posts

    sidebar = sidebar_context(request)

    # 🔟 Top 10 Posts across all platforms by engagement
    # Build a unified list of posts combining Facebook and TikTok with a consistent schema
    unified_posts = []
    # Handle Facebook posts
    for f_post in posts:
        # Compute total engagement for facebook as likes + comments + shares
        likes_count = 0
        if isinstance(f_post.reactions, dict):
            likes_count = f_post.reactions.get('ถูกใจ', 0)
        total_eng_f = likes_count + (f_post.comment_count or 0) + (f_post.share_count or 0)
        unified_posts.append({
            'platform': 'facebook',
            'post_id': f_post.post_id,
            'post_url': None,
            'post_content': f_post.post_content,
            'post_imgs': f_post.post_imgs or [],
            'post_timestamp_dt': f_post.post_timestamp_dt,
            'post_timestamp_str': f_post.post_timestamp_dt.strftime('%Y-%m-%d %H:%M') if f_post.post_timestamp_dt else '',
            'like_count': likes_count,
            'comment_count': f_post.comment_count or 0,
            'share_count': f_post.share_count or 0,
            'save_count': 0,
            'view_count': 0,
            'reactions': f_post.reactions or {},
            'total_engagement': total_eng_f,
            'page_name': f_post.page.page_name if f_post.page else '',
            'profile_pic': f_post.page.profile_pic if f_post.page else '',
            'content_pillar': f_post.content_pillar or '',
        })
    # Handle TikTok posts
    for t_post in tiktok_posts:
        total_eng_t = (t_post.like_count or 0) + (t_post.comment_count or 0) + (t_post.share_count or 0) + (t_post.save_count or 0)
        unified_posts.append({
            'platform': 'tiktok',
            'post_id': None,
            'post_url': t_post.post_url,
            'post_content': t_post.post_content,
            'post_imgs': [t_post.post_imgs] if t_post.post_imgs else [],
            'post_timestamp_dt': t_post.post_timestamp_dt,
            'post_timestamp_str': t_post.post_timestamp_dt.strftime('%Y-%m-%d %H:%M') if t_post.post_timestamp_dt else (t_post.post_timestamp or ''),
            'like_count': t_post.like_count or 0,
            'comment_count': t_post.comment_count or 0,
            'share_count': t_post.share_count or 0,
            'save_count': t_post.save_count or 0,
            'view_count': t_post.view_count or 0,
            'reactions': None,
            'total_engagement': total_eng_t,
            'page_name': t_post.page.page_name if t_post.page else '',
            'profile_pic': t_post.page.profile_pic if t_post.page else '',
            'content_pillar': '',
        })
    # Sort unified posts by total engagement descending and then by view_count for tiktok as secondary
    unified_sorted = sorted(
        unified_posts,
        key=lambda p: (p['total_engagement'], p.get('view_count', 0)),
        reverse=True
    )[:10]

    unified_top_posts = []
    for p in unified_sorted:
        # Compute engagement rate: use total_engagement divided by view_count (if available) or followers? Use simple ratio: total_engagement / 100 as placeholder
        engagement_rate = 0.0
        if p['platform'] == 'tiktok':
            # avoid division by zero
            if p['view_count']:
                engagement_rate = round((p['total_engagement'] / p['view_count']) * 100, 2)
            else:
                engagement_rate = 0.0
        else:
            engagement_rate = round((p['total_engagement'] / 100), 1)
        unified_top_posts.append({
            'platform': p['platform'],
            'post_id': p['post_id'],
            'post_url': p['post_url'],
            'post_content': p['post_content'],
            'post_imgs': p['post_imgs'],
            'post_timestamp': p['post_timestamp_str'],
            'like_count': p['like_count'],
            'comment_count': p['comment_count'],
            'share_count': p['share_count'],
            'save_count': p.get('save_count', 0),
            'view_count': p.get('view_count', 0),
            'reactions': p['reactions'],
            'total_engagement': p['total_engagement'],
            'engagement_rate': engagement_rate,
            'content_pillar': p['content_pillar'],
            'page_name': p['page_name'],
            'page_profile_pic': p['profile_pic'],
        })

    # Assign unified_top_posts to top10_posts_data for backward compatibility
    top10_posts_data = unified_top_posts

    # 🕺 Top TikTok posts by view count (for groups that include TikTok pages)
    # จัดลำดับโพสต์ TikTok ตามจำนวนผู้ชม (view_count)
    top10_tiktok_posts_data = []
    if tiktok_posts:
        # หาผลรวม top 10 ตาม view_count หรือ like_count หากไม่มี view_count ให้ใช้ 0
        top10_tiktok_posts = sorted(
            tiktok_posts,
            key=lambda p: (p.view_count or 0),
            reverse=True
        )[:10]

        for t_post in top10_tiktok_posts:
            top10_tiktok_posts_data.append({
                'post_url': t_post.post_url,
                'post_content': t_post.post_content,
                # TikTokPost มี post_imgs เป็น string เดียว ดังนั้นแปลงเป็น list เพื่อใช้ร่วมกับ template ที่คาดว่าเป็น list
                'post_imgs': [t_post.post_imgs] if t_post.post_imgs else [],
                'post_timestamp': t_post.post_timestamp_dt.strftime('%Y-%m-%d %H:%M') if t_post.post_timestamp_dt else (t_post.post_timestamp or ''),
                'view_count': t_post.view_count or 0,
                'like_count': t_post.like_count or 0,
                'comment_count': t_post.comment_count or 0,
                'share_count': t_post.share_count or 0,
                'save_count': t_post.save_count or 0,
                'page_name': t_post.page.page_name if t_post.page else '',
                'page_profile_pic': t_post.page.profile_pic if t_post.page else '',
                'platform': 'tiktok',
            })

    colors = ['#e20414', '#2e3d93', '#fbd305', '#355e73', '#0c733c', '#c94087']

    # 📊 Followers Chart & Interaction Pie Chart
    chart_data = []
    # Calculate total interactions by summing total engagement for Facebook and TikTok posts separately
    interaction_totals = defaultdict(int)
    # Facebook posts
    for f_post in posts:
        if not f_post.page:
            continue
        # Sum up like_count from reactions and comments/shares
        reactions = f_post.reactions or {}
        if isinstance(reactions, str):
            try:
                reactions = json.loads(reactions)
            except json.JSONDecodeError:
                reactions = {}
        like_count = reactions.get('ถูกใจ', 0)
        total_eng = like_count + (f_post.comment_count or 0) + (f_post.share_count or 0)
        interaction_totals[str(f_post.page.id)] += total_eng
    # TikTok posts
    for t_post in tiktok_posts:
        if not t_post.page:
            continue
        total_eng = (t_post.like_count or 0) + (t_post.comment_count or 0) + (t_post.share_count or 0) + (t_post.save_count or 0)
        interaction_totals[str(t_post.page.id)] += total_eng
    total_interactions = sum(interaction_totals.values())
    interaction_data = []
    for i, page in enumerate(pages):
        interactions = interaction_totals.get(str(page.id), 0)
        interaction_data.append({
            'id': page.id,
            'name': page.page_name or page.page_username or 'Unnamed',
            'interactions': interactions,
            'percent': round((interactions / total_interactions * 100) if total_interactions else 0, 1),
            'color': colors[i % len(colors)],
            'platform': page.platform or 'facebook',
        })
        # Use page_followers_count when available, otherwise fallback to page_followers
        follower_count = page.page_followers_count or page.page_followers or 0
        chart_data.append({
            'id': page.id,
            'name': page.page_name or page.page_username or 'Unnamed',
            'followers': follower_count,
            'profile_pic': page.profile_pic or '',
            'platform': page.platform or 'facebook',
            'color': colors[i % len(colors)]
        })

    # 🔁 followers_posts_map เพื่อ popup โพสต์ของแต่ละเพจ
    # Include posts from both Facebook and TikTok so the bar chart popup shows posts for all platforms.
    followers_posts_map = defaultdict(list)
    # Facebook posts: add platform and page info for each post
    for f_post in posts:
        # Skip posts without a page relationship
        if not f_post.page:
            continue
        reactions = f_post.reactions or {}
        # If reactions field is a JSON string, attempt to decode it
        if isinstance(reactions, str):
            try:
                reactions = json.loads(reactions)
            except json.JSONDecodeError:
                reactions = {}
        like_count = reactions.get('ถูกใจ', 0)
        total_eng = like_count + (f_post.comment_count or 0) + (f_post.share_count or 0)
        post_entry = {
            'platform': 'facebook',
            'post_id': f_post.post_id,
            'post_url': None,
            'post_content': f_post.post_content,
            'post_imgs': f_post.post_imgs or [],
            'post_timestamp': f_post.post_timestamp_dt.strftime('%Y-%m-%d %H:%M') if f_post.post_timestamp_dt else '',
            'reactions': reactions,
            'comment_count': f_post.comment_count or 0,
            'share_count': f_post.share_count or 0,
            'like_count': like_count,
            'save_count': 0,
            'view_count': 0,
            'total_engagement': total_eng,
            # duplicate page info at top level for convenience
            'profile_pic': f_post.page.profile_pic,
            'page_name': f_post.page.page_name,
            # nested page details (may include platform)
            'page': {
                'page_name': f_post.page.page_name,
                'profile_pic': f_post.page.profile_pic,
                'platform': 'facebook',
            }
        }
        followers_posts_map[str(f_post.page.id)].append(post_entry)

    # TikTok posts
    for t_post in tiktok_posts:
        if not t_post.page:
            continue
        # Determine timestamp string (TikTok may have only date string)
        if t_post.post_timestamp_dt:
            timestamp_str = t_post.post_timestamp_dt.strftime('%Y-%m-%d %H:%M')
        else:
            timestamp_str = t_post.post_timestamp or ''
        post_entry = {
            'platform': 'tiktok',
            'post_id': None,
            'post_url': t_post.post_url,
            'post_content': t_post.post_content,
            # TikTokPost has post_imgs as single string; wrap in list for template
            'post_imgs': [t_post.post_imgs] if t_post.post_imgs else [],
            'post_timestamp': timestamp_str,
            'reactions': None,
            'comment_count': t_post.comment_count or 0,
            'share_count': t_post.share_count or 0,
            'like_count': t_post.like_count or 0,
            'save_count': t_post.save_count or 0,
            'view_count': t_post.view_count or 0,
            'total_engagement': (t_post.like_count or 0) + (t_post.comment_count or 0) + (t_post.share_count or 0) + (t_post.save_count or 0),
            # duplicate page info at top level
            'profile_pic': t_post.page.profile_pic,
            'page_name': t_post.page.page_name,
            # nested page details with platform
            'page': {
                'page_name': t_post.page.page_name,
                'profile_pic': t_post.page.profile_pic,
                'platform': 'tiktok',
            }
        }
        followers_posts_map[str(t_post.page.id)].append(post_entry)

    # 📅 Number of posts by weekday (Bar Chart) for combined posts (Facebook + TikTok)
    day_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day_counts = Counter()
    posts_grouped_by_day = defaultdict(list)
    # Iterate through unified_posts to count posts per weekday and build grouping
    for p in unified_posts:
        if p['post_timestamp_dt']:
            weekday = p['post_timestamp_dt'].weekday()
            day_counts[weekday] += 1
            entry = {
                'platform': p['platform'],
                'post_id': p['post_id'],
                'post_url': p['post_url'],
                'post_content': p['post_content'],
                'post_imgs': p['post_imgs'],
                'post_timestamp': p['post_timestamp_str'],
                'reactions': p['reactions'],
                'like_count': p['like_count'],
                'comment_count': p['comment_count'],
                'share_count': p['share_count'],
                'save_count': p.get('save_count', 0),
                'view_count': p.get('view_count', 0),
                'total_engagement': p['total_engagement'],
                'page_name': p['page_name'],
                'profile_pic': p['profile_pic'],
            }
            posts_grouped_by_day[str(weekday)].append(entry)
    bar_day_labels = day_labels
    bar_day_values = [day_counts.get(i, 0) for i in range(7)]
    bar_day_colors = [colors[i % len(colors)] for i in range(7)]

    # 🕒 Best Times To Post (Bubble Chart) for combined posts
    bubble_grouped = defaultdict(list)
    posts_grouped_by_time = defaultdict(list)
    for p in unified_posts:
        if not p['post_timestamp_dt']:
            continue
        weekday = p['post_timestamp_dt'].weekday()
        hour = p['post_timestamp_dt'].hour
        hour_slot = (hour // 2) * 2
        key = f"{weekday}_{hour_slot}"
        bubble_grouped[key].append(p)

    bubble_data = []
    for key, grouped_posts in bubble_grouped.items():
        weekday, hour_slot = map(int, key.split('_'))
        count = len(grouped_posts)
        # Sum likes/comments/shares across platforms
        total_likes = sum(g['like_count'] if g['platform'] == 'tiktok' else (g['reactions'].get('ถูกใจ', 0) if g['reactions'] else 0) for g in grouped_posts)
        total_comments = sum(g['comment_count'] for g in grouped_posts)
        total_shares = sum(g['share_count'] for g in grouped_posts)
        bubble_data.append({
            'x': weekday,
            'y': hour_slot,
            'r': max(5, min(20, int(count ** 1.1))),
            'count': count,
            'likes': total_likes,
            'comments': total_comments,
            'shares': total_shares,
            'tooltip_label': f"{day_labels[weekday]} {hour_slot:02d}:00 - {hour_slot + 2:02d}:00",
            'key': key
        })
        for g in grouped_posts:
            entry = {
                'platform': g['platform'],
                'post_id': g['post_id'],
                'post_url': g['post_url'],
                'post_content': g['post_content'],
                'post_imgs': g['post_imgs'],
                'post_timestamp': g['post_timestamp_str'],
                'reactions': g['reactions'],
                'like_count': g['like_count'],
                'comment_count': g['comment_count'],
                'share_count': g['share_count'],
                'save_count': g.get('save_count', 0),
                'view_count': g.get('view_count', 0),
                'total_engagement': g['total_engagement'],
                'page': {
                    'page_name': g['page_name'],
                    'profile_pic': g['profile_pic']
                }
            }
            posts_grouped_by_time[key].append(entry)

    # 📌 ย้ายออกมาไว้หลัง bubble_data ทำงานเสร็จแล้ว
    pillar_summary = posts.values('content_pillar').annotate(post_count=Count('id')).order_by(
        '-post_count') if posts else []
    posts_by_pillar = [{"pillar": post.content_pillar, "post": post} for post in posts]

    return render(request, 'PageInfo/group_detail.html', {
        'group': group,
        'pages': pages,
        'chart_data_json': json.dumps(chart_data),
        'interaction_data_json': json.dumps(interaction_data),
        'bar_day_labels': json.dumps(bar_day_labels),
        'bar_day_values': json.dumps(bar_day_values),
        'bar_day_colors': json.dumps(bar_day_colors),
        'bubble_data': json.dumps(bubble_data),
        'posts_grouped_json': json.dumps(posts_grouped_by_time),
        'posts_by_day_json': json.dumps(posts_grouped_by_day),
        'followers_posts_map': json.dumps(followers_posts_map),
        # unified top posts across platforms for display
        'unified_top_posts': unified_top_posts,
        # separate lists for backward compatibility
        'facebook_posts_top10': top10_posts_data,
        'tiktok_posts_top10': top10_tiktok_posts_data,
        "pillar_summary": pillar_summary,
        'posts_by_pillar': posts_by_pillar,
        'sidebar': sidebar,
        # include JSON for pillar summary and top posts for export functions
        'pillar_summary_json': json.dumps(list(pillar_summary.values('content_pillar', 'post_count')) if pillar_summary else []),
        'top_posts_json': json.dumps(top10_posts_data),
    })

@login_required
def index(request):
    # 🔐 ตรวจสอบว่า user ต้องเปลี่ยนรหัสผ่านก่อน
    if request.user.is_first_login:
        return redirect(reverse('accounts:password_change'))

    full_name = request.user.get_full_name()

    # ✅ ดำเนินการตามปกติ
    page_groups = PageGroup.objects.prefetch_related('pages')
    total_groups = page_groups.count()

    comment_dashboards = FBCommentDashboard.objects.all()
    comment_dashboards_by_group = defaultdict(list)
    for dashboard in comment_dashboards:
        if dashboard.campaign_group:
            comment_dashboards_by_group[dashboard.campaign_group].append(dashboard)

    form_group = PageGroupForm(request.POST or None)
    if form_group.is_valid():
        form_group.save()
        return redirect('index')

    comment_campaign_groups = CommentCampaignGroup.objects.order_by('-created_at')

    return render(request, 'PageInfo/index.html', {
        'page_groups': page_groups,
        'total_groups': total_groups,
        'comment_dashboards_by_group': comment_dashboards_by_group,
        'comment_campaign_groups': comment_campaign_groups,
        'form_group': form_group,
        'full_name': full_name,
    })

def sidebar_context(request):
    page_groups = PageGroup.objects.all()
    # ดึงข้อมูลแคมเปญพร้อมกับกลุ่ม
    post_campaigns_sidebar = FBCommentDashboard.objects.select_related('campaign_group').order_by('-created_at')[:10]

    # ดึง comment_campaign_groups เพื่อนำไปแสดงใน sidebar
    comment_campaign_groups = CommentCampaignGroup.objects.all()

    return {
        'page_groups_sidebar': page_groups,
        'page_groups_count': page_groups.count(),
        'post_campaigns_sidebar': post_campaigns_sidebar,  # ใช้ข้อมูลที่ดึงมาในเมนูบาร์
        'post_campaigns_count': post_campaigns_sidebar.count(),  # จำนวนแคมเปญทั้งหมด
        'comment_campaign_groups': comment_campaign_groups  # ส่งกลุ่มแคมเปญไปยังเมนูข้าง
    }



def pageview(request, page_id):
    page = get_object_or_404(PageInfo, id=page_id)

    facebook_posts = None
    facebook_posts_top10 = None
    facebook_posts_flop10 = None
    scatter_data = []  # ✅ เตรียม scatter_data นอก loop ใหญ่
    posts_by_day_data = []  # ✅ เตรียม posts_by_day_data

    # หากเป็นเพจ TikTok ให้เตรียมข้อมูลและ return ทันที
    if page.platform == "tiktok":
        # 📲 ดึงโพสต์ TikTok ทั้งหมดของเพจนี้
        tiktok_posts_qs = TikTokPost.objects.filter(page=page).order_by('-post_timestamp_dt')
        # แปลง queryset เป็น list ของ dict เพื่อใช้ใน template
        tiktok_posts_data = []
        for p in tiktok_posts_qs:
            # เตรียมข้อมูล timestamp และ interaction สำหรับตารางและกราฟ
            timestamp_text = p.post_timestamp_dt.strftime('%Y-%m-%d %H:%M') if p.post_timestamp_dt else (p.post_timestamp or '')
            total_engagement = (p.like_count or 0) + (p.comment_count or 0) + (p.share_count or 0) + (p.save_count or 0)
            # อัตราปฏิสัมพันธ์: ใช้ engagement ต่อจำนวน view หากมี view
            if p.view_count and p.view_count > 0:
                interaction_rate = f"{(total_engagement / p.view_count):.2%}"
            else:
                interaction_rate = '-'
            tiktok_posts_data.append({
                'post_url': p.post_url,
                'post_content': p.post_content or '',
                'post_imgs': [p.post_imgs] if p.post_imgs else [],
                'post_timestamp': timestamp_text,
                'post_timestamp_dt': p.post_timestamp_dt,
                'view_count': p.view_count or 0,
                'like_count': p.like_count or 0,
                'comment_count': p.comment_count or 0,
                'share_count': p.share_count or 0,
                'save_count': p.save_count or 0,
                'page_name': p.page.page_name if p.page else '',
                'profile_pic': p.page.profile_pic if p.page else '',
                'total_engagement': total_engagement,
                'interaction_rate': interaction_rate,
            })

        # จัดลำดับโพสต์สำหรับ Top 10 และ Flop 10 ตาม view_count
        tiktok_posts_top10 = sorted(tiktok_posts_data, key=lambda x: x['view_count'], reverse=True)[:10]
        tiktok_posts_flop10 = sorted(tiktok_posts_data, key=lambda x: x['view_count'])[:10]

        # สร้าง scatter chart (วันที่ vs. engagement)
        tiktok_scatter = []
        # เก็บวันที่ทั้งหมดเพื่อหาช่วงวันที่
        scatter_dates = []
        for item in tiktok_posts_data:
            if item.get('post_timestamp_dt'):
                # ใช้ datetime จริงสำหรับแกน X
                scatter_dates.append(item['post_timestamp_dt'].date())
                tiktok_scatter.append({
                    'x': item['post_timestamp_dt'].strftime('%Y-%m-%d %H:%M'),
                    'y': item['total_engagement'],
                    'content': (item['post_content'][:30] + '...') if item.get('post_content') else '',
                    'page_name': item.get('page_name', page.page_name),
                    'timestamp_text': item['post_timestamp'],
                    'img': item['post_imgs'][0] if item['post_imgs'] else None,
                    'link': item['post_url'],
                })
            else:
                # ถ้าไม่มี datetime ให้ข้ามใน scatter chart
                continue

        # หาวันแรกและวันสุดท้ายสำหรับหัวกราฟ
        start_date = ''
        end_date = ''
        if scatter_dates:
            scatter_dates_sorted = sorted(scatter_dates)
            start_date = scatter_dates_sorted[0].strftime('%d %b')
            end_date = scatter_dates_sorted[-1].strftime('%d %b')

        # นับจำนวนโพสต์ตามวันในสัปดาห์
        weekday_counter = Counter()
        posts_by_day_json = defaultdict(list)
        posts_grouped_by_time = defaultdict(list)
        # เตรียม heatmap สำหรับ best time chart
        heatmap_counter = {}
        hour_bins = list(range(0, 24, 2))  # กลุ่มชั่วโมงทุก 2 ชั่วโมง
        for p in tiktok_posts_qs:
            dt = p.post_timestamp_dt
            if not dt:
                continue
            weekday_index = dt.weekday()
            weekday_name = dt.strftime('%A')
            weekday_counter[weekday_name] += 1
            hour = dt.hour
            hour_slot = (hour // 2) * 2
            key = f"{weekday_index}_{hour_slot}"

            # ตัวแปรปฏิสัมพันธ์
            likes = p.like_count or 0
            comments = p.comment_count or 0
            shares = p.share_count or 0
            saves = p.save_count or 0
            views = p.view_count or 0
            total_engagement = likes + comments + shares

            # posts_by_day_json สำหรับ popup วัน
            posts_by_day_json[str(weekday_index)].append({
                "platform": "tiktok",
                "post_url": p.post_url,
                "post_imgs": [p.post_imgs] if p.post_imgs else [],
                "post_content": p.post_content or '',
                "post_timestamp": dt.strftime('%Y-%m-%d %H:%M'),
                # Always include page details for popup rendering
                "profile_pic": p.page.profile_pic if p.page else '',
                "page_name": p.page.page_name if p.page else '',
                "like_count": likes,
                "comment_count": comments,
                "share_count": shares,
                "save_count": saves,
                "view_count": views,
                "total_engagement": likes + comments + shares + saves,
            })

            # posts_grouped_by_time สำหรับ popup Best Times chart
            posts_grouped_by_time[key].append({
                "platform": "tiktok",
                "post_url": p.post_url,
                "post_imgs": [p.post_imgs] if p.post_imgs else [],
                "post_content": p.post_content or '',
                "post_timestamp": dt.strftime('%Y-%m-%d %H:%M'),
                # Always include page details for popup rendering
                "profile_pic": p.page.profile_pic if p.page else '',
                "page_name": p.page.page_name if p.page else '',
                "like_count": likes,
                "comment_count": comments,
                "share_count": shares,
                "save_count": saves,
                "view_count": views,
                "total_engagement": likes + comments + shares + saves,
            })

            # รวมข้อมูล heatmap สำหรับ bubble chart
            heat_key = (weekday_name, hour_slot)
            if heat_key not in heatmap_counter:
                heatmap_counter[heat_key] = {
                    "count": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "saves": 0,
                    "engagement": 0,
                }
            heatmap_counter[heat_key]["count"] += 1
            heatmap_counter[heat_key]["likes"] += likes
            heatmap_counter[heat_key]["comments"] += comments
            heatmap_counter[heat_key]["shares"] += shares
            heatmap_counter[heat_key]["saves"] += saves
            heatmap_counter[heat_key]["engagement"] += likes + comments + shares + saves

        # สร้าง bar chart ข้อมูลวัน
        posts_by_day_data = [{"day": day, "count": weekday_counter.get(day, 0)} for day in calendar.day_name]
        bar_day_labels = list(calendar.day_name)
        bar_day_values = [weekday_counter.get(day, 0) for day in bar_day_labels]

        # กำหนดสีของแถบในกราฟตามโทนสีหลัก (primary color) และปรับความสว่างให้แตกต่างกันเล็กน้อยแต่ยังอยู่ในสไตล์เดียวกัน
        base_color = '#2563eb'

        def lighten_color(hex_color: str, factor: float) -> str:
            """Lighten the given hex color by the given factor (0.0-1.0)."""
            hex_color = hex_color.lstrip('#')
            r, g, b = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
            r = int(r + (255 - r) * factor)
            g = int(g + (255 - g) * factor)
            b = int(b + (255 - b) * factor)
            return f'#{r:02x}{g:02x}{b:02x}'

        # สร้างรายการ factor สำหรับแต่ละวันในสัปดาห์ เพื่อให้แต่ละแถบมีเฉดสีนวลตามลำดับ
        lighten_factors = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]
        bar_day_colors = [lighten_color(base_color, lighten_factors[i % len(lighten_factors)]) for i, _ in enumerate(bar_day_labels)]

        # สร้างข้อมูล bubble chart (Best Times To Post)
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        best_times_bubble = []

        for (day_name, hour_slot), val in heatmap_counter.items():
            key_str = f"{day_order.index(day_name)}_{hour_slot}"
            tooltip_label = f"{day_name} {hour_slot:02d}:00 - {hour_slot + 2:02d}:00"
            bubble = {
                "x": day_order.index(day_name),
                "y": hour_slot,
                "r": max(4, min(20, val["count"] * 3)),
                "count": val["count"],
                "likes": val["likes"],
                "comments": val["comments"],
                "shares": val["shares"],
                "saves": val["saves"],
                "label": tooltip_label,
                "tooltip_label": tooltip_label,
                "key": key_str,
                "color": get_bar_color_by_count(val["count"]),
                "customTooltip": {
                    "line1": tooltip_label,
                    "line2": f"{val['count']} Number of posts",
                    "line3": f"{val['likes']} Likes, {val['comments']} Comments, {val['shares']} Shares, {val['saves']} Saves"
                }
            }
            best_times_bubble.append(bubble)

        # ดึงข้อมูลผู้ติดตามจาก FollowerHistory หากมี
        follower_qs = FollowerHistory.objects.filter(page=page).order_by('date')
        follower_data = [
            {"date": f.date.strftime("%b %d"), "followers": f.page_followers_count}
            for f in follower_qs if f.page_followers_count
        ]

        # คำนวณ Top 50 Hashtags สำหรับ TikTok
        top_hashtags_raw = extract_top_hashtags(tiktok_posts_qs)  # ดึง (tag, count)
        top_count_max = top_hashtags_raw[0][1] if top_hashtags_raw else 1
        top_hashtags = []
        for tag, count in top_hashtags_raw:
            font_size = round(0.8 + (count / top_count_max) * 1.5, 2)
            color_hue = round(120 - (count / top_count_max) * 60, 2)
            top_hashtags.append({
                "tag": tag,
                "count": count,
                "font_size": font_size,
                "color_hue": color_hue,
            })

        # Build top posts export data for TikTok
        top_posts_export = []
        for p in tiktok_posts_top10:
            top_posts_export.append({
                'platform': 'tiktok',
                'post_url': p['post_url'],
                'post_content': p['post_content'],
                'post_timestamp': p['post_timestamp'],
                'like_count': p['like_count'],
                'comment_count': p['comment_count'],
                'share_count': p['share_count'],
                'save_count': p['save_count'],
                'view_count': p['view_count'],
                'engagement_rate': p['interaction_rate'],
                'page_name': p['page_name'],
            })

        # เตรียมข้อมูล JSON สำหรับการส่งออก/แสดงผลเพิ่มเติม
        follower_data_json = json.dumps(follower_data, ensure_ascii=False)
        # Export top_hashtags as tag-count pairs only
        top_hashtags_export = [{'tag': h['tag'], 'count': h['count']} for h in top_hashtags]
        top_hashtags_json = json.dumps(top_hashtags_export, ensure_ascii=False)

        return render(request, 'PageInfo/pageview.html', {
            'page': page,
            'tiktok_posts': tiktok_posts_data,
            'tiktok_posts_top10': tiktok_posts_top10,
            'tiktok_posts_flop': tiktok_posts_flop10,
            'scatter_data': json.dumps(tiktok_scatter, ensure_ascii=False),
            'scatter_data_json': json.dumps(tiktok_scatter, ensure_ascii=False),
            'top_posts_json': json.dumps(top_posts_export, ensure_ascii=False),
            'start_date': start_date,
            'end_date': end_date,
            'follower_data': follower_data,
            'follower_data_json': follower_data_json,
            'posts_by_day_data': posts_by_day_data,
            'bar_day_labels': json.dumps(bar_day_labels, ensure_ascii=False),
            'bar_day_values': json.dumps(bar_day_values),
            'bar_day_colors': json.dumps(bar_day_colors),
            'bubble_data': json.dumps(best_times_bubble),
            'posts_by_day_json': json.dumps(posts_by_day_json),
            'posts_grouped_json': json.dumps(posts_grouped_by_time),
            'top_hashtags': top_hashtags,
            'top_hashtags_json': top_hashtags_json,
        })

    if page.platform == "facebook":
        facebook_posts = FacebookPost.objects.filter(page=page).order_by('-post_timestamp_dt')
        posts_by_day_json = defaultdict(list)
        posts_grouped_by_time = defaultdict(list)
        heatmap_counter = {}  # ✅ สำหรับรวมข้อมูล bubble chart
        best_times_bubble = []  # ✅ สำหรับแสดงผล chart
        hour_bins = list(range(0, 24, 2))  # 0,2,4,...22

        for post in facebook_posts:
            if not post.post_timestamp_dt:
                continue

            weekday_index = post.post_timestamp_dt.weekday()
            hour = post.post_timestamp_dt.hour
            hour_slot = (hour // 2) * 2  # เช่น 13 => 12
            key = f"{weekday_index}_{hour_slot}"

            # ✅ แปลง reactions
            reactions = post.reactions or {}
            if isinstance(reactions, str):
                try:
                    reactions = json.loads(reactions)
                except json.JSONDecodeError:
                    reactions = {}

            # ✅ คำนวณ metrics
            post.like_count = reactions.get("ถูกใจ", 0)
            post.comment_count = post.comment_count or 0
            post.share_count = post.share_count or 0
            post.total_engagement = sum(reactions.values()) + post.comment_count + post.share_count

            post.reach = getattr(post, 'reach_per_post', None)
            post.impressions = getattr(post, 'impressions', None)

            if post.reach and isinstance(post.reach, (int, float)) and post.reach > 0:
                post.interaction_rate = f"{post.total_engagement / post.reach:.4%}"
            else:
                post.interaction_rate = "0%"
                post.reach = "-"

            if post.impressions and isinstance(post.impressions, (int, float)) and post.impressions > 0:
                post.impression_per_view = f"{post.total_engagement / post.impressions:.4f}"
            else:
                post.impression_per_view = "-"

            post.negative_sentiment_share = "0%"

            # ✅ เพิ่มข้อมูลเข้า posts_by_day_json
            posts_by_day_json[str(weekday_index)].append({
                "post_id": post.post_id,
                "post_imgs": post.post_imgs,
                "post_content": post.post_content,
                "post_timestamp": post.post_timestamp_text,
                # Always include page details for popup rendering
                "profile_pic": post.page.profile_pic if post.page else '',
                "page_name": post.page.page_name if post.page else '',
                "platform": "facebook",
                "comment_count": post.comment_count,
                "share_count": post.share_count,
                "total_engagement": post.total_engagement,
                "reactions": reactions,
            })

            # ✅ เพิ่มข้อมูลเข้า posts_grouped_by_time สำหรับ popup bubble chart
            posts_grouped_by_time[key].append({
                "post_id": post.post_id,
                "post_content": post.post_content,
                "post_imgs": post.post_imgs,
                "post_timestamp": post.post_timestamp_text,
                "reactions": reactions,
                "comment_count": post.comment_count,
                "share_count": post.share_count,
                "total_engagement": post.total_engagement,
                # Ensure platform and page details at the top level for popup rendering
                "platform": "facebook",
                "page_name": post.page.page_name if post.page else '',
                "profile_pic": post.page.profile_pic if post.page else '',
            })

            # ✅ เพิ่มข้อมูลเข้า scatter chart
            scatter_data.append({
                "x": post.post_timestamp_dt.strftime("%Y-%m-%d"),
                "y": post.total_engagement,
                "content": (post.post_content[:30] + '...') if post.post_content else "",
                "page_name": page.page_name,
                "timestamp_text": post.post_timestamp_text,
                "img": post.post_imgs[0] if isinstance(post.post_imgs, list) and len(post.post_imgs) > 0 else None,
                # ตรวจสอบว่า post_imgs เป็น list
            })

            # ✅ รวมข้อมูล bubble chart
            if key not in heatmap_counter:
                heatmap_counter[key] = {
                    "count": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                }

            heatmap_counter[key]["count"] += 1
            heatmap_counter[key]["likes"] += reactions.get("ถูกใจ", 0)
            heatmap_counter[key]["comments"] += post.comment_count
            heatmap_counter[key]["shares"] += post.share_count

        # ✅ ฟังก์ชันกำหนดสีแยกตามจำนวนโพสต์
        def get_color_by_count(count):
            color_map = {
                1: "#cdb4db",
                2: "#c5f6f7",
                3: "#f9c6c9",
                4: "#ffd6a5",
                5: "#FF6962",
            }
            return color_map.get(count, "#9E9E9E")

        # ✅ แปลง heatmap_counter => best_times_bubble
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for key, val in heatmap_counter.items():
            weekday, hour = map(int, key.split("_"))
            label = f"{day_order[weekday]} {hour:02d}:00 - {hour + 2:02d}:00"
            best_times_bubble.append({
                "x": weekday,
                "y": hour,
                "r": max(4, min(20, val["count"] * 3)),
                "count": val["count"],
                "likes": val["likes"],
                "comments": val["comments"],
                "shares": val["shares"],
                "label": label,
                "key": key,
                "color": get_color_by_count(val["count"]),
            })

        facebook_posts_top10 = sorted(facebook_posts, key=lambda p: p.total_engagement, reverse=True)[:10]
        facebook_posts_flop10 = sorted(facebook_posts, key=lambda p: p.total_engagement)[:10]
        # ===== หลังจากสร้าง facebook_posts สำเร็จแล้ว
        top_hashtags_raw = extract_top_hashtags(facebook_posts)  # ดึง (tag, count)
        top_count_max = top_hashtags_raw[0][1] if top_hashtags_raw else 1

        # เตรียมข้อมูลสำหรับ render
        top_hashtags = []
        for tag, count in top_hashtags_raw:
            font_size = round(0.8 + (count / top_count_max) * 1.5, 2)
            color_hue = round(120 - (count / top_count_max) * 60, 2)
            top_hashtags.append({
                "tag": tag,
                "count": count,
                "font_size": font_size,
                "color_hue": color_hue,
            })

        # ✅ สร้างข้อมูล follower line chart จากตาราง FollowerHistory
        follower_qs = FollowerHistory.objects.filter(page=page).order_by('date')
        follower_data = [
            {"date": f.date.strftime("%b %d"), "followers": f.page_followers_count}
            for f in follower_qs if f.page_followers_count
        ]

        # ✅ เตรียม Counter สำหรับนับจำนวนโพสต์ตามวันในสัปดาห์
        weekday_counter = Counter()
        for post in facebook_posts:
            if post.post_timestamp_dt:
                weekday_name = post.post_timestamp_dt.strftime('%A')
                weekday_counter[weekday_name] += 1

        # ✅ เตรียมข้อมูล posts by day chart
        posts_by_day_data = [{"day": day, "count": weekday_counter.get(day, 0)} for day in calendar.day_name]
        bar_day_labels = list(calendar.day_name)  # ["Monday", "Tuesday", ..., "Sunday"]
        bar_day_values = [weekday_counter.get(day, 0) for day in bar_day_labels]

        def get_bar_color_by_count(count):
            color_map = {
                1: "#a2d2ff",  # ฟ้าพาสเทล
                2: "#cdb4db",  # ม่วงพาสเทล
                3: "#ffd6a5",  # เหลืองพาสเทล
                4: "#ffdac1",  # ส้มพาสเทล
                5: "#f9c6c9",  # ชมพูพาสเทล
                6: "#b5ead7",  # เขียวพาสเทล
            }
            return color_map.get(count, "#e2e2e2")  # fallback สีเทา

        # ปรับโทนสี bar chart สำหรับเพจ Facebook ให้สะท้อนโทนสีหลัก โดยการไล่ระดับความสว่างของสีหลัก
        base_color_fb = '#2563eb'
        def lighten_color_fb(hex_color: str, factor: float) -> str:
            hex_color = hex_color.lstrip('#')
            r, g, b = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
            r = int(r + (255 - r) * factor)
            g = int(g + (255 - g) * factor)
            b = int(b + (255 - b) * factor)
            return f'#{r:02x}{g:02x}{b:02x}'
        lighten_factors_fb = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]
        bar_day_colors = [lighten_color_fb(base_color_fb, lighten_factors_fb[i % len(lighten_factors_fb)]) for i, _ in enumerate(bar_day_labels)]

        # ✅ เตรียมข้อมูลสำหรับ Bubble Chart Best Times to Post
        best_times_data = []
        hour_bins = list(range(0, 24, 2))  # bin ทุก 2 ชั่วโมง: 0,2,4,...22
        heatmap_counter = {}

        for post in facebook_posts:
            if post.post_timestamp_dt:
                weekday = post.post_timestamp_dt.strftime('%A')  # Monday - Sunday
                hour = post.post_timestamp_dt.hour
                time_bin = hour_bins[hour // 2]  # ex: 9 => 8
                key = (weekday, time_bin)

                # ดึง reaction แบบแยกประเภท
                reactions = post.reactions or {}
                if isinstance(reactions, str):
                    try:
                        reactions = json.loads(reactions)
                    except json.JSONDecodeError:
                        reactions = {}

                likes = reactions.get("ถูกใจ", 0)
                comments = post.comment_count or 0
                shares = post.share_count or 0

                if key not in heatmap_counter:
                    heatmap_counter[key] = {
                        "count": 0,
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                        "engagement": 0,
                    }

                heatmap_counter[key]["count"] += 1
                heatmap_counter[key]["likes"] += likes
                heatmap_counter[key]["comments"] += comments
                heatmap_counter[key]["shares"] += shares
                heatmap_counter[key]["engagement"] += likes + comments + shares

        # ✅ แปลงข้อมูลให้พร้อมใช้ใน Chart.js
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        best_times_bubble = []


        # ฟังก์ชันเลือกสีตามจำนวนโพสต์
        def get_color_by_count(count):
            color_map = {
                1: "#cdb4db",
                2: "#c5f6f7",
                3: "#f9c6c9",
                4: "#ffd6a5",
                5: "#FF6962",
            }
            return color_map.get(count, "#9E9E9E")  # สีเทาสำหรับ fallback

        for (day, hour), val in heatmap_counter.items():
            key_str = f"{day_order.index(day)}_{hour}"  # ✅ ให้ตรงกับ key ที่ใช้ใน posts_grouped_by_time

            tooltip_label = f"{day} {hour:02d}:00 - {hour + 2:02d}:00"
            bubble = {
                "x": day_order.index(day),
                "y": hour,
                "r": max(4, min(20, val["count"] * 3)),
                "count": val["count"],
                "likes": val.get("likes", 0),
                "comments": val.get("comments", 0),
                "shares": val.get("shares", 0),
                "label": tooltip_label,  # ✅ เดิม
                "tooltip_label": tooltip_label,  # ✅ เพิ่มสำหรับ group_detail style
                "key": key_str,
                "color": get_color_by_count(val["count"]),
                "customTooltip": {
                    "line1": tooltip_label,
                    "line2": f"{val['count']} Number of posts",
                    "line3": f"{val.get('likes', 0)} Likes, {val.get('comments', 0)} Comments, {val.get('shares', 0)} Shares"
                }
            }

            best_times_bubble.append(bubble)

    # Build top posts export data for Facebook
    top_posts_export = []
    for p in facebook_posts_top10:
        # Ensure reactions is a dict
        reactions = p.reactions or {}
        if isinstance(reactions, str):
            try:
                reactions = json.loads(reactions)
            except json.JSONDecodeError:
                reactions = {}
        like_count = reactions.get("ถูกใจ", 0)
        comment_count = p.comment_count or 0
        share_count = p.share_count or 0
        # Facebook posts do not have save_count or view_count in this model
        engagement_rate = getattr(p, 'interaction_rate', '0%') or '0%'
        top_posts_export.append({
            'platform': 'facebook',
            'post_id': p.post_id,
            'post_content': p.post_content,
            'post_timestamp': p.post_timestamp_text,
            'like_count': like_count,
            'comment_count': comment_count,
            'share_count': share_count,
            'save_count': 0,
            'view_count': 0,
            'engagement_rate': engagement_rate,
            'page_name': p.page.page_name if p.page else '',
        })
    # Prepare scatter data JSON for CSV export
    scatter_data_json = json.dumps(scatter_data, ensure_ascii=False)

    # เตรียมข้อมูล JSON สำหรับส่งออก
    follower_data_json_fb = json.dumps(follower_data, ensure_ascii=False)
    top_hashtags_export_fb = [{'tag': h['tag'], 'count': h['count']} for h in top_hashtags]
    top_hashtags_json_fb = json.dumps(top_hashtags_export_fb, ensure_ascii=False)

    return render(request, 'PageInfo/pageview.html', {
        'page': page,
        'facebook_posts': facebook_posts,
        'facebook_posts_top10': facebook_posts_top10,
        'facebook_posts_flop': facebook_posts_flop10,
        'scatter_data': scatter_data,
        'scatter_data_json': scatter_data_json,
        'top_posts_json': json.dumps(top_posts_export, ensure_ascii=False),
        'follower_data': follower_data,  # ✅ ส่งไปยังเทมเพลตด้วย
        'follower_data_json': follower_data_json_fb,
        'posts_by_day_data': posts_by_day_data,  # ✅ เพิ่มเพื่อส่งให้ Bar Chart
        # ✅ เพิ่ม 2 ตัวนี้เพื่อใช้กับ Chart.js
        'bar_day_labels': json.dumps(bar_day_labels),
        'bar_day_values': json.dumps(bar_day_values),
        'bubble_data': json.dumps(best_times_bubble),
        'bar_day_colors': json.dumps(bar_day_colors),
        'top_hashtags': top_hashtags,
        'top_hashtags_json': top_hashtags_json_fb,
        'posts_by_day_json': json.dumps(posts_by_day_json),
        'posts_grouped_json': json.dumps(posts_grouped_by_time),
    })


