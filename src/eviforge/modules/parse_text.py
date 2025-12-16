from __future__ import annotations

import requests
import json
from pathlib import Path
from typing import Any, Dict

from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence
from eviforge.config import load_settings
from eviforge.modules.base import ForensicModule


class ParseTextModule(ForensicModule):
    @property
    def name(self) -> str:
        return "parse_text"

    @property
    def description(self) -> str:
        return "Extract text and metadata using Apache Tika"

    def run(self, case_id: str, evidence_id: str, **kwargs) -> Dict[str, Any]:
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)
        
        # 1. Get Evidence Path
        with SessionLocal() as session:
            ev = session.get(Evidence, evidence_id)
            if not ev:
                raise ValueError(f"Evidence {evidence_id} not found")
            
            # Construct absolute path to evidence file in vault
            # stored path is relative to vault_dir
            file_path = settings.vault_dir / ev.path
            
        if not file_path.exists():
             raise FileNotFoundError(f"Evidence file not found at {file_path}")

        # 2. Send to Tika
        # Tika container is reachable at 'tika' hostname inside docker network
        # or localhost if running with port mapping on host.
        # Ideally use env var for TIKA_URL
        tika_url = "http://tika:9998/tika" # Default internal docker DNS
        
        # We need both text and metadata.
        # Tika /rmeta endpoint gives recursive metadata + content (as XHTML or text)
        tika_rmeta = "http://tika:9998/rmeta/text" 

        try:
            with open(file_path, "rb") as f:
                response = requests.put(
                    tika_rmeta, 
                    data=f, 
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                response.raise_for_status()
                tika_data = response.json()
        except Exception as e:
            return {"error": str(e), "status": "failed"}

        # 3. Save Artifacts
        # artifacts/parse_text/<evidence_id>.json
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "parse_text"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(tika_data, f, indent=2)

        return {
            "status": "success", 
            "output_file": str(output_file),
            "parsed_objects": len(tika_data)
        }
