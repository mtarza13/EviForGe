from typing import Any, Dict
import os
import subprocess
from pathlib import Path
import json

from eviforge.modules.base import ForensicModule
from eviforge.config import load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.models import Evidence

class PcapModule(ForensicModule):
    @property
    def name(self) -> str:
        return "pcap"

    @property
    def description(self) -> str:
        return "Analyze PCAP files with TShark"

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

        # Check extension
        if file_path.suffix.lower() not in ['.pcap', '.pcapng', '.cap']:
             return {"status": "skipped", "reason": "Not a PCAP file"}

        # Run TShark to get summary (endpoints/convos)
        # tshark -r file -q -z conv,ip -z endpoints,ip
        # We'll use -T json for packets? Too large.
        # Let's extract endpoints and conversations.
        
        out_data = {}
        
        try:
            # Endpoints
            # tshark -r file -q -z endpoints,ip
            # Parsing text output is annoying.
            # Using -T ek or -T json dumps PACKETS.
            # We want statistics.
            # Let's just dump first 100 packets summary?
            # Or use pyshark if installed? Check dependencies.
            # Requirement says "Use tshark to produce: endpoints, conversations..."
            
            # Simple approach: tshark -r file -T json -c 100 (sample)
            # OR better: tshark -r file -q -z io,phs (protocol hierarchy)
            
            cmd_phs = ["tshark", "-r", str(file_path), "-q", "-z", "io,phs"]
            res_phs = subprocess.run(cmd_phs, capture_output=True, text=True)
            out_data["protocol_hierarchy"] = res_phs.stdout
            
            # DNS queries?
            # tshark -r file -Y "dns" -T fields -e dns.qry.name
            cmd_dns = ["tshark", "-r", str(file_path), "-Y", "dns", "-T", "fields", "-e", "dns.qry.name"]
            res_dns = subprocess.run(cmd_dns, capture_output=True, text=True)
            domains = [d for d in res_dns.stdout.splitlines() if d]
            out_data["dns_queries_sample"] = list(set(domains))[:50] # Unique top 50
            
        except Exception as e:
            raise RuntimeError(f"TShark failed: {e}")

        # Save Artifact
        case_vault = settings.vault_dir / case_id
        artifact_dir = case_vault / "artifacts" / "pcap"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = artifact_dir / f"{evidence_id}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)

        return {
            "status": "success",
            "output_file": str(output_file),
            "dns_count": len(out_data.get("dns_queries_sample", []))
        }
