from datetime import datetime, timedelta, time
import pytz
from django.utils import timezone

today = timezone.now().date()

# Create timezone-aware datetime objects
START_DATE = timezone.make_aware(datetime.combine(today, time.min))
END_DATE = timezone.make_aware(datetime.combine(today, time.max))

