from datetime import datetime, timedelta, time
import pytz
from datetime import datetime
from django.utils import timezone

CHAT_GPT_OPEN_AI = 100
PERPLEXITY = 200
CLAUDE_ANTHROPIC = 300
GEMINI_GOOGLE = 400

today = timezone.now().date()
yesterday = today - timedelta(days=1)

START_DATE = timezone.make_aware(datetime.combine(today, time.min))
END_DATE = timezone.make_aware(datetime.combine(today, time.max))

# yesterday
# START_DATE = timezone.make_aware(datetime.combine(yesterday, time.min))
# END_DATE = timezone.make_aware(datetime.combine(yesterday, time.max))

SIMILARITY_THRESHOLD_FOR_FINDING_SIMILAR_ARTICLES = 0.75

LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS = PERPLEXITY

