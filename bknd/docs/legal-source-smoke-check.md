# Legal Source Smoke Check

Run from the backend directory after installing backend requirements:

```powershell
python scripts/source_smoke_check.py
```

The script checks only active, curated registry URLs. It reports the final URL,
same-domain redirect status, whether HTML text or extractable PDF text was
available, a content hash, and the check time. Exit code `0` means every
configured page was reachable and readable; exit code `1` means at least one
page was unavailable, redirected outside its registered domain, or unreadable.

This is a live connectivity and text-extraction check, not a legal review. It
does not prove that a law is current, that a service applies to a user's case,
or that a procedure or document requirement has been completely retrieved.
Freshness is `unknown` until a previous content hash is supplied. A changed
hash is a review signal, not proof that the source is stale or legally amended.
The regular test suite should continue to mock government websites and must
not depend on this script succeeding.