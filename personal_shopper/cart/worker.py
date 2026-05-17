import logging
import time

from personal_shopper.cart.automation import process_cart_job
from personal_shopper.config import Settings, get_settings
from personal_shopper.database.db import init_db
from personal_shopper.slack.store import get_pending_cart_job_ids

logger = logging.getLogger(__name__)


def run_worker(settings: Settings | None = None, poll_interval_seconds: int = 5) -> None:
    if settings is None:
        settings = get_settings()

    init_db(settings.database_path)
    logger.info("Cart worker started")

    while True:
        job_ids = get_pending_cart_job_ids(settings.database_path)
        if not job_ids:
            time.sleep(poll_interval_seconds)
            continue

        for job_id in job_ids:
            succeeded = process_cart_job(settings.database_path, job_id, settings)
            if succeeded:
                logger.info("Cart job %s succeeded", job_id)
            else:
                logger.warning("Cart job %s failed", job_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_worker()
