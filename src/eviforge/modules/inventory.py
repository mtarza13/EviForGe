from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence
from eviforge.modules.base import ForensicModule


class InventoryModule(ForensicModule):
    @property
    def name(self) -> str:
        return "inventory"

    @property
    def description(self) -> str:
        return "Recursively lists files in the evidence and collects metadata."

    def run(self, case_id: str, evidence_id: str, **kwargs) -> Dict[str, Any]:
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)
        
        with SessionLocal() as session:
            evidence = session.get(Evidence, evidence_id)
            if not evidence:
                raise ValueError(f"Evidence {evidence_id} not found")
            
            # Evidence path is stored relative to vault root in DB, or we can construct it
            # Model says: path: Mapped[str] = mapped_column(String(4096), nullable=False)
            # Ingest stores: str(dest_path.relative_to(settings.vault_dir))
            
            full_path = settings.vault_dir / evidence.path
            
            if not full_path.exists():
                raise FileNotFoundError(f"Evidence file missing at {full_path}")
                
            results = []
            
            if full_path.is_file():
                # Single file ingest
                stat = full_path.stat()
                results.append({
                    "path": evidence.path,
                    "size": stat.st_size,
                    "created": stat.st_ctime,
                    "modified": stat.st_mtime,
                    "is_dir": False
                })
            elif full_path.is_dir():
                # Directory ingest (if supported later)
                for p in full_path.rglob("*"):
                    stat = p.stat()
                    results.append({
                        "path": str(p.relative_to(settings.vault_dir)),
                        "size": stat.st_size,
                        "created": stat.st_ctime,
                        "modified": stat.st_mtime,
                        "is_dir": p.is_dir()
                    })
            
            case_root = settings.vault_dir / case_id
            artifact_dir = case_root / "artifacts" / "inventory"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            output_file = artifact_dir / f"{evidence_id}.json"
            with output_file.open("w", encoding="utf-8") as f:
                json.dump({"file_count": len(results), "files": results}, f, indent=2)

            return {"status": "success", "file_count": len(results), "output_file": str(output_file)}
