from __future__ import annotations

import subprocess
import json
from pathlib import Path
from typing import Any, Dict

from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence
from eviforge.config import load_settings
from eviforge.modules.base import ForensicModule


class ExifModule(ForensicModule):
    @property
    def name(self) -> str:
        return "exif"

    @property
    def description(self) -> str:
        return "Extract metadata using ExifTool"

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

        # Run Exiftool
        try:
            # -j for JSON output, -g for group headings (optional, sticking to flat -j for simplicity or default)
            cmd = ["exiftool", "-j", str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            metadata = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
             return {"error": f"Exiftool failed: {e.stderr}", "status": "failed"}
        except Exception as e:
             return {"error": str(e), "status": "failed"}

        # Save Artifacts
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "exif"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return {
            "status": "success",
            "output_file": str(output_file),
            "tags_found": len(metadata[0]) if metadata else 0
        }
