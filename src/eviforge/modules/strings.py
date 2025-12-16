from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence
from eviforge.modules.base import ForensicModule


class StringsModule(ForensicModule):
    @property
    def name(self) -> str:
        return "strings"

    @property
    def description(self) -> str:
        return "Extracts printable strings from binary files."

    def run(self, case_id: str, evidence_id: str, min_length: int = 4, max_strings: int = 10000, **kwargs) -> Dict[str, Any]:
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)

        with SessionLocal() as session:
            evidence = session.get(Evidence, evidence_id)
            if not evidence:
                raise ValueError(f"Evidence {evidence_id} not found")

            full_path = settings.vault_dir / evidence.path
            if not full_path.exists():
                raise FileNotFoundError(f"Evidence file missing at {full_path}")

            if not full_path.is_file():
                return {"error": "Strings extraction only supported on single files"}

            extracted_strings = []
            count = 0
            
            # Simple regex for printable strings
            # ASCII range 32-126, min_length chars
            pattern = re.compile(rb"[\x20-\x7E]{" + str(min_length).encode() + rb",}")
            
            try:
                # Process in chunks to avoid memory issues for large files
                with full_path.open("rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)  # 1MB chunk
                        if not chunk:
                            break
                        
                        matches = pattern.findall(chunk)
                        for m in matches:
                            s = m.decode("ascii", errors="ignore")
                            extracted_strings.append(s)
                            count += 1
                            if count >= max_strings:
                                break
                        if count >= max_strings:
                            break
            except Exception as e:
                 return {"error": f"Failed to extract strings: {e}"}

            case_root = settings.vault_dir / case_id
            artifact_dir = case_root / "artifacts" / "strings"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            output_file = artifact_dir / f"{evidence_id}.json"
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(
                    {
                        "count": count,
                        "limit_reached": count >= max_strings,
                        "min_length": min_length,
                        "max_strings": max_strings,
                        "strings": extracted_strings,
                    },
                    f,
                    indent=2,
                )

            return {
                "status": "success",
                "count": count,
                "limit_reached": count >= max_strings,
                "output_file": str(output_file),
            }
