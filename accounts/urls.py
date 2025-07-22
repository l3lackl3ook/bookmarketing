# accounts/urls.py
from django.urls import path
from accounts.views import (
    GrowfoxLoginView,
    password_change,  # แก้ไขจาก force_password_change เป็น password_change
)
from django.contrib.auth.views import LogoutView

app_name = 'accounts'

urlpatterns = [
    path("login/", GrowfoxLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("change-password/", password_change, name="password_change"),  # เปลี่ยนจาก force_password_change
]
