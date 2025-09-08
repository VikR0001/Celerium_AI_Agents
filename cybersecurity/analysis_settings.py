from datetime import datetime, timedelta, time
import pytz
from datetime import datetime
from django.utils import timezone

today = timezone.now().date()

# Create timezone-aware datetime objects
START_DATE = timezone.make_aware(datetime.combine(today, time.min))
END_DATE = timezone.make_aware(datetime.combine(today, time.max))

print(type(START_DATE))  # Should be <class 'datetime.datetime'>
print(START_DATE)
print(type(END_DATE))
print(END_DATE)
print('...')

