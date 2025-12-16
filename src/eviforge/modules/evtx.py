from typing import Any, Dict
import json
from pathlib import Path

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence

class EvtxModule(ForensicModule):
    @property
    def name(self) -> str:
        return "evtx"

    @property
    def description(self) -> str:
        return "Parse Windows EVTX event logs"

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

        if file_path.suffix.lower() != ".evtx":
             return {"status": "skipped", "reason": "Not an EVTX file"}

        import Evtx.Evtx as evtx
        import xml.etree.ElementTree as ET

        events = []
        try:
            with evtx.Evtx(str(file_path)) as log:
                for i, record in enumerate(log.records()):
                    if i > 1000: break # Cap for MVP speed
                    try:
                        # record.xml() returns string
                        xml_str = record.xml()
                        # Parse XML to JSON-ish
                        # This is heavy. Let's just store specific fields if possible or raw XML snippet
                        # For finding/alerting (Step 4), we need EventID
                        root = ET.fromstring(xml_str)
                        # Namespace hell usually {http://schemas.microsoft.com/win/2004/08/events/event}
                        # Let's just regex or substring for simple parsing without namespace overhead logic
                        # But for robustness, Evtx usually parses well.
                        
                        # Extract System/EventID
                        ns = {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}
                        sys_node = root.find('ns:System', ns)
                        event_id = sys_node.find('ns:EventID', ns).text
                        time_created = sys_node.find('ns:TimeCreated', ns).attrib.get('SystemTime')
                        
                        events.append({
                            "offset": record.offset(),
                            "event_id": event_id,
                            "timestamp": time_created,
                            "xml_excerpt": xml_str[:500] # Truncate
                        })
                    except Exception:
                        continue
        except Exception as e:
            raise RuntimeError(f"EVTX parsing failed: {e}")

        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "evtx"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

        return {
            "status": "success",
            "events_count": len(events),
            "output_file": str(output_file)
        }
