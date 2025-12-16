from typing import Any, Dict
import json
import hashlib
from pathlib import Path

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence

class VerificationModule(ForensicModule):
    @property
    def name(self) -> str:
        return "verification"

    @property
    def description(self) -> str:
        return "Verify evidence integrity against stored hashes"

    def run(self, case_id: str, evidence_id: str, **kwargs) -> Dict[str, Any]:
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)
        
        with SessionLocal() as session:
            ev = session.get(Evidence, evidence_id)
            if not ev:
                raise ValueError(f"Evidence {evidence_id} not found")
            file_path = settings.vault_dir / ev.path
            stored_sha256 = ev.sha256
            stored_md5 = ev.md5
            
        if not file_path.exists():
             raise FileNotFoundError(f"Evidence file not found at {file_path}")

        # Re-hash
        h_sha256 = hashlib.sha256()
        h_md5 = hashlib.md5()
        
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                h_sha256.update(chunk)
                h_md5.update(chunk)
                
        current_sha256 = h_sha256.hexdigest()
        current_md5 = h_md5.hexdigest()
        
        match = (current_sha256 == stored_sha256)
        
        result = {
            "match": match,
            "stored_sha256": stored_sha256,
            "current_sha256": current_sha256,
            "stored_md5": stored_md5,
            "current_md5": current_md5
        }

        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "verification"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        return {
            "status": "success",
            "integrity_ok": match,
            "output_file": str(output_file)
        }
