"""Parse the CURRENT OneNoteTR/trips.mht fresh (ignoring the stale cache) using the old tool's
MHTParser, and dump the reports to cache/fresh_trips.json for the migration to consume."""
import json
import sys
from pathlib import Path

OLD = r"C:\ATPtool\SHI Account Technology Profiler"
sys.path.insert(0, OLD)

import mht_parser  # noqa: E402
# Redirect its cache write to a temp path so we DON'T overwrite the user's .parsed_trips_cache.json
mht_parser.CACHE_FILE = Path(r"C:\hackathonsandbox\cache\_fresh_trips_cache.json")
from mht_parser import MHTParser  # noqa: E402

reports = MHTParser(Path(OLD) / "OneNoteTR" / "trips.mht").parse_mht(use_cache=False)
out = [r.to_dict() for r in reports]
Path(r"C:\hackathonsandbox\cache\fresh_trips.json").write_text(
    json.dumps({"reports": out}, ensure_ascii=False), encoding="utf-8")
print("PARSED", len(reports), "reports")
# quick customer sanity
from collections import Counter
c = Counter((r.metadata.customer_name or "?").strip() for r in reports)
for name, n in c.most_common(15):
    print(f"  {n:3}  {name}".encode("ascii", "replace").decode())
