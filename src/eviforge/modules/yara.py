from typing import Any, Dict, List
import yara
import os
from pathlib import Path

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence

class YaraModule(ForensicModule):
    @property
    def name(self) -> str:
        return "yara"

    @property
    def description(self) -> str:
        return "Scan files with YARA rules"

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

        # Rules directory: repo_root/rules/yara
        # Ideally passed via config or env. Defaulting to project structure.
        # Assuming we can find 'rules/yara' relative to project root or in a known location.
        # In Docker, we might need to mount it.
        # MVP: Create a dummy rule if none exist, or scan with a basic rule.
        
        rules_dir = Path("/app/rules/yara") # Docker path
        if not rules_dir.exists():
             # Fallback or create for testing
             rules_dir.mkdir(parents=True, exist_ok=True)
             
        # Compile rules
        filepaths = {}
        for r in rules_dir.glob("*.yar"):
            filepaths[r.name] = str(r)
            
        if not filepaths:
            return {"status": "skipped", "reason": "No YARA rules found in /app/rules/yara"}
            
        try:
            rules = yara.compile(filepaths=filepaths)
        except Exception as e:
            raise RuntimeError(f"Failed to compile YARA rules: {e}")

        matches = rules.match(str(file_path))
        
        results = []
        for m in matches:
            results.append({
                "rule": m.rule,
                "tags": m.tags,
                "meta": m.meta,
                "strings": [(s[0], s[1], str(s[2])) for s in m.strings[:10]] # Limit captured strings
            })

        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "yara"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        
        import json
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        return {
            "status": "success",
            "matches_count": len(results),
            "output_file": str(output_file)
        }
