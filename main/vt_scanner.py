"""
vt_scanner.py — VirusTotal File Scan Helper
============================================
Scans uploaded file bytes against the VirusTotal API.

Flow
----
1. Hash the bytes (SHA-256) → check if VT already has a report (GET /files/{hash})
   - Hit  → return existing verdict instantly (saves quota)
   - Miss → upload bytes (POST /files) → get analysis ID
2. Poll GET /analyses/{id} every 5 s (max 90 s) until status == "completed"
3. Return a simple verdict dict.

Usage
-----
    from main.vt_scanner import scan_bytes
    result = await scan_bytes(file_data, filename)
    # result = {safe, malicious, suspicious, undetected, engines_total, verdict, scan_id}
"""

import asyncio
import hashlib
import os
import httpx

VT_BASE = "https://www.virustotal.com/api/v3"
POLL_INTERVAL = 5      # seconds between polls
POLL_TIMEOUT  = 90    # max seconds to wait for analysis


def _get_key() -> str:
    key = os.environ.get("VT_API_KEY", "")
    if not key or key == "YOUR_VIRUSTOTAL_API_KEY_HERE":
        raise RuntimeError(
            "VT_API_KEY is not set. Add it to your .env file: VT_API_KEY=your_key_here"
        )
    return key


def _headers() -> dict:
    return {"x-apikey": _get_key(), "Accept": "application/json"}


def _parse_stats(stats: dict) -> dict:
    malicious   = stats.get("malicious", 0)
    suspicious  = stats.get("suspicious", 0)
    undetected  = stats.get("undetected", 0)
    harmless    = stats.get("harmless", 0)
    total       = malicious + suspicious + undetected + harmless
    safe        = malicious == 0 and suspicious == 0
    if malicious > 0:
        verdict = f"MALICIOUS ({malicious}/{total} engines flagged)"
    elif suspicious > 0:
        verdict = f"SUSPICIOUS ({suspicious}/{total} engines warned)"
    else:
        verdict = f"CLEAN ({total} engines checked)"
    return {
        "safe":          safe,
        "malicious":     malicious,
        "suspicious":    suspicious,
        "undetected":    undetected,
        "engines_total": total,
        "verdict":       verdict,
    }


async def _poll_analysis(analysis_id: str, client: httpx.AsyncClient) -> dict:
    """Poll until the analysis is complete, then return parsed stats."""
    url = f"{VT_BASE}/analyses/{analysis_id}"
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        data   = resp.json()
        attrs  = data.get("data", {}).get("attributes", {})
        status = attrs.get("status", "")
        if status == "completed":
            return _parse_stats(attrs.get("stats", {}))
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    # Timeout — treat as safe to avoid blocking users indefinitely
    print(f"[VTScanner] Analysis {analysis_id} timed out after {POLL_TIMEOUT}s — treating as safe")
    return {
        "safe": True, "malicious": 0, "suspicious": 0,
        "undetected": 0, "engines_total": 0,
        "verdict": "SCAN TIMEOUT — treated as clean",
    }


async def scan_bytes(data: bytes, filename: str) -> dict:
    """
    Scan file bytes against VirusTotal.
    Returns a verdict dict (see module docstring).
    """
    sha256 = hashlib.sha256(data).hexdigest()

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Check if VT already has this file's report
        try:
            resp = await client.get(f"{VT_BASE}/files/{sha256}", headers=_headers())
            if resp.status_code == 200:
                attrs = resp.json().get("data", {}).get("attributes", {})
                stats = attrs.get("last_analysis_stats", {})
                if stats:
                    result = _parse_stats(stats)
                    result["scan_id"] = sha256
                    result["cached"]  = True
                    print(f"[VTScanner] Cache hit for {filename}: {result['verdict']}")
                    return result
        except Exception as e:
            print(f"[VTScanner] Hash lookup failed ({e}), will upload fresh")

        # 2. Upload the file
        upload_resp = await client.post(
            f"{VT_BASE}/files",
            headers=_headers(),
            files={"file": (filename, data, "text/csv")},
            timeout=60,
        )
        upload_resp.raise_for_status()
        analysis_id = upload_resp.json()["data"]["id"]
        print(f"[VTScanner] Uploaded {filename} → analysis {analysis_id}")

        # 3. Poll until complete
        result = await _poll_analysis(analysis_id, client)
        result["scan_id"] = analysis_id
        result["cached"]  = False
        print(f"[VTScanner] {filename}: {result['verdict']}")
        return result
