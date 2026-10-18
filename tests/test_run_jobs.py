from src.app.run_jobs import get_job, put_job


def test_put_and_get_job():
    put_job("job-1", {"job_id": "job-1", "status": "running"})
    assert get_job("job-1")["status"] == "running"
    assert get_job("missing") is None
