# Generated by Django 5.2.1 on 2025-07-22 09:49

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('PageInfo', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagegroup',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
