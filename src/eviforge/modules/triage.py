from __future__ import annotations

import json
import math
import collections
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Dict

from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence
from eviforge.config import load_settings
from eviforge.modules.base import ForensicModule


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    entropy = 0
    counts = collections.Counter(data)
    length = len(data)
    for count in counts.values():
        p = count / length
        entropy -= p * math.log(p, 2)
    return entropy


class TriageModule(ForensicModule):
    @property
    def name(self) -> str:
        return "triage"

    @property
    def description(self) -> str:
        return "Basic file triage (Entropy, MIME check)"

    def run(self, case_id: str, evidence_id: str, **kwargs) -> Dict[str, Any]:
        settings = load_settings()
        SessionLocal = create_session_factory(settings.database_url)
        
        with SessionLocal() as session:
            ev = session.get(Evidence, evidence_id)
            if not ev:
                raise ValueError(f"Evidence {evidence_id} not found")
            file_path = settings.vault_dir / ev.path
            original_filename = Path(file_path).name # Or get from DB if we stored original name separately
            
        if not file_path.exists():
             raise FileNotFoundError(f"Evidence file not found at {file_path}")

        # 1. Read start/end for entropy (triage usually doesn't read full ISOs)
        # Read first 1MB for entropy calc or full file if small
        size = file_path.stat().st_size
        read_size = min(size, 1024 * 1024) 
        
        with open(file_path, "rb") as f:
            data = f.read(read_size)
            
        entropy = shannon_entropy(data)
        
        # 2. Extension Check
        guessed_type, _ = mimetypes.guess_type(original_filename)
        # In a real tool we'd use libmagic here (python-magic)
        # But let's stick to stdlib or basic heuristics for MVP without extra deps if possible
        # We installed 'file' command, so we can use subprocess
        
        import subprocess
        try:
             res = subprocess.run(["file", "--mime-type", "-b", str(file_path)], capture_output=True, text=True)
             magic_mime = res.stdout.strip()
        except:
             magic_mime = "unknown"

        is_suspicious = False
        if entropy > 7.5:
            is_suspicious = True # Packed/Encrypted
        
        result = {
            "entropy": entropy,
            "mime_magic": magic_mime,
            "mime_guessed": guessed_type,
            "is_suspicious": is_suspicious,
            "size": size
        }

        case_root = settings.vault_dir / case_id
        artifact_dir = case_root / "artifacts" / "triage"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        output_file = artifact_dir / f"{evidence_id}.json"
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        return {"status": "success", **result, "output_file": str(output_file)}
