from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from typing import Any, Optional
import json
from datetime import datetime, timedelta

from cybersecurity.report_latest_cybersecurity_news import startAI_Agent


class Command(BaseCommand):
    help = 'Runs AI Agents'

    def handle(self, *args: Any, **kwargs: Any) -> Optional[str]:
        """
        Creates cost analysis reports based on the provided parameters.
        """

        self.stdout.write('Staring Agent...')

        startAI_Agent(gather_articles_only=False)

        try:
            # Report generation logic will go here
            self.stdout.write(self.style.SUCCESS('Successfully reports'))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error generating reports: {str(e)}')
            )
            return None






# class Command(BaseCommand):
#     help = 'Reports today\'s cybersecurity news and threats'
#
#     def add_arguments(self, parser):
#         parser.add_argument(
#             '--source',
#             type=str,
#             default='all',
#             help='News source to use (all, hackernews, reddit, etc.)',
#         )
#         parser.add_argument(
#             '--format',
#             type=str,
#             default='summary',
#             choices=['summary', 'detailed', 'json'],
#             help='Output format for the report',
#         )
#         parser.add_argument(
#             '--save-to-file',
#             type=str,
#             help='Save report to specified file path',
#         )
#
#     def handle(self, *args, **options):
#         try:
#             self.stdout.write(
#                 self.style.SUCCESS('🔒 Cybersecurity News Report for %s' % timezone.now().strftime('%Y-%m-%d'))
#             )
#             self.stdout.write('=' * 50)
#
#             # Get today's date for filtering news
#             today = datetime.now().date()
#
#             # Collect news from various sources
#             news_data = self.collect_news(options['source'])
#
#             # Format and display the report
#             if options['format'] == 'json':
#                 report = json.dumps(news_data, indent=2, default=str)
#             elif options['format'] == 'detailed':
#                 report = self.format_detailed_report(news_data)
#             else:
#                 report = self.format_summary_report(news_data)
#
#             # Display the report
#             self.stdout.write(report)
#
#             # Save to file if requested
#             if options['save_to_file']:
#                 with open(options['save_to_file'], 'w') as f:
#                     f.write(report)
#                 self.stdout.write(
#                     self.style.SUCCESS(f'\n📄 Report saved to: {options["save_to_file"]}')
#                 )
#
#             self.stdout.write('\n' + '=' * 50)
#             self.stdout.write(
#                 self.style.SUCCESS('✅ Report generated successfully!')
#             )
#
#         except Exception as e:
#             raise CommandError(f'Error generating cybersecurity report: {str(e)}')
#
#     def collect_news(self, source):
#         """
#         Collect cybersecurity news from various sources
#         Note: This is a template - you'll need to implement actual API calls
#         """
#         news_data = {
#             'generated_at': timezone.now(),
#             'source': source,
#             'articles': []
#         }
#
#         if source == 'all' or source == 'sample':
#             # Sample data - replace with actual API calls
#             sample_articles = [
#                 {
#                     'title': 'Critical Zero-Day Vulnerability Discovered in Popular Web Framework',
#                     'source': 'Security Weekly',
#                     'severity': 'Critical',
#                     'published': timezone.now() - timedelta(hours=2),
#                     'summary': 'A critical zero-day vulnerability has been discovered that affects millions of websites.',
#                     'url': 'https://example.com/news/1',
#                 },
#                 {
#                     'title': 'New Ransomware Campaign Targets Healthcare Organizations',
#                     'source': 'CyberSec Today',
#                     'severity': 'High',
#                     'published': timezone.now() - timedelta(hours=4),
#                     'summary': 'Healthcare organizations are being targeted by a sophisticated new ransomware campaign.',
#                     'url': 'https://example.com/news/2',
#                 },
#                 {
#                     'title': 'Supply Chain Attack Affects Multiple Software Vendors',
#                     'source': 'InfoSec News',
#                     'severity': 'High',
#                     'published': timezone.now() - timedelta(hours=6),
#                     'summary': 'A supply chain attack has compromised software from multiple vendors, affecting thousands of organizations.',
#                     'url': 'https://example.com/news/3',
#                 },
#             ]
#             news_data['articles'] = sample_articles
#
#         # TODO: Implement actual news sources
#         # Examples of what you could add:
#         # - RSS feeds from cybersecurity news sites
#         # - Reddit API for /r/cybersecurity, /r/netsec
#         # - Hacker News API for security-related posts
#         # - CISA alerts API
#         # - CVE database API
#         # - Threat intelligence feeds
#
#         return news_data
#
#     def format_summary_report(self, news_data):
#         """Format the news data as a summary report"""
#         report = f"\n📊 Summary Report ({len(news_data['articles'])} articles found)\n\n"
#
#         for i, article in enumerate(news_data['articles'], 1):
#             severity_emoji = {
#                 'Critical': '🚨',
#                 'High': '⚠️',
#                 'Medium': '📋',
#                 'Low': '📝'
#             }.get(article.get('severity', 'Medium'), '📋')
#
#             report += f"{i}. {severity_emoji} {article['title']}\n"
#             report += f"   Source: {article['source']} | Severity: {article.get('severity', 'Unknown')}\n"
#             report += f"   Published: {article['published'].strftime('%H:%M %Z') if hasattr(article['published'], 'strftime') else article['published']}\n"
#             report += f"   Summary: {article['summary'][:100]}...\n"
#             report += f"   URL: {article.get('url', 'N/A')}\n\n"
#
#         return report
#
#     def format_detailed_report(self, news_data):
#         """Format the news data as a detailed report"""
#         report = f"\n📋 Detailed Cybersecurity Report\n"
#         report += f"Generated: {news_data['generated_at'].strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
#         report += f"Source: {news_data['source']}\n"
#         report += f"Total Articles: {len(news_data['articles'])}\n\n"
#
#         # Group by severity
#         by_severity = {}
#         for article in news_data['articles']:
#             severity = article.get('severity', 'Unknown')
#             if severity not in by_severity:
#                 by_severity[severity] = []
#             by_severity[severity].append(article)
#
#         for severity in ['Critical', 'High', 'Medium', 'Low', 'Unknown']:
#             if severity in by_severity:
#                 report += f"\n🔹 {severity.upper()} SEVERITY ({len(by_severity[severity])} articles)\n"
#                 report += "-" * 40 + "\n"
#
#                 for article in by_severity[severity]:
#                     report += f"\nTitle: {article['title']}\n"
#                     report += f"Source: {article['source']}\n"
#                     report += f"Published: {article['published']}\n"
#                     report += f"Summary: {article['summary']}\n"
#                     report += f"URL: {article.get('url', 'N/A')}\n"
#                     report += "-" * 30 + "\n"
#
#         return report
#
#     def get_threat_level_color(self, severity):
#         """Get the appropriate color style for threat levels"""
#         colors = {
#             'Critical': self.style.ERROR,
#             'High': self.style.WARNING,
#             'Medium': self.style.NOTICE,
#             'Low': self.style.SUCCESS,
#         }
#         return colors.get(severity, self.style.NOTICE)
