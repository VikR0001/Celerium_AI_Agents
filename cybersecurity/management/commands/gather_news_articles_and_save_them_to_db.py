from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from typing import Any, Optional
import json
from datetime import datetime, timedelta

from cybersecurity.report_latest_cybersecurity_news import startAI_Agent


class Command(BaseCommand):
    help = 'Gathers news articles and saves them to the DB for later reference. No reporting is done yet.'

    def handle(self, *args: Any, **kwargs: Any) -> Optional[str]:
        """
        Gathers news articles and saves them to the DB for later reference.
        """

        self.stdout.write('Staring Agent...')

        startAI_Agent(gather_articles_only=True)

        try:
            # Report generation logic will go here
            self.stdout.write(self.style.SUCCESS('Successfully generated cost analysis reports'))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error generating reports: {str(e)}')
            )
            return None



