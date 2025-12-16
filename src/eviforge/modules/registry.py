from typing import Any, Dict
import json
from pathlib import Path

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence

class RegistryModule(ForensicModule):
    @property
    def name(self) -> str:
        return "registry"

    @property
    def description(self) -> str:
        return "Parse Windows Registry Hives"

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

        name = file_path.name.upper()
        if name not in ["NTUSER.DAT", "SYSTEM", "SOFTWARE", "SAM", "SECURITY"]:
             return {"status": "skipped", "reason": "Not a recognized Registry Hive file"}

        from Registry import Registry

        results = {}
        try:
            reg = Registry.Registry(str(file_path))
            
            # Helper to recursively dump keys? Too big.
            # Targeted extraction.
            if name == "NTUSER.DAT":
                # Run keys
                try:
                    k = reg.open("Software\\Microsoft\\Windows\\CurrentVersion\\Run")
                    results["Run"] = [v.name() for v in k.values()]
                except:
                    pass
            elif name == "SOFTWARE":
                 # CurrentVersion
                 try:
                    k = reg.open("Microsoft\\Windows NT\\CurrentVersion")
                    results["CurrentVersion"] = [v.value() for v in k.values() if v.name() == "ProductName"]
                 except:
                    pass

        except Exception as e:
            raise RuntimeError(f"Registry parsing failed: {e}")

        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "registry"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        return {
            "status": "success",
            "keys_extracted": list(results.keys()),
            "output_file": str(output_file)
        }
