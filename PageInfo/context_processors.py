# PageInfo/context_processors.py

from .models import PageGroup, FBCommentDashboard  # ✅ ลบ FBPageDashboard ออก

def sidebar_context(request):
    post_campaigns_sidebar = FBCommentDashboard.objects.select_related('campaign_group').order_by('-created_at')[:10]

    return {
        'post_campaigns_sidebar': post_campaigns_sidebar,
    }
