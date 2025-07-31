from openai import OpenAI
import os
import json
import re
from dotenv import load_dotenv

# ✅ โหลด environment variables
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_sentiment_and_category(content, image_url=None, post_product="Hygiene"):
    """
    วิเคราะห์คอมเมนต์ Facebook สำหรับโพสต์ Hygiene
    """
    prompt = f"""
    คุณคือผู้เชี่ยวชาญ Consumer Insight และนักวิเคราะห์ความเห็นผู้บริโภคในบริบทของ Social Media โดยเฉพาะแบรนด์น้ำยาปรับผ้านุ่ม Hygiene

    🎯 **Context ของโพสต์นี้**
    - Product: {post_product}
    - Image URL (ถ้ามี): {image_url}
    - โพสต์นี้เป็นโพสต์ของแบรนด์ Hygiene ซึ่งอาจมีภาพสินค้า กลิ่น สี หรือคำบรรยายต่าง ๆ ที่เกี่ยวข้องกับผลิตภัณฑ์น้ำยาปรับผ้านุ่ม

    🎯 **วัตถุประสงค์**
    ช่วยวิเคราะห์ความรู้สึก (Sentiment), หมวดหมู่ (Category), และ Keyword ที่เด่นของคอมเมนต์ Facebook ด้านล่างนี้ โดยยึดตามเงื่อนไข:

    ---

    🔹 **Category (หมวดหมู่)** — *เลือก 1 อย่างจากรายการด้านล่างนี้เท่านั้น หากไม่มีข้อมูลให้ตอบ "อื่นๆ"*
    - ใช้ดี
    - กลิ่นหอม
    - ราคา
    - ซื้อที่ไหน
    - ไม่หอม
    - คราบไม่ออก
    - แท็กเพื่อน
    - ตอบกลับ
    - อื่นๆ

    🔹 **Sentiment**
    - Positive → ชมสินค้า, ชอบกลิ่น, ชอบสี, อยากลอง, ซื้อแล้ว, ถ่ายรูปสินค้า, บอกว่าสะอาด/นุ่ม
    - Neutral → คำถาม (ซื้อที่ไหน, ราคา), แท็กเพื่อน, ตอบกลับ, คำเฉยๆ
    - Negative → วิจารณ์ว่าไม่หอม, กลิ่นแรง, ไม่สะอาด, มีคราบ, ผิวแพ้ ฯลฯ

    🔹 **Keyword Group**
    - ให้เลือกเพียงคำเดียวจากเนื้อหา เช่น "หอม", "นุ่ม", "ชมพู", "กลิ่น", "แพ้", "ซักผ้า", หรือชื่อสินค้า เช่น “Hygiene Berry Toast”
    - ห้ามตอบมากกว่า 1 คำ หรือคำทั่วไปเกินไป

    ---

    📌 **กฎพิเศษเพิ่มเติม**
    1. หากคอมเมนต์เป็นการแท็กเพื่อนหรือพูดถึง author เฉย ๆ → category = "แท็กเพื่อน", sentiment = "neutral"
    2. หากขึ้นต้นด้วยชื่อ author ตามด้วยข้อความ → category = "ตอบกลับ", sentiment = "neutral"
    3. หากไม่มีข้อความแต่มีรูป → วิเคราะห์จากรูปเพื่อดูว่าคือสินค้าของ Hygiene หรือมีสีเด่น เช่น ชมพู, ฟ้า, ขาว
    4. ให้ดูที่เจตนา ความรู้สึก และคำที่ใช้เป็นหลัก ไม่ใช่แค่คำเดียว

    ---

    📤 **ผลลัพธ์ที่ต้องการ (ตอบกลับเป็น JSON เท่านั้น):**
    {{
        "sentiment": "Positive",    // หรือ neutral / negative
        "reason": "เหตุผลสั้น ๆ กระชับ เช่น กล่าวถึงกลิ่นหอมโดยตรง",
        "keyword_group": "หอม",     // คำเดียวเท่านั้น
        "category": "กลิ่นหอม"     // หมวดหมู่ตามด้านบน
    }}

    ❌ ห้าม:
    - ใส่ backtick หรือ ```json
    - ใส่หลายค่าในฟิลด์เดียว
    - ตอบเกิน JSON ที่กำหนด

    🎯 **คอมเมนต์**:
    "{content}"

    🎯 **Image URL**:
    "{image_url}"
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert Thai sentiment categorizer and consumer insight analyst."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    try:
        raw = response.choices[0].message.content

        # 🔧 clean backtick หรือ ```json
        clean = re.sub(r"```json|```", "", raw).strip()

        # 🔧 หากยังมีข้อความเกิน JSON, ดึงเฉพาะ {...}
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            raise ValueError("JSON not found in AI response")

        # ✅ แก้ sentiment format ตามโจทย์
        sentiment = result.get("sentiment", "").strip()
        if sentiment.lower() == "positive":
            sentiment = "Positive"
        elif sentiment.lower() == "neutral":
            sentiment = "neutral"
        elif sentiment.lower() == "negative":
            sentiment = "negative"
        else:
            sentiment = ""

        final_result = {
            "sentiment": sentiment,
            "reason": result.get("reason", "").strip(),
            "keyword_group": result.get("keyword_group", "").strip(),
            "category": result.get("category", "").strip(),
        }

        return final_result

    except Exception as e:
        print("❌ Error parsing AI response:", e)
        print("Raw response:", raw)
        return {"sentiment": "", "reason": "", "keyword_group": "", "category": ""}
