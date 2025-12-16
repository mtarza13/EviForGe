from typing import Any, Dict
import json
import email
from email import policy
from pathlib import Path

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence

class EmailModule(ForensicModule):
    @property
    def name(self) -> str:
        return "email"

    @property
    def description(self) -> str:
        return "Parse EML/MBOX files"

    def run(self, case_id: str, evidence_id: str, **kwargs) -> Dict[str, Any]:
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)
        
        with SessionLocal() as session:
            ev = session.get(Evidence, evidence_id)
            if not ev:
                raise ValueError(f"Evidence {evidence_id} not found")
            file_path = settings.vault_dir / ev.path
            
        if not file_path.exists():
             raise FileNotFoundError(f"Evidence file not found at {file_path}")

        # Check extension for EML
        if file_path.suffix.lower() not in ['.eml', '.msg']: # MSG requires msgconvert/ole, skipping for now
             if not file_path.name.endswith(".eml"):
                 # Maybe mbox? Too complex for single file ingest logic usually.
                 return {"status": "skipped", "reason": "Not an EML file"}

        parsed_data = {}
        try:
            with open(file_path, "rb") as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
                
            parsed_data = {
                "subject": msg.get("subject"),
                "from": msg.get("from"),
                "to": msg.get("to"),
                "date": msg.get("date"),
                "body_text": "",
                "attachments": []
            }
            
            # Extract body
            body = msg.get_body(preferencelist=('plain', 'html'))
            if body:
                try:
                    parsed_data["body_text"] = body.get_content()[:2000] # Cap size
                except:
                    parsed_data["body_text"] = "(decoding error)"
            
            # Attachments
            for part in msg.iter_attachments():
                parsed_data["attachments"].append(part.get_filename())

        except Exception as e:
             raise RuntimeError(f"Email parsing failed: {e}")

        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "email"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=2)

        return {
            "status": "success",
            "subject": parsed_data.get("subject"),
            "output_file": str(output_file)
        }
