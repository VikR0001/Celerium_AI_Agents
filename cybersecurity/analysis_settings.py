from datetime import datetime, timedelta, time
import pytz
from datetime import datetime
from django.utils import timezone
import zoneinfo

CHAT_GPT_OPEN_AI = 100
PERPLEXITY = 200
CLAUDE_ANTHROPIC = 300
GEMINI_GOOGLE = 400

today = timezone.now().date()
yesterday = today - timedelta(days=1)
two_days_ago = today - timedelta(days=2)

START_DATE = timezone.make_aware(datetime.combine(today, time.min))
END_DATE = timezone.make_aware(datetime.combine(today, time.max))

# yesterday
# START_DATE = timezone.make_aware(datetime.combine(yesterday, time.min))
# END_DATE = timezone.make_aware(datetime.combine(yesterday, time.max))

#attempt to get articles starting yesterday at 5pm since the email report goes out arund 5pm
#but new code will have to be added to prevent stories from being emailed that were included in the
#previous email.
# eastern = zoneinfo.ZoneInfo('America/New_York')
# START_DATE = timezone.make_aware(
#     datetime.combine(yesterday, time(17, 0)),  # 5pm = 17:00
#     timezone=eastern
# )
# END_DATE = timezone.make_aware(datetime.combine(today, time.max))

# yesterday
# START_DATE = timezone.make_aware(
#     datetime.combine(two_days_ago, time(17, 0)),  # 5pm = 17:00
#     timezone=eastern
# )
# END_DATE = timezone.make_aware(datetime.combine(yesterday, time.max))

SIMILARITY_THRESHOLD_FOR_FINDING_SIMILAR_ARTICLES = 0.75

LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS = PERPLEXITY

