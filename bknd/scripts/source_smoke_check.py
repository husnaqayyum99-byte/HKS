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

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result["status"] == "available" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())