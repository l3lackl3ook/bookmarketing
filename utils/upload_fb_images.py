# utils/upload_fb_images.py

import os
import sys
import django
from io import BytesIO
import pandas as pd
import psycopg2
import requests
from urllib.parse import urlparse
from ftplib import FTP
from dotenv import load_dotenv

# ✅ แก้ sys.path เพื่อให้ Django รู้จัก project
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ✅ โหลด ENV
load_dotenv()

# ✅ Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FB_WebApp_Project.settings")
django.setup()

# 🔐 ดึงค่าจาก .env
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

FTP_CONFIG = {
    "ftp_host": os.getenv("FTP_HOST"),
    "ftp_user": os.getenv("FTP_USER"),
    "ftp_pass": os.getenv("FTP_PASS"),
    "ftp_root": os.getenv("FTP_ROOT"),
    "ftp_folder": "image",
    "base_url": os.getenv("FTP_BASE_URL")
}

# ✅ Connect PostgreSQL
conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

columns_to_update = ["image_url", "profile_img_url"]

for column in columns_to_update:
    print(f"\n📦 คอลัมน์: {column}")

    df = pd.read_sql(f"""
        SELECT ctid, {column}
        FROM "PageInfo_facebookcomment"
        WHERE {column} IS NOT NULL AND {column} != ''
        AND {column} NOT LIKE '%{FTP_CONFIG["base_url"]}%'
    """, conn)

    if df.empty:
        print(f"⚠️ ไม่มีข้อมูลที่ต้องอัปเดตในคอลัมน์ {column}")
        continue

    # ✅ Connect FTP
    ftp = FTP()
    ftp.connect(FTP_CONFIG["ftp_host"], 21)
    ftp.login(FTP_CONFIG["ftp_user"], FTP_CONFIG["ftp_pass"])

    # ✅ เข้า public_html ก่อนแล้วเข้า image
    ftp.cwd(FTP_CONFIG["ftp_root"])

    # ตรวจสอบว่ามีโฟลเดอร์ image ใน public_html หรือยัง
    folders = []
    ftp.retrlines("NLST", folders.append)
    if FTP_CONFIG["ftp_folder"] not in folders:
        ftp.mkd(FTP_CONFIG["ftp_folder"])

    ftp.cwd(FTP_CONFIG["ftp_folder"])

    # ✅ Upload loop
    for _, row in df.iterrows():
        image_url = row[column]
        ctid = row["ctid"]

        try:
            filename = os.path.basename(urlparse(image_url).path)
            new_url = f"{FTP_CONFIG['base_url']}{filename}"

            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            ftp.storbinary(f"STOR {filename}", BytesIO(response.content))

            cursor.execute(f"""
                UPDATE "PageInfo_facebookcomment"
                SET {column} = %s
                WHERE ctid = %s
            """, (new_url, ctid))
            conn.commit()

            print(f"✅ {column} updated → {new_url}")

        except Exception as e:
            print(f"❌ Error ({column}): {e}")

    ftp.quit()

# ✅ Close connections
cursor.close()
conn.close()

print("\n🎉 อัปโหลดรูปภาพและอัปเดตลิงก์ในฐานข้อมูลสำเร็จแล้ว")
