from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from typing import Any, Optional
import json
from datetime import datetime, timedelta

from cybersecurity.analysis_settings import CHAT_GPT_OPEN_AI, GEMINI_GOOGLE
from cybersecurity.seek_trends import seek_trends


class Command(BaseCommand):
    help = 'Seeks and analyzes cybersecurity trends from collected data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to look back for trend analysis (default: 7)',
        )
        parser.add_argument(
            '--llm_to_use',
            type=int,
            default=CHAT_GPT_OPEN_AI,
            choices=[CHAT_GPT_OPEN_AI, GEMINI_GOOGLE],
            help='LLM to use when making Trends report',
        )
        parser.add_argument(
            '--category',
            type=str,
            default='all',
            help='Category of trends to analyze (all, malware, vulnerabilities, breaches, etc.)',
        )
        parser.add_argument(
            '--save-to-file',
            type=str,
            help='Save trend analysis to specified file path',
        )

    def handle(self, *args: Any, **kwargs: Any) -> Optional[str]:
        """
        Seeks and analyzes cybersecurity trends from collected data.
        """

        self.stdout.write('🔍 Starting trend analysis...')
        
        try:
            # Get parameters
            days = kwargs['days']
            llm_to_use = kwargs['llm_to_use']
            category = kwargs['category']
            save_file = kwargs.get('save_to_file')

            self.stdout.write(f'📊 Analyzing trends for the last {days} days')
            self.stdout.write(f'🤖 Using LLM: {"ChatGPT" if llm_to_use == CHAT_GPT_OPEN_AI else "Gemini"}')
            self.stdout.write(f'📋 Category: {category}')
            self.stdout.write('=' * 50)

            # Call seek_trends with the llm_to_use parameter
            seek_trends(llm_to_use=llm_to_use, days=days, category=category)
            
            self.stdout.write('\n' + '=' * 50)
            self.stdout.write(
                self.style.SUCCESS('✅ Trend analysis completed successfully!')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error during trend analysis: {str(e)}')
            )
            raise CommandError(f'Trend analysis failed: {str(e)}')