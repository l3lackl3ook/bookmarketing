from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from accounts.models import CustomUser
from accounts.forms import GrowfoxLoginForm


class GrowfoxLoginView(LoginView):
    authentication_form = GrowfoxLoginForm

    def form_valid(self, form):
        user = form.get_user()

        if user.failed_login_attempts >= 3:
            messages.error(self.request, "บัญชีนี้ถูกล็อก กรุณาตรวจสอบอีเมลเพื่อรีเซ็ตรหัสผ่าน")
            return redirect("login")

        if user.is_first_login:
            auth_login(self.request, user)
            return redirect("accounts:password_change")  # เปลี่ยนรหัสผ่านครั้งแรก

        # login สำเร็จ: รีเซ็ต failed login
        user.failed_login_attempts = 0
        user.last_failed_login = None
        user.save()

        auth_login(self.request, user)
        return redirect("index")  # ไปหน้า dashboard หรือ index


@login_required
def password_change(request):
    user = request.user

    if not user.is_first_login:
        return redirect("index")  # ไม่ใช่ login แรก ก็ไม่ต้องเปลี่ยน

    if request.method == "POST":
        form = PasswordChangeForm(user=user, data=request.POST)
        if form.is_valid():
            form.save()
            user.is_first_login = False  # เปลี่ยนสถานะการเข้าสู่ระบบครั้งแรก
            user.save()
            messages.success(request, "เปลี่ยนรหัสผ่านเรียบร้อยแล้ว")
            return redirect("index")  # เปลี่ยนเสร็จแล้วไปหน้า index
    else:
        form = PasswordChangeForm(user)

    return render(request, "accounts/password_change.html", {"form": form})


def some_view(request):
    # เปลี่ยนการเรียกใช้ reverse ให้ตรงกับชื่อ path
    return redirect(reverse('accounts:password_change'))
