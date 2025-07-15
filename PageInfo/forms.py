from django import forms
from .models import PageGroup, FBCommentDashboard, FacebookComment

# ฟอร์มสำหรับกรอกความคิดเห็นของ Facebook
class FacebookCommentForm(forms.ModelForm):
    class Meta:
        model = FacebookComment
        fields = '__all__'  # หรือกำหนดเฉพาะ field ที่ให้แก้ไข
        widgets = {
            'content': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'sentiment': forms.TextInput(attrs={'class': 'form-control'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'keyword_group': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
        }

# ฟอร์มสำหรับกรอก URL ของ Page
class PageURLForm(forms.Form):
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('tiktok', 'TikTok'),
        ('instagram', 'Instagram'),
        ('lemon8', 'Lemon8'),
        ('youtube', 'Youtube'),
    ]
    platform = forms.ChoiceField(
        choices=PLATFORM_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control form-control-lg'}),
        required=True,  # บังคับเลือก platform
        label="Platform"
    )
    url = forms.URLField(
        label="Page URL",
        widget=forms.URLInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'Input URL Page'})
    )

# ฟอร์มสำหรับสร้างกลุ่มเพจใหม่
class PageGroupForm(forms.ModelForm):
    class Meta:
        model = PageGroup
        fields = ['group_name']
        widgets = {
            'group_name': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Input Group Name'
            }),
        }

# ฟอร์มสำหรับ Dashboard ของคอมเมนต์
class CommentDashboardForm(forms.ModelForm):
    class Meta:
        model = FBCommentDashboard
        fields = ['dashboard_name', 'post_id']

