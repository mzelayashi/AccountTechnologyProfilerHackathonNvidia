"""Network topology Excel reader for SE Draw.

Supports two formats:
  - Legacy 2-site: "Primary Site" / "Secondary/DR Site" sheet headers
  - Multi-site (N): "Site: <name>" headers with optional DC/Branch type hint

Both formats return the same unified structure:
  {'sites': [
      {'label': 'Primary DC', 'site_type': 'dc', 'categories': [...]},
      ...
  ]}

Each category dict contains:
  {'category': str, 'base_category': str, 'group': str, 'qty_model': str,
   'connected_to': str, 'end_of_support': str, 'rating': int|None, 'notes': str}

Numbered category variants (e.g., "Servers2") are supported. The 'category' field
includes the number ("Servers2") while 'base_category' is the canonical name ("Servers").
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from atlas.sedraw.constants import NET_CATEGORY_GROUPS, NET_CATEGORIES


# Build category -> group lookup from config
_CATEGORY_TO_GROUP = {}
for _group, _cats in NET_CATEGORY_GROUPS.items():
    for _cat in _cats:
        _CATEGORY_TO_GROUP[_cat.lower()] = _group

# All 23 recognised category names (case-insensitive lookup)
_CATEGORY_NAMES = {c.lower(): c for c in NET_CATEGORIES}

# Field labels that follow each category header (case-insensitive)
FIELD_LABELS = {
    'qty x model:': 'qty_model',
    'connected to:': 'connected_to',
    'end of support date:': 'end_of_support',
    'rating (1-5):': 'rating',
    'notes:': 'notes',
    'status:': 'status',
}


class NetworkReader:
    """Read form-style network topology Excel files."""

    def read_network_topology(self, excel_path: Path) -> Dict:
        """Parse a network topology Excel file into structured data.

        Automatically detects legacy (2-site) vs multi-site format.

        Returns:
            {'sites': [{'label': str, 'site_type': str, 'categories': [...]}]}
        """
        import openpyxl

        excel_path = Path(excel_path)
        if not excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {excel_path}")

        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb.active

        rows = []
        for row in ws.iter_rows(min_col=1, max_col=2, values_only=True):
            a_val = str(row[0]).strip() if row[0] is not None else ''
            b_val = str(row[1]).strip() if row[1] is not None else ''
            rows.append((a_val, b_val))

        wb.close()

        # Detect format: multi-site ("Site:") vs legacy ("Primary Site")
        has_site_prefix = any(r[0].lower().startswith('site:') for r in rows)

        if has_site_prefix:
            sites = self._parse_multi_site(rows)
        else:
            sites = self._parse_legacy(rows)

        if not sites:
            raise ValueError(f"No topology data found in {excel_path.name}")

        return {'sites': sites}

    # ── Multi-site format ─────────────────────────────────────────────────

    def _parse_multi_site(self, rows: List[tuple]) -> List[Dict]:
        """Parse 'Site: <name>' format with N sites."""
        # Find all site header indices
        site_indices = []
        for i, (a_val, b_val) in enumerate(rows):
            if a_val.lower().startswith('site:'):
                label = a_val[5:].strip()
                site_type = self._detect_site_type(label, b_val)
                site_indices.append((i, label, site_type))

        sites = []
        for pos, (start_idx, label, site_type) in enumerate(site_indices):
            end_idx = site_indices[pos + 1][0] if pos + 1 < len(site_indices) else len(rows)
            chunk = rows[start_idx + 1:end_idx]
            categories = self._parse_site(chunk)
            # Only include sites that have at least one populated category
            if any(c.get('qty_model') for c in categories):
                sites.append({
                    'label': label,
                    'site_type': site_type,
                    'categories': categories,
                })

        return sites

    @staticmethod
    def _detect_site_type(label: str, b_val: str) -> str:
        """Detect dc vs branch from label and column B hint."""
        b_lower = b_val.lower()
        if 'branch' in b_lower:
            return 'branch'
        if any(kw in b_lower for kw in ('dc', 'data', 'colo')):
            return 'dc'
        # Guess from label
        label_lower = label.lower()
        dc_keywords = ['dc', 'data center', 'datacenter', 'colo',
                        'primary', 'hq', 'headquarters', 'dr']
        if any(kw in label_lower for kw in dc_keywords):
            return 'dc'
        return 'branch'

    # ── Legacy 2-site format ──────────────────────────────────────────────

    def _parse_legacy(self, rows: List[tuple]) -> List[Dict]:
        """Parse legacy 'Primary Site' / 'Secondary/DR Site' format."""
        primary_start = None
        secondary_start = None

        for i, (a_val, _) in enumerate(rows):
            lower = a_val.lower()
            if 'primary site' in lower and 'secondary' not in lower:
                primary_start = i + 1
            elif 'secondary' in lower or 'dr site' in lower:
                secondary_start = i + 1

        sites = []

        if primary_start is not None:
            end = secondary_start - 1 if secondary_start else len(rows)
            categories = self._parse_site(rows[primary_start:end])
            if any(c.get('qty_model') for c in categories):
                sites.append({
                    'label': 'Primary Site',
                    'site_type': 'dc',
                    'categories': categories,
                })

        if secondary_start is not None:
            categories = self._parse_site(rows[secondary_start:])
            if any(c.get('qty_model') for c in categories):
                sites.append({
                    'label': 'Secondary/DR Site',
                    'site_type': 'dc',
                    'categories': categories,
                })

        # If no site headers found, treat entire sheet as one DC site
        if not sites and primary_start is None and secondary_start is None:
            categories = self._parse_site(rows)
            if any(c.get('qty_model') for c in categories):
                sites.append({
                    'label': 'Primary Site',
                    'site_type': 'dc',
                    'categories': categories,
                })

        return sites

    # ── Shared site parsing ───────────────────────────────────────────────

    def _parse_site(self, rows: List[tuple]) -> List[Dict]:
        """Parse rows for a single site into a list of category dicts."""
        categories = []

        i = 0
        while i < len(rows):
            a_val, b_val = rows[i]
            a_lower = a_val.lower().strip()

            # Check if this row is a category header (exact or numbered variant)
            canonical = None
            group = None
            base_category = None

            if a_lower in _CATEGORY_NAMES:
                canonical = _CATEGORY_NAMES[a_lower]
                base_category = canonical
                group = _CATEGORY_TO_GROUP.get(a_lower, 'other')
            else:
                # Numbered variant: e.g. "servers2", "firewalls3"
                m = re.match(r'^(.+?)(\d+)$', a_lower)
                if m and m.group(1) in _CATEGORY_NAMES:
                    base_name = m.group(1)
                    variant_num = m.group(2)
                    base_category = _CATEGORY_NAMES[base_name]
                    canonical = f"{base_category}{variant_num}"
                    group = _CATEGORY_TO_GROUP.get(base_name, 'other')

            if canonical:
                entry = {
                    'category': canonical,
                    'base_category': base_category,
                    'group': group,
                    'qty_model': '',
                    'connected_to': '',
                    'end_of_support': '',
                    'rating': None,
                    'notes': '',
                    'status': 'current',
                }

                # Scan next few rows for field labels
                for j in range(1, min(7, len(rows) - i)):
                    field_a, field_b = rows[i + j]
                    field_key = self._match_field_label(field_a)
                    if field_key:
                        if field_key == 'rating':
                            entry['rating'] = self._parse_rating(field_b)
                        elif field_key == 'status':
                            raw = str(field_b).strip().lower()
                            entry['status'] = 'refresh' if raw in ('refresh', 'future', 'planned') else 'current'
                        else:
                            entry[field_key] = field_b
                    elif self._is_category_header(field_a.lower().strip()):
                        break  # Hit next category
                    elif field_a.lower().startswith('site:'):
                        break  # Hit next site

                categories.append(entry)

            i += 1

        return categories

    @staticmethod
    def _is_category_header(text: str) -> bool:
        """Check if text is a known category name or a numbered variant."""
        if text in _CATEGORY_NAMES:
            return True
        m = re.match(r'^(.+?)(\d+)$', text)
        return bool(m and m.group(1) in _CATEGORY_NAMES)

    @staticmethod
    def _match_field_label(text: str) -> Optional[str]:
        text_lower = text.lower().strip()
        for label, key in FIELD_LABELS.items():
            if label in text_lower:
                return key
        return None

    @staticmethod
    def _parse_rating(value: str) -> Optional[int]:
        if not value:
            return None
        try:
            rating = int(float(value))
            if 1 <= rating <= 5:
                return rating
        except (ValueError, TypeError):
            pass
        return None
