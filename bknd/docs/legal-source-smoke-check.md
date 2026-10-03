# Legal Source Smoke Check

Run from the backend directory after installing backend requirements:

```powershell
python scripts/source_smoke_check.py
```

The script checks only active, curated registry URLs. It reports each requested
and final URL, HTTP status, same-domain redirect status, whether HTML text or
extractable PDF text was available, a content hash, and the check time. A
failure summary includes the source, cause, URL, and attempts. It makes up to
three attempts for transient connection/timeouts, HTTP 429, or HTTP 5xx
responses. It does not retry access-denied responses such as HTTP 403. Exit
code `0` means every configured page was reachable and readable; exit code `1`
means at least one page was unavailable, redirected outside its registered
domain, or unreadable. A non-zero result can therefore correctly report remote
site restrictions and is not itself evidence of a code defect.

This is a live connectivity and text-extraction check, not a legal review. It
does not prove that a law is current, that a service applies to a user's case,
or that a procedure or document requirement has been completely retrieved.
Freshness is `unknown` until a previous content hash is supplied. A changed
hash is a review signal, not proof that the source is stale or legally amended.
The regular test suite should continue to mock government websites and must
not depend on this script succeeding.