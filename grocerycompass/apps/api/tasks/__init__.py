from celery import Celery
from celery.schedules import crontab

from config import settings

celery_app = Celery("grocerycompass", broker=settings.redis_url)

celery_app.conf.update(
    result_backend=settings.redis_url,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Rome",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    'scrape-esselunga': {
        'task': 'tasks.scraping.scrape_chain',
        'schedule': crontab(hour='4', minute='0'),
        'args': ('esselunga',),
    },
    'scrape-iperal': {
        'task': 'tasks.scraping.scrape_chain',
        'schedule': crontab(hour='4', minute='30'),
        'args': ('iperal',),
    },
    'normalize-pending': {
        'task': 'tasks.normalization.run_normalization',
        'schedule': crontab(hour='7', minute='0'),
    },
    'update-meilisearch': {
        'task': 'tasks.search_sync.sync_search_index',
        'schedule': crontab(hour='8', minute='0'),
    },
}
