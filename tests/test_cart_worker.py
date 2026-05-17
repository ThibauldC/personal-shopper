from pathlib import Path
from unittest.mock import MagicMock, patch

from personal_shopper.cart.worker import run_worker
from personal_shopper.config import Settings


def test_worker_sleeps_when_no_jobs(tmp_path: Path):
    settings = Settings(database_path=tmp_path / "test.db")

    with patch("personal_shopper.cart.worker.init_db") as mock_init_db, patch(
        "personal_shopper.cart.worker.get_pending_cart_job_ids", return_value=[]
    ) as mock_get_pending, patch("personal_shopper.cart.worker.time.sleep", side_effect=SystemExit):
        try:
            run_worker(settings=settings, poll_interval_seconds=1)
        except SystemExit:
            pass

    mock_init_db.assert_called_once_with(settings.database_path)
    mock_get_pending.assert_called_once_with(settings.database_path)


def test_worker_processes_pending_jobs(tmp_path: Path):
    settings = Settings(database_path=tmp_path / "test.db")
    mock_process = MagicMock(side_effect=[True, False])

    with patch("personal_shopper.cart.worker.init_db"), patch(
        "personal_shopper.cart.worker.get_pending_cart_job_ids", side_effect=[[11, 12], []]
    ), patch("personal_shopper.cart.worker.process_cart_job", mock_process), patch(
        "personal_shopper.cart.worker.time.sleep", side_effect=SystemExit
    ):
        try:
            run_worker(settings=settings, poll_interval_seconds=1)
        except SystemExit:
            pass

    assert mock_process.call_count == 2
    assert mock_process.call_args_list[0].args == (settings.database_path, 11, settings)
    assert mock_process.call_args_list[1].args == (settings.database_path, 12, settings)
