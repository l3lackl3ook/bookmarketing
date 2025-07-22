from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import PasswordChangeForm


class GrowfoxLoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, initial=False, label='Remember me')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Email (@growfox.co เท่านั้น)',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password',
        })

    def clean_username(self):
        email = self.cleaned_data.get('username')
        if not email.endswith('@growfox.co'):
            raise ValidationError("อนุญาตเฉพาะอีเมล growfox.co เท่านั้น")
        return email

class ChangePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)