import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.legal_sources.source_health import check_source_health
from app.legal_sources.source_registry import LEGAL_SOURCES


def main() -> int:
    sources = [source for source in LEGAL_SOURCES if source.active]
    with ThreadPoolExecutor(max_workers=min(6, len(sources) or 1)) as executor:
        results = list(executor.map(check_source_health, sources))

    failures = [result for result in results if result["status"] != "available"]
    if failures:
        print("Source smoke check failed for the following registered URLs:")
        for result in failures:
            print(
                f"- {result['source_name']}: "
                f"{result.get('failure_reason') or result['status']} "
                f"(HTTP {result.get('http_status') or 'unknown'}; "
                f"attempts: {result.get('attempts', 1)}; "
                f"URL: {result.get('requested_url', 'unknown')})"
            )
        print()

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())