from typing import Any, Dict
import json
from pathlib import Path

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Case, Job, JobStatus

class ReportModule(ForensicModule):
    @property
    def name(self) -> str:
        return "reports"

    @property
    def description(self) -> str:
        return "Generate Case Report HTML"

    def run(self, case_id: str, evidence_id: str = None, **kwargs) -> Dict[str, Any]:
        """
        Reports run per case, usually. 'evidence_id' might be ignored or used to trigger report update?
        We'll treat it as Case Report.
        """
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)
        
        with SessionLocal() as session:
            case = session.get(Case, case_id)
            if not case:
                raise ValueError(f"Case {case_id} not found")
            
            jobs = session.query(Job).filter(Job.case_id == case_id).all()
            evidence_count = len(case.evidence_items)
            job_count = len(jobs)
            case_name = case.name
            
        # Build HTML Report (MVP)
        # In real world, use Jinja2 template. Here we build simple string for speed.
        
        html = f"""
        <html>
        <head><title>Case Report: {case_name}</title>
        <style>body{{font-family:sans-serif;}} table{{border-collapse:collapse;width:100%;}} th,td{{border:1px solid #ddd;padding:8px;}} th{{background:#eee;}}</style>
        </head>
        <body>
        <h1>Case Report: {case_name}</h1>
        <p>Case ID: {case_id}</p>
        <p>Evidence Items: {evidence_count}</p>
        <p>Jobs Run: {job_count}</p>
        
        <h2>Jobs Summary</h2>
        <table>
            <tr><th>Tool</th><th>Status</th><th>Created</th><th>Error</th></tr>
        """
        
        for j in jobs:
            html += f"<tr><td>{j.tool_name}</td><td>{j.status}</td><td>{j.created_at}</td><td>{j.error_message or ''}</td></tr>"
            
        html += """
        </table>
        </body></html>
        """
        
        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "reports"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        import time
        ts = int(time.time())
        output_file = artifact_dir / f"report_{ts}.html"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        return {
            "status": "success",
            "report_file": str(output_file)
        }
