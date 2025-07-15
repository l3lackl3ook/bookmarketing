import sys
import os
import django
from dotenv import load_dotenv
from pathlib import Path

# ✅ เพิ่ม sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# ✅ Setup Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FB_WebApp_Project.settings")
django.setup()

# ✅ Load env
load_dotenv()

from PageInfo.models import FacebookComment
from PageInfo.ai_sentiment_analyzer import analyze_sentiment_and_category

# 🔧 ตั้งชื่อ dashboard ที่ต้องการ
target_dashboard_name = "Hygiene รีวิวโลตัส by Kea Kannika"

if target_dashboard_name:
    comments = FacebookComment.objects.filter(
        dashboard__dashboard_name=target_dashboard_name,
        sentiment__isnull=True
    )
else:
    comments = FacebookComment.objects.filter(sentiment__isnull=True)

print(f"🔎 พบทั้งหมด {comments.count()} comments ที่ต้องอัปเดตใน dashboard '{target_dashboard_name}'" if target_dashboard_name else f"🔎 พบทั้งหมด {comments.count()} comments ที่ต้องอัปเดต")

for comment in comments:
    print(f"✏️ วิเคราะห์ comment ID {comment.id}")

    result = analyze_sentiment_and_category(comment.content, comment.image_url)

    # ✅ อัปเดตผลลัพธ์
    comment.sentiment = result.get("sentiment", "")
    comment.reason = result.get("reason", "")
    comment.keyword_group = result.get("keyword_group", "")
    comment.category = result.get("category", "")
    comment.save()

    print(f"✅ อัปเดตเรียบร้อย: sentiment={comment.sentiment}, keyword_group={comment.keyword_group}, category={comment.category}")

print("🎉 เสร็จสิ้นการอัปเดตทั้งหมด")
