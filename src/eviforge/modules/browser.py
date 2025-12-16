from typing import Any, Dict
import json
import sqlite3
import shutil
from pathlib import Path

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence

class BrowserModule(ForensicModule):
    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "Parse Browser History (Chrome/Firefox)"

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

        # Basic SQLite check for History
        # We try to open as SQLite and query 'urls' (Chrome) or 'moz_places' (Firefox)
        
        history = []
        is_sqlite = False
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)
                if b'SQLite format 3' in header:
                    is_sqlite = True
        except:
            pass
            
        if not is_sqlite:
             return {"status": "skipped", "reason": "Not a SQLite DB"}

        # Copy to temp because we are read-only and locks might happen
        temp_db = Path(f"/tmp/browser_{evidence_id}.sqlite")
        shutil.copy(file_path, temp_db)
        
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # Chrome/Edge: urls table
            try:
                cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls LIMIT 100")
                for row in cursor.fetchall():
                    history.append({
                        "url": row[0],
                        "title": row[1],
                        "visits": row[2],
                        "timestamp": row[3], # Webkit timestamp
                        "browser": "Chrome/Edge"
                    })
            except:
                pass
                
            # Firefox: moz_places table
            try:
                cursor.execute("SELECT url, title, visit_count, last_visit_date FROM moz_places LIMIT 100")
                for row in cursor.fetchall():
                    history.append({
                        "url": row[0],
                        "title": row[1],
                        "visits": row[2],
                        "timestamp": row[3], # PRTime
                        "browser": "Firefox"
                    })
            except:
                pass
                
            conn.close()
        except Exception as e:
             raise RuntimeError(f"Browser parsing failed: {e}")
        finally:
            if temp_db.exists():
                temp_db.unlink()

        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "browser"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        return {
            "status": "success",
            "history_count": len(history),
            "output_file": str(output_file)
        }
