import openai

# ✅ ตั้งค่า API Key
openai.api_key = "sk-xxxxxxx"

def classify_pillar_with_gpt(content, timestamp=None, img_urls=None):
    prompt = f"""
โพสต์นี้มีรายละเอียดดังนี้:
📝 เนื้อหา: "{content}"
📅 เวลาโพสต์: {timestamp or "ไม่ระบุ"}
🖼️ จำนวนภาพแนบ: {len(img_urls) if img_urls else 0}

🔽 กรุณาเลือก Content Pillar ที่เหมาะสมที่สุดจากรายการต่อไปนี้:
- Realtime
- Lifestyle
- Knowledge
- Recipe
- Activity
- Product
- Promotion
- PR and Event
- CSR

ตอบกลับเป็นชื่อหมวดหมู่เพียง 1 คำ เช่น: Recipe
ห้ามอธิบายเพิ่มเติม
    """.strip()

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        result = response.choices[0].message.content.strip()
        # ⚠️ ป้องกัน GPT ตอบเกิน ให้ตัดเหลือบรรทัดแรก และ strip ช่องว่าง
        return result.splitlines()[0].strip()
    except Exception as e:
        print("❌ GPT Error:", e)
        return "ไม่สามารถจัดหมวดหมู่ได้"
