import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import openai
import pandas as pd
from sqlalchemy import create_engine, text
from utils.pillar_classifier import classify_pillar_with_gpt

# ✅ ตั้งค่า OpenAI API KEY
openai.api_key = "sk-xxxxxxx"

# ✅ เชื่อมต่อฐานข้อมูล PostgreSQL
db_config = {
    "user": "book",
    "password": "Ssru8004",
    "host": "asia-east1-001.proxy.kinsta.app",
    "port": 30577,
    "database": "marketing_api_growfox"
}
db_url = f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
engine = create_engine(db_url)

# ✅ ดึงข้อมูลจากตาราง (ชื่อ table ต้องใส่ double quote เพราะมีตัวพิมพ์ใหญ่)
query = """
SELECT id, post_content, post_timestamp_dt, post_imgs
FROM "PageInfo_facebookpost"
WHERE content_pillar IS NULL AND post_content IS NOT NULL
"""

df = pd.read_sql(query, con=engine)

# ✅ ฟังก์ชันวิเคราะห์ Pillar
def safe_classify(row):
    try:
        return classify_pillar_with_gpt(
            content=row["post_content"],
            timestamp=str(row["post_timestamp_dt"]),
            img_urls=row["post_imgs"] if isinstance(row["post_imgs"], list) else []
        )
    except Exception as e:
        print(f"❌ Error at ID {row['id']}: {e}")
        return "ไม่สามารถจัดหมวดหมู่ได้"

# ✅ วิเคราะห์
df["content_pillar"] = df.apply(safe_classify, axis=1)

# ✅ อัปเดตผลกลับเข้า table (ต้องใส่ double quote ด้วย)
with engine.begin() as conn:
    for _, row in df.iterrows():
        conn.execute(
            text('UPDATE "PageInfo_facebookpost" SET content_pillar = :pillar WHERE id = :id'),
            {"pillar": row["content_pillar"], "id": row["id"]}
        )

print("✅ วิเคราะห์ Content Pillar สำเร็จแล้ว!")
