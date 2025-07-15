def get_pillar_summary(page_ids):
    query = """
    SELECT content_pillar, COUNT(*) as post_count
    FROM "PageInfo_facebookpost"
    WHERE page_id = ANY(:page_ids)
    GROUP BY content_pillar
    """
    with engine.connect() as conn:
        result = conn.execute(text(query), {"page_ids": page_ids})
        return [{"pillar": row["content_pillar"], "post_count": row["post_count"]} for row in result]
