from django.db import models

class PageGroup(models.Model):
    group_name = models.CharField(max_length=255, default='Test Campaign')

    def __str__(self):
        return self.group_name


class PageInfo(models.Model):
    page_group = models.ForeignKey(PageGroup, on_delete=models.CASCADE, related_name='pages')
    platform = models.CharField(
        max_length=20,
        choices=[('facebook', 'Facebook'), ('tiktok', 'TikTok'), ('instagram', 'Instagram'),  ('lemon8', 'Lemon8'),  ('youtube', 'Youtube')],
        default='facebook'
    )
    page_name = models.CharField(max_length=255, null=True, blank=True)
    page_url = models.URLField(max_length=500, null=True, blank=True)
    profile_pic = models.URLField(max_length=500, null=True, blank=True)
    page_username = models.CharField(max_length=255, null=True, blank=True)
    page_id = models.CharField(max_length=100, null=True, blank=True)
    is_business_page = models.BooleanField(null=True, blank=True)
    page_followers = models.CharField(max_length=100, null=True, blank=True)
    page_likes = models.CharField(max_length=100, null=True, blank=True)
    page_followers_count = models.IntegerField(null=True, blank=True)
    page_likes_count = models.CharField(max_length=100, null=True, blank=True)
    page_talking_count = models.CharField(max_length=100, null=True, blank=True)
    page_were_here_count = models.CharField(max_length=100, null=True, blank=True)
    page_description = models.TextField(null=True, blank=True)
    page_category = models.CharField(max_length=255, null=True, blank=True)
    page_address = models.CharField(max_length=500, null=True, blank=True)
    page_phone = models.CharField(max_length=100, null=True, blank=True)
    page_email = models.EmailField(max_length=254, null=True, blank=True)
    page_website = models.URLField(max_length=500, null=True, blank=True)
    following_count = models.CharField(max_length=100, null=True, blank=True)  # เช่น "9"
    age = models.CharField(max_length=50, null=True, blank=True)  # เช่น "ช่วงอายุ 20 ปี"
    # 🔥 เพิ่ม field สำหรับ Instagram post_count
    post_count = models.IntegerField(null=True, blank=True)
    page_join_date = models.CharField(max_length=100, null=True, blank=True)
    page_videos_count = models.BigIntegerField(null=True, blank=True)
    page_total_views = models.BigIntegerField(null=True, blank=True)

    def __str__(self):
        return self.page_name or "Unnamed Page"

class FacebookPost(models.Model):
    POST_TYPES = (
        ('post', 'Post'),
        ('video', 'Video'),
        ('reel', 'Reel'),
        ('live', 'Live'),
    )

    page = models.ForeignKey('PageInfo', on_delete=models.CASCADE, related_name='facebook_posts')

    post_id = models.CharField(max_length=100, unique=True)
    post_url = models.URLField(max_length=500, null=True, blank=True)
    post_type = models.CharField(max_length=10, choices=POST_TYPES, default='post')

    post_timestamp_dt = models.DateTimeField(null=True)
    post_timestamp_text = models.TextField()

    post_content = models.TextField(blank=True, null=True)
    post_imgs = models.JSONField(blank=True, null=True, default=list)  # รวม video thumbnail ด้วย

    watch_count = models.IntegerField(null=True, blank=True)  # เฉพาะ video
    reactions = models.JSONField(blank=True, null=True, default=dict)

    comment_count = models.IntegerField(default=0)
    share_count = models.IntegerField(default=0)

    content_pillar = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.page.page_name if self.page else 'Unknown'} - {self.post_timestamp_text}"

class FollowerHistory(models.Model):
    page = models.ForeignKey(PageInfo, on_delete=models.CASCADE)
    date = models.DateField()
    page_followers_count = models.IntegerField(null=True, blank=True)  # ✅ ชื่อนี้

    def __str__(self):
        return f"{self.page.page_name} - {self.date} - {self.page_followers_count}"

class FacebookComment(models.Model):
    id = models.AutoField(primary_key=True)
    dashboard = models.ForeignKey('FBCommentDashboard', on_delete=models.CASCADE, null=True, blank=True)
    # 🗑️ ลบ post_id หากไม่จำเป็น
    post_url = models.TextField()
    author = models.CharField(max_length=500, null=True, blank=True)
    profile_img_url = models.TextField(null=True, blank=True)
    content = models.TextField()
    reaction = models.CharField(max_length=500, null=True, blank=True)
    timestamp_text = models.CharField(max_length=500, null=True, blank=True)
    image_url = models.TextField(null=True, blank=True)
    reply = models.TextField(null=True, blank=True)
    like_status = models.CharField(max_length=50, null=True, blank=True, default="ยังไม่ถูกใจ")
    share_status = models.CharField(max_length=50, null=True, blank=True, default="ยังไม่แชร์")
    sentiment = models.CharField(max_length=20, null=True, blank=True)
    reason = models.CharField(max_length=255, null=True, blank=True)
    keyword_group = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"{self.author} - {self.content[:30]}"

class CommentCampaignGroup(models.Model):
    group_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    post = models.OneToOneField('FacebookPost', on_delete=models.CASCADE, related_name='campaign', null=True, blank=True)

    def __str__(self):
        return self.group_name



class FBCommentDashboard(models.Model):
    post_id = models.CharField(max_length=1000, db_index=True, null=True, blank=True)
    dashboard_name = models.CharField(max_length=255, blank=True, null=True)
    dashboard_type = models.CharField(
        max_length=50,
        choices=[("seeding", "Seeding"), ("activity", "Activity")],
        default="seeding"
    )
    screenshot_path = models.ImageField(upload_to='post_screenshots/', null=True, blank=True)
    campaign_group = models.ForeignKey(CommentCampaignGroup, related_name='dashboards', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.dashboard_name or self.post_id

