from django.core.management.base import BaseCommand
from PageInfo.models import PageInfo, FollowerHistory
from datetime import date

class Command(BaseCommand):
    help = 'Update follower count for all pages and store it in FollowerHistory'

    def handle(self, *args, **kwargs):
        for page in PageInfo.objects.all():
            current_count = page.page_followers_count or 0

            if not FollowerHistory.objects.filter(page=page, date=date.today()).exists():
                FollowerHistory.objects.create(
                    page=page,
                    date=date.today(),
                    page_followers_count=current_count
                )
                self.stdout.write(self.style.SUCCESS(
                    f'Saved {current_count} followers for {page.page_name}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Data for {page.page_name} already exists today'
                ))
