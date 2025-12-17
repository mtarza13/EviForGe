from __future__ import annotations

from pathlib import Path

from eviforge.core.db import create_session_factory, utcnow
from eviforge.core.jobs import update_job_status
from eviforge.core.models import Job, JobStatus


def test_update_job_status_transitions(tmp_path: Path) -> None:
    SessionLocal = create_session_factory(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")

    job_id = "00000000-0000-0000-0000-000000000001"
    with SessionLocal() as session:
        job = Job(
            id=job_id,
            case_id="case-1",
            evidence_id=None,
            tool_name="inventory",
            status=JobStatus.PENDING,
            queued_at=utcnow(),
            created_at=utcnow(),
        )
        session.add(job)
        session.commit()

    with SessionLocal() as session:
        update_job_status(session, job_id, JobStatus.RUNNING)
        j = session.get(Job, job_id)
        assert j is not None
        assert j.status == JobStatus.RUNNING
        assert j.completed_at is None

    with SessionLocal() as session:
        update_job_status(session, job_id, JobStatus.COMPLETED, result={"ok": True})
        j = session.get(Job, job_id)
        assert j is not None
        assert j.status == JobStatus.COMPLETED
        assert j.result_json is not None
        assert j.completed_at is not None

    with SessionLocal() as session:
        update_job_status(session, job_id, JobStatus.FAILED, error="boom")
        j = session.get(Job, job_id)
        assert j is not None
        assert j.status == JobStatus.FAILED
        assert "boom" in (j.error_message or "")
        assert j.completed_at is not None
