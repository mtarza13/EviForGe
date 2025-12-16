from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence
from eviforge.modules.base import ForensicModule


class TimelineModule(ForensicModule):
    @property
    def name(self) -> str:
        return "timeline"

    @property
    def description(self) -> str:
        return "Extracts MACE (Modified, Accessed, Created) timestamps to build a chronological event list."

    def run(self, case_id: str, evidence_id: str, **kwargs) -> Dict[str, Any]:
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)

        with SessionLocal() as session:
            evidence = session.get(Evidence, evidence_id)
            if not evidence:
                raise ValueError(f"Evidence {evidence_id} not found")

            full_path = settings.vault_dir / evidence.path
            if not full_path.exists():
                raise FileNotFoundError(f"Evidence file missing at {full_path}")

            events: List[Dict[str, Any]] = []

            def process_file(p: Path):
                try:
                    stat = p.stat()
                    # MACE: Modified, Accessed, Created (Metadata Change usually for unix 'ctime', but python .stat() ctime is creation on Windows, metadata change on Unix. We'll label generic 'ctime'.)
                    
                    # Modified
                    events.append({
                        "timestamp": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        "type": "MODIFIED",
                        "path": str(p.relative_to(settings.vault_dir)),
                        "details": f"File Modified (Size: {stat.st_size})"
                    })
                    
                    # Accessed
                    events.append({
                        "timestamp": datetime.fromtimestamp(stat.st_atime, tz=timezone.utc).isoformat(),
                        "type": "ACCESSED",
                        "path": str(p.relative_to(settings.vault_dir)),
                        "details": "File Accessed"
                    })
                    
                    # Created / Metadata Change
                    events.append({
                        "timestamp": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
                        "type": "CHANGED",
                        "path": str(p.relative_to(settings.vault_dir)),
                        "details": "File Metadata Changed / Created"
                    })
                    
                except Exception as e:
                    # Log error but continue
                    events.append({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "type": "ERROR",
                        "path": str(p),
                        "details": str(e)
                    })

            if full_path.is_file():
                process_file(full_path)
            elif full_path.is_dir():
                for p in full_path.rglob("*"):
                    if p.is_file():
                        process_file(p)

            # Sort by timestamp
            events.sort(key=lambda x: x["timestamp"])

            case_root = settings.vault_dir / case_id
            artifact_dir = case_root / "artifacts" / "timeline"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            output_file = artifact_dir / f"{evidence_id}.json"
            with output_file.open("w", encoding="utf-8") as f:
                json.dump({"event_count": len(events), "events": events}, f, indent=2)

            return {"status": "success", "event_count": len(events), "output_file": str(output_file)}
