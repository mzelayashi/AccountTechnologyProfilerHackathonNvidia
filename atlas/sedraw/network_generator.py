"""Draw.io Network Topology Diagram Generator.

Generates editable .drawio XML files showing multi-site network topology
diagrams with embedded SVG icons and rating-based coloring.

Supports N sites in a grid layout:
  - DC sites: up to 2 per row at 520px width
  - Branch sites: up to 3 per row at 340px width
  - BFS-tiered 2D layout with fan-out connections within each site
"""
import html as html_mod
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from atlas.sedraw.constants import (
    NET_SITE_WIDTH, NET_SITE_PADDING, NET_SITE_GAP,
    NET_TITLE_HEIGHT,
    RATING_COLORS, NET_CONNECTION_COLORS,
    ICONS_DIR, CATEGORY_ICON_MAP, NET_ICON_WIDTH, NET_ICON_HEIGHT,
    NET_BRANCH_SITE_WIDTH, NET_DC_COLUMNS, NET_BRANCH_COLUMNS, NET_ROW_GAP,
    NET_TIER_ROW_HEIGHT, NET_TIER_H_PAD, NET_SITE_CONTAINER_PAD,
    REFRESH_COLORS, SECTION_SEPARATOR_COLORS, NET_SECTION_SEPARATOR_HEIGHT,
)


def _shares_numbered_base(a: str, b: str) -> bool:
    """True if a and b are the same base category with different trailing numbers.

    E.g. "servers" and "servers2" share a base; "servers2" and "servers3" share
    a base.  These should NOT partial-match each other.
    """
    import re
    ma = re.match(r'^(.+?)(\d+)?$', a)
    mb = re.match(r'^(.+?)(\d+)?$', b)
    if ma and mb:
        return ma.group(1) == mb.group(1) and (ma.group(2) or '') != (mb.group(2) or '')
    return False


class NetworkTopologyGenerator:
    """Generate Draw.io XML for network topology diagrams."""

    SITE_HEADER_COLORS = {
        'dc':     {'fill': '#37474f', 'stroke': '#455a64', 'font': '#eceff1'},
        'branch': {'fill': '#4e342e', 'stroke': '#6d4c41', 'font': '#efebe9'},
    }

    # Priority order for BFS root selection
    ROOT_PRIORITY = ['router', 'firewalls', 'sd-wan', 'core switch']

    def __init__(self):
        self._icon_cache: Dict[str, str] = {}
        self._icons_loaded = False
        self._edge_counter = 0

    def _load_icons(self):
        if self._icons_loaded:
            return
        for category, filename in CATEGORY_ICON_MAP.items():
            icon_path = ICONS_DIR / filename
            if icon_path.exists():
                svg_text = icon_path.read_text(encoding='utf-8')
                encoded = quote(svg_text, safe='')
                self._icon_cache[category] = encoded
        self._icons_loaded = True

    # ── public API ────────────────────────────────────────────────────────

    def generate(self, customer_name: str, network_data: Dict,
                 output_path: Path, generate_legend: bool = True) -> Path:
        """Generate a network topology .drawio file.

        Args:
            customer_name: Customer name for title
            network_data: {'sites': [...]} from NetworkReader, or legacy dict
            output_path: Where to save the .drawio file
            generate_legend: If True, add a Legend & Specifications tab
        """
        self._load_icons()
        self._edge_counter = 0

        # Convert legacy format to multi-site
        if 'sites' not in network_data:
            network_data = self._convert_legacy(network_data)

        sites = network_data['sites']
        if not sites:
            raise ValueError("No sites found in network data")

        nodes = []
        edges = []
        node_id = 2  # 0 and 1 reserved

        # Calculate grid layout positions
        layout, canvas_w, canvas_h = self._calculate_grid_layout(sites)

        # Title bar
        title_label = f"{customer_name} - Network Topology"
        nodes.append({
            'id': str(node_id),
            'label': title_label,
            'x': NET_SITE_PADDING, 'y': NET_SITE_PADDING,
            'width': canvas_w, 'height': NET_TITLE_HEIGHT,
            'type': 'title',
        })
        node_id += 1

        # Render each site
        for site, sx, sy, sw in layout:
            node_id = self._render_site(
                site, sx, sy, sw, nodes, edges, node_id)

        # Build topology diagram XML
        topo_xml = self._generate_diagram_xml(
            title_label, "networktopo", nodes, edges,
            canvas_w + NET_SITE_PADDING * 2,
            canvas_h + NET_SITE_PADDING * 2)

        # Build legend diagram XML if requested
        diagram_xmls = [topo_xml]
        if generate_legend:
            legend_xml = self._generate_legend_diagram(customer_name, sites)
            diagram_xmls.append(legend_xml)

        xml_content = self._wrap_mxfile(*diagram_xmls)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)

        return output_path

    # ── legacy conversion ─────────────────────────────────────────────────

    @staticmethod
    def _convert_legacy(data: Dict) -> Dict:
        sites = []
        if 'primary_site' in data and data['primary_site']:
            sites.append({
                'label': data['primary_site'].get('label', 'Primary Site'),
                'site_type': 'dc',
                'categories': data['primary_site']['categories'],
            })
        if 'secondary_site' in data and data['secondary_site']:
            sites.append({
                'label': data['secondary_site'].get('label', 'Secondary/DR Site'),
                'site_type': 'dc',
                'categories': data['secondary_site']['categories'],
            })
        return {'sites': sites}

    # ── grid layout ───────────────────────────────────────────────────────

    def _calculate_grid_layout(self, sites: list):
        """Compute (site, x, y, width) for each site + canvas dimensions."""
        dc_sites = [s for s in sites if s.get('site_type') == 'dc']
        branch_sites = [s for s in sites if s.get('site_type') != 'dc']

        layout = []
        y_start = NET_SITE_PADDING + NET_TITLE_HEIGHT + 20
        current_y = y_start
        max_row_width = 0

        # DC rows (2 per row)
        if dc_sites:
            for row_start in range(0, len(dc_sites), NET_DC_COLUMNS):
                row = dc_sites[row_start:row_start + NET_DC_COLUMNS]
                row_h = 0
                row_w = 0
                for col, site in enumerate(row):
                    x = NET_SITE_PADDING + col * (NET_SITE_WIDTH + NET_SITE_GAP)
                    h = self._calculate_site_height(site['categories'], NET_SITE_WIDTH)
                    layout.append((site, x, current_y, NET_SITE_WIDTH))
                    row_h = max(row_h, h)
                    row_w = x + NET_SITE_WIDTH - NET_SITE_PADDING
                max_row_width = max(max_row_width, row_w)
                current_y += row_h + NET_ROW_GAP

        # Branch rows (3 per row)
        if branch_sites:
            for row_start in range(0, len(branch_sites), NET_BRANCH_COLUMNS):
                row = branch_sites[row_start:row_start + NET_BRANCH_COLUMNS]
                row_h = 0
                row_w = 0
                for col, site in enumerate(row):
                    x = NET_SITE_PADDING + col * (NET_BRANCH_SITE_WIDTH + NET_SITE_GAP)
                    h = self._calculate_site_height(site['categories'], NET_BRANCH_SITE_WIDTH)
                    layout.append((site, x, current_y, NET_BRANCH_SITE_WIDTH))
                    row_h = max(row_h, h)
                    row_w = x + NET_BRANCH_SITE_WIDTH - NET_SITE_PADDING
                max_row_width = max(max_row_width, row_w)
                current_y += row_h + NET_ROW_GAP

        canvas_w = max(max_row_width, 400)
        canvas_h = current_y

        return layout, canvas_w, canvas_h

    @staticmethod
    def _partition_by_status(categories: List[Dict]):
        """Split populated categories into (current_cats, refresh_cats)."""
        current = [c for c in categories if c.get('qty_model') and c.get('status', 'current') == 'current']
        refresh = [c for c in categories if c.get('qty_model') and c.get('status', 'current') == 'refresh']
        return current, refresh

    def _calculate_site_height(self, categories: List[Dict],
                               site_width: int) -> int:
        """Calculate total height based on number of BFS tiers, accounting for dual sections."""
        current_cats, refresh_cats = self._partition_by_status(categories)
        site_header_h = 36
        height = site_header_h + NET_SITE_CONTAINER_PAD * 2 + 10

        current_tiers = self._compute_tiers(current_cats) if current_cats else {}
        refresh_tiers = self._compute_tiers(refresh_cats) if refresh_cats else {}

        num_current = max(len(current_tiers), 1) if current_cats else 0
        num_refresh = max(len(refresh_tiers), 1) if refresh_cats else 0

        height += num_current * NET_TIER_ROW_HEIGHT
        height += num_refresh * NET_TIER_ROW_HEIGHT

        # Add separator if both sections exist
        if current_cats and refresh_cats:
            height += NET_SECTION_SEPARATOR_HEIGHT + 10

        # At least 1 tier if somehow empty
        if not current_cats and not refresh_cats:
            height += NET_TIER_ROW_HEIGHT

        return height

    # ── BFS tier computation ──────────────────────────────────────────────

    def _compute_tiers(self, categories: List[Dict]) -> Dict[int, List[Dict]]:
        """Build adjacency graph from connected_to fields, BFS to assign tiers.

        Returns {tier_number: [category_dicts]} where tier 0 is the root.
        """
        if not categories:
            return {}

        # Build lookup and bidirectional adjacency graph
        cat_by_name: Dict[str, Dict] = {}
        adj: Dict[str, set] = {}

        for cat in categories:
            name = cat['category'].lower()
            cat_by_name[name] = cat
            adj.setdefault(name, set())

            conn = cat.get('connected_to', '').strip()
            if conn:
                for target in conn.split(','):
                    target = target.strip().lower()
                    if target:
                        adj[name].add(target)
                        adj.setdefault(target, set())
                        adj[target].add(name)

        # Select root by priority order
        root = None
        for priority_name in self.ROOT_PRIORITY:
            if priority_name in cat_by_name:
                root = priority_name
                break
        if root is None:
            root = max(cat_by_name.keys(),
                       key=lambda n: len(adj.get(n, set())))

        # BFS from root
        visited: Dict[str, int] = {root: 0}
        queue = deque([root])

        while queue:
            current = queue.popleft()
            current_tier = visited[current]
            for neighbor in sorted(adj.get(current, set())):
                if neighbor not in visited and neighbor in cat_by_name:
                    visited[neighbor] = current_tier + 1
                    queue.append(neighbor)

        # Assign disconnected devices to an extra tier
        max_tier = max(visited.values()) if visited else 0
        for name in cat_by_name:
            if name not in visited:
                max_tier += 1
                visited[name] = max_tier

        # Build tier -> [categories] mapping
        tiers: Dict[int, List[Dict]] = {}
        for name, tier in visited.items():
            if name in cat_by_name:
                tiers.setdefault(tier, []).append(cat_by_name[name])

        return tiers

    # ── site rendering ────────────────────────────────────────────────────

    def _render_section(self, tiers, sx, tier_start_y, sw, nodes,
                        node_id, node_map, device_nodes,
                        force_refresh_colors=False, status_suffix=''):
        """Render devices for one section (current or refresh) into BFS tiers."""
        icon_w = min(NET_ICON_WIDTH, sw - 40)

        for tier_num in sorted(tiers.keys()):
            tier_cats = tiers[tier_num]
            tier_y = tier_start_y + tier_num * NET_TIER_ROW_HEIGHT
            n_devices = len(tier_cats)
            usable_w = sw - NET_TIER_H_PAD * 2

            for i, cat in enumerate(tier_cats):
                if n_devices == 1:
                    icon_x = sx + (sw - icon_w) / 2
                else:
                    slot_w = usable_w / n_devices
                    icon_x = sx + NET_TIER_H_PAD + slot_w * i + (slot_w - icon_w) / 2

                category_name = cat['category']
                device_label = self._build_device_label(cat)
                tooltip = self._build_device_tooltip(cat)
                rating = cat.get('rating')

                node_dict = {
                    'id': str(node_id),
                    'label': device_label,
                    'x': int(icon_x), 'y': int(tier_y),
                    'width': icon_w,
                    'height': NET_ICON_HEIGHT,
                    'type': 'device',
                    'rating': rating,
                    'tooltip': tooltip,
                    'category': category_name,
                    'base_category': cat.get('base_category', category_name),
                }
                if force_refresh_colors:
                    node_dict['force_refresh_colors'] = True
                nodes.append(node_dict)

                # Use status-qualified key to avoid collisions between sections
                cat_lower = category_name.lower()
                qualified_key = f"{cat_lower}{status_suffix}"
                if qualified_key not in node_map:
                    node_map[qualified_key] = str(node_id)
                # Also register unqualified if not taken (for cross-section connections)
                if cat_lower not in node_map:
                    node_map[cat_lower] = str(node_id)

                conn = cat.get('connected_to', '').strip()
                if conn:
                    device_nodes.append((str(node_id), conn))

                node_id += 1

        return node_id

    def _render_site(self, site: Dict, sx: int, sy: int, sw: int,
                     nodes: list, edges: list, node_id: int) -> int:
        """Render one site with container, header, BFS-tiered devices, and connections."""
        site_type = site.get('site_type', 'branch')
        label = site.get('label', 'Site')
        categories = site.get('categories', [])

        current_cats, refresh_cats = self._partition_by_status(categories)
        has_dual = bool(current_cats) and bool(refresh_cats)

        container_h = self._calculate_site_height(categories, sw)
        site_header_h = 36

        # Site container
        nodes.append({
            'id': str(node_id),
            'label': '',
            'x': sx, 'y': sy,
            'width': sw, 'height': container_h,
            'type': 'site_container',
            'site_type': site_type,
        })
        node_id += 1

        # Site header bar
        type_badge = ' (DC)' if site_type == 'dc' else ''
        nodes.append({
            'id': str(node_id),
            'label': (label + type_badge).upper(),
            'x': sx, 'y': sy,
            'width': sw, 'height': site_header_h,
            'type': 'site_header',
            'site_type': site_type,
        })
        node_id += 1

        node_map: Dict[str, str] = {}
        device_nodes: List[tuple] = []
        tier_start_y = sy + site_header_h + NET_SITE_CONTAINER_PAD

        if current_cats:
            current_tiers = self._compute_tiers(current_cats)
            node_id = self._render_section(
                current_tiers, sx, tier_start_y, sw, nodes,
                node_id, node_map, device_nodes,
                force_refresh_colors=False, status_suffix='_current')
            num_current_tiers = max(len(current_tiers), 1)
            next_y = tier_start_y + num_current_tiers * NET_TIER_ROW_HEIGHT
        else:
            next_y = tier_start_y

        if has_dual:
            # Separator bar between current and refresh
            nodes.append({
                'id': str(node_id),
                'label': 'REFRESH / PLANNED',
                'x': sx + 10, 'y': int(next_y),
                'width': sw - 20, 'height': NET_SECTION_SEPARATOR_HEIGHT,
                'type': 'section_separator',
            })
            node_id += 1
            next_y += NET_SECTION_SEPARATOR_HEIGHT + 10

        if refresh_cats:
            refresh_tiers = self._compute_tiers(refresh_cats)
            node_id = self._render_section(
                refresh_tiers, sx, next_y, sw, nodes,
                node_id, node_map, device_nodes,
                force_refresh_colors=True, status_suffix='_refresh')

        # Draw connections (deduplicate bidirectional edges)
        drawn = set()
        for source_id, conn_str in device_nodes:
            targets = [t.strip() for t in conn_str.split(',') if t.strip()]
            for target_name in targets:
                target_id = self._find_target(target_name, node_map)
                if target_id and target_id != source_id:
                    edge_key = tuple(sorted([source_id, target_id]))
                    if edge_key not in drawn:
                        self._edge_counter += 1
                        edges.append({
                            'id': f"e{self._edge_counter}",
                            'source': source_id,
                            'target': target_id,
                        })
                        drawn.add(edge_key)

        return node_id

    @staticmethod
    def _find_target(target_name: str, node_map: Dict) -> Optional[str]:
        """Find target node ID by category name (case-insensitive).

        Skips status-qualified keys (_current, _refresh suffixes) during
        partial matching to avoid false matches.
        """
        target_lower = target_name.lower().strip()
        # Direct match first
        nid = node_map.get(target_lower)
        if nid:
            return nid
        # Partial match, skipping qualified keys and numbered-variant boundaries
        for cat_name, nid in node_map.items():
            # Skip status-qualified keys for partial matching
            if cat_name.endswith('_current') or cat_name.endswith('_refresh'):
                continue
            if target_lower in cat_name or cat_name in target_lower:
                if _shares_numbered_base(target_lower, cat_name):
                    continue
                return nid
        return None

    # ── helpers ───────────────────────────────────────────────────────────

    def _build_device_label(self, cat: Dict) -> str:
        name = cat['category']
        qty_model = cat.get('qty_model', '')
        eos = cat.get('end_of_support', '')
        parts = [
            f'<b>{name}</b>',
            f'<font style="font-size:9px">{qty_model}</font>',
        ]
        if eos:
            parts.append(f'<font style="font-size:8px;color:#888888">EoS: {eos}</font>')
        return '<br>'.join(parts)

    def _build_device_tooltip(self, cat: Dict) -> str:
        sections = []
        if cat.get('connected_to'):
            sections.append(f"Connected to: {cat['connected_to']}")
        if cat.get('end_of_support'):
            sections.append(f"End of Support: {cat['end_of_support']}")
        if cat.get('rating') is not None:
            sections.append(f"Rating: {cat['rating']}/5")
        if cat.get('notes'):
            sections.append(f"Notes: {cat['notes']}")
        return "\n".join(sections)

    # ── XML generation ────────────────────────────────────────────────────

    def _generate_diagram_xml(self, diagram_name: str, diagram_id: str,
                              nodes: List[Dict], edges: List[Dict],
                              canvas_w: int, canvas_h: int,
                              extra_cells: str = '') -> str:
        """Return a single <diagram>...</diagram> XML string (no mxfile wrapper).

        Args:
            extra_cells: Raw mxCell XML to inject (used by legend tab).
        """
        max_x = max((n['x'] + n['width'] for n in nodes), default=canvas_w) + 40
        max_y = max((n['y'] + n['height'] for n in nodes), default=canvas_h) + 40

        xml_parts = [
            f'  <diagram name="{diagram_name}" id="{diagram_id}">',
            f'    <mxGraphModel dx="{int(max_x)}" dy="{int(max_y)}" grid="1" '
            f'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            f'fold="1" page="1" pageScale="1" '
            f'pageWidth="{int(max_x + 100)}" pageHeight="{int(max_y + 100)}" '
            f'math="0" shadow="0">',
            '      <root>',
            '        <mxCell id="0"/>',
            '        <mxCell id="1" parent="0"/>',
        ]

        for node in nodes:
            xml_parts.append(self._node_to_xml(node))

        for edge in edges:
            xml_parts.append(self._edge_to_xml(edge))

        if extra_cells:
            xml_parts.append(extra_cells)

        xml_parts.append('      </root>')
        xml_parts.append('    </mxGraphModel>')
        xml_parts.append('  </diagram>')

        return '\n'.join(xml_parts)

    @staticmethod
    def _wrap_mxfile(*diagram_xmls: str) -> str:
        """Wrap one or more <diagram> XML strings in an mxfile envelope."""
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<mxfile host="app.diagrams.net" modified="2024-01-01T00:00:00.000Z" '
            'agent="SE Draw" version="22.1.0">',
        ]
        for d in diagram_xmls:
            parts.append(d)
        parts.append('</mxfile>')
        return '\n'.join(parts)

    # ── Legend / Specifications tab ────────────────────────────────────────

    def _generate_legend_diagram(self, customer_name: str,
                                 sites: List[Dict]) -> str:
        """Build a second diagram tab with structured reference tables."""
        W = 1400  # total content width
        ROW_H = 28
        HDR_H = 36
        SEC_GAP = 30
        PAD = 30
        y = PAD

        cells: List[str] = []
        cell_id = 100  # start IDs high to avoid collision

        def _esc(text):
            return html_mod.escape(str(text))

        hdr_style = (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#1a1a2e;strokeColor=#333366;"
            "fontColor=#e0e0ff;fontSize=13;fontStyle=1;"
            "align=left;verticalAlign=middle;spacingLeft=10;"
        )
        row_style_white = (
            "rounded=0;whiteSpace=wrap;html=1;"
            "fillColor=#ffffff;strokeColor=#cccccc;"
            "fontColor=#333333;fontSize=10;fontStyle=0;"
            "align=left;verticalAlign=middle;spacingLeft=10;"
        )
        row_style_gray = (
            "rounded=0;whiteSpace=wrap;html=1;"
            "fillColor=#f5f5f5;strokeColor=#cccccc;"
            "fontColor=#333333;fontSize=10;fontStyle=0;"
            "align=left;verticalAlign=middle;spacingLeft=10;"
        )

        def add_header(text):
            nonlocal y, cell_id
            cells.append(
                f'        <mxCell id="{cell_id}" value="{_esc(text)}" '
                f'style="{hdr_style}" vertex="1" parent="1">\n'
                f'          <mxGeometry x="{PAD}" y="{y}" width="{W}" '
                f'height="{HDR_H}" as="geometry"/>\n'
                f'        </mxCell>'
            )
            cell_id += 1
            y += HDR_H

        def add_row(text, idx=0):
            nonlocal y, cell_id
            style = row_style_gray if idx % 2 else row_style_white
            cells.append(
                f'        <mxCell id="{cell_id}" value="{_esc(text)}" '
                f'style="{style}" vertex="1" parent="1">\n'
                f'          <mxGeometry x="{PAD}" y="{y}" width="{W}" '
                f'height="{ROW_H}" as="geometry"/>\n'
                f'        </mxCell>'
            )
            cell_id += 1
            y += ROW_H

        def add_gap():
            nonlocal y
            y += SEC_GAP

        # ── Title ──
        title_style = (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#667eea;strokeColor=#5a67d8;"
            "fontColor=#ffffff;fontSize=16;fontStyle=1;"
            "align=center;verticalAlign=middle;"
        )
        cells.append(
            f'        <mxCell id="{cell_id}" value="{_esc(customer_name + " - Legend &amp; Specifications")}" '
            f'style="{title_style}" vertex="1" parent="1">\n'
            f'          <mxGeometry x="{PAD}" y="{y}" width="{W}" '
            f'height="50" as="geometry"/>\n'
            f'        </mxCell>'
        )
        cell_id += 1
        y += 50 + SEC_GAP

        # ── Section 1: WAN Connectivity Matrix ──
        add_header("WAN Connectivity Matrix")
        wan_rows = [
            "TC3 <-> TC5:  2x 10Gb Dark Fiber (MBO #1 / MBO #2, Tulsa Connect campus)",
            "DCs <-> Branches:  ATT ASEOD primary + DMVPN/Starlink secondary (Active/Active SD-WAN via Palo Alto)",
            "All branch traffic backhauled to TC3 (primary) or TC5 (failover)",
            "HQ (Johnstone):  ATT ASEOD primary + Cradlepoint LTE failover",
            "Branch failover:  Cradlepoint LTE (current) -> Starlink (refresh target)",
        ]
        for i, row in enumerate(wan_rows):
            add_row(row, i)
        add_gap()

        # ── Section 2: IP Addressing Scheme ──
        add_header("IP Addressing Scheme (Per-Site)")
        ip_rows = [
            "TC3 Primary DC:  Servers 10.57.0.0/16 + 10.103.0.0/16  |  FW Outside 67.214.103.130  |  DMZ VLAN 1300  |  DMVPN 10.255.255.30",
            "TC5 Secondary DR:  Servers 10.69.0.0/16 + 10.105.0.0/16  |  Internet 198.78.64.0/24  |  BGP 148.78.64.254",
            "Johnstone HQ:  Core 10.20.150.2/10.20.150.6  |  Router 10.20.150.1  |  IDF Mgmt 10.150.99.100-116",
            "LAW Main:  DMVPN 10.255.255.14  |  VLANs 1/5/10/89",
            "LAW South:  DMVPN 10.255.255.18  |  VLANs 1/5/10/90",
            "LAW West:  DMVPN 10.255.255.160  |  VLANs 5/10/70",
            "LAW Iowa:  DMVPN 10.255.255.161  |  VLANs 5/10/70",
            "LAW Campus:  DMVPN 10.255.255.22  |  VLANs 1/5/10/91",
            "Olathe (KC):  DMVPN 10.255.255.168  |  VLANs 5/10/70",
            "TX ConocoPhillips:  DMVPN 10.255.255.10  |  VLANs 1/5/10",
            "TX Philips 66:  DMVPN 10.255.255.34  |  VLANs 1/5/10/88",
            "WASO:  DMVPN 10.255.255.6  |  VLANs 1/5/10/70/85",
        ]
        for i, row in enumerate(ip_rows):
            add_row(row, i)
        add_gap()

        # ── Section 3: VLAN Reference ──
        add_header("VLAN Reference")
        vlan_rows = [
            "VLAN 1:   Data (default)  —  used at most branch sites",
            "VLAN 5:   PC / Workstation  —  standard across all sites",
            "VLAN 10:  Voice (VoIP / CUCM)  —  standard across all sites",
            "VLAN 70:  ITM / ATM machines  —  LAW West, Iowa, Olathe, WASO",
            "VLAN 85:  Cameras  —  WASO",
            "VLAN 88:  Cameras  —  TX Philips 66",
            "VLAN 89:  Cameras  —  LAW Main",
            "VLAN 90:  Cameras  —  LAW South",
            "VLAN 91:  Cameras  —  LAW Campus",
            "VLAN 1300: DMZ  —  TC3 Data Center",
        ]
        for i, row in enumerate(vlan_rows):
            add_row(row, i)
        add_gap()

        # ── Section 4: Security Stack ──
        add_header("Security Stack")
        sec_rows = [
            "Endpoint Protection:  Cortex XDR + Microsoft Defender",
            "Network Security:  Palo Alto PA-3410 (DC) + PA-440 (branch) + inline ThreatER IPS/IDS",
            "MDR:  Critical Start (managed detection & response)",
            "VPN:  Palo Alto GlobalProtect (remote access)",
            "IAM:  Microsoft Entra ID + Azure MFA (conditional access)",
            "Network Monitoring:  Auvik",
            "SIEM:  None currently deployed (planned)",
            "Backup:  Aikido (Aiku) air-gapped immutable appliances — no cloud backup",
        ]
        for i, row in enumerate(sec_rows):
            add_row(row, i)
        add_gap()

        # ── Section 5: Circuit Details ──
        add_header("Circuit Details (Per-Site)")
        circuit_rows = [
            "TC3 Primary DC:  ATT ASEOD (primary WAN) + 2x 10Gb dark fiber to TC5  |  Public IP 67.214.103.130",
            "TC5 Secondary DR:  ATT ASEOD + 2x 10Gb dark fiber to TC3  |  Public range 198.78.64.0/24",
            "Johnstone HQ:  ATT ASEOD (primary) + Cradlepoint LTE (failover)",
            "All Branches (current):  Cisco ISR 4351 DMVPN spoke + Cradlepoint LTE failover",
            "All Branches (refresh):  Palo Alto PA-440 SD-WAN + ATT ASEOD + Starlink Active/Active",
        ]
        for i, row in enumerate(circuit_rows):
            add_row(row, i)
        add_gap()

        # ── Section 6: Refresh Roadmap ──
        add_header("Refresh Roadmap (Current -> Future)")
        refresh_rows = [
            "DC Firewalls:  Palo Alto PA-850 (HA)  ->  Palo Alto PA-3410 (HA pair)",
            "DC Routers:  Cisco ISR 4331 (DMVPN)  ->  REMOVED (SD-WAN replaces DMVPN)",
            "HQ Routing:  Cisco Catalyst 9500 (L3 routing)  ->  L2 only; PA firewall handles ROAS",
            "HQ Wireless:  Legacy APs  ->  Juniper AP45/AP34 (Mist)",
            "Branch Router/FW:  Cisco ISR 4351 (ROAS)  ->  Palo Alto PA-440 (NGFW + SD-WAN)",
            "Branch Switching:  Meraki MS225/MS350  ->  Juniper EX4100-48MP (PoE++)",
            "Branch WAN:  Cradlepoint LTE (failover)  ->  ATT ASEOD + Starlink Active/Active",
            "Branch Wireless:  Mixed/Legacy  ->  Juniper AP34 (Mist standardized)",
            "Branch Power:  Varies  ->  Eaton 5PX UPS (standardized)",
            "Hypervisor:  VMware (fully exited)  ->  Nutanix AHV (complete)",
        ]
        for i, row in enumerate(refresh_rows):
            add_row(row, i)
        add_gap()

        # ── Section 7: Rating Legend ──
        add_header("Rating Color Legend")
        rating_legend = [
            "Rating 5 (Green):  Excellent — meets all current and future requirements",
            "Rating 4 (Light Green):  Good — minor improvements planned",
            "Rating 3 (Amber):  Adequate — refresh recommended within 12-18 months",
            "Rating 2 (Orange):  Below standard — active replacement in progress",
            "Rating 1 (Red):  Critical — immediate replacement required",
            "No Rating (Gray):  Not assessed",
        ]
        for i, row in enumerate(rating_legend):
            add_row(row, i)
        add_gap()

        # ── Section 8: Status Section Legend ──
        add_header("Status Section Legend (Dual-Row Layout)")
        status_rows = [
            "CURRENT section (top):  Devices currently deployed — colored by rating (green/amber/orange/red)",
            "REFRESH / PLANNED section (bottom):  Future replacement devices — shown in blue",
            "Separator bar:  Dashed gray bar labeled 'REFRESH / PLANNED' divides the two sections",
            "Sites with only CURRENT devices:  No separator bar shown, devices colored by rating",
            "Sites with only REFRESH devices:  All devices shown in blue, no separator bar",
        ]
        for i, row in enumerate(status_rows):
            add_row(row, i)

        # Build the diagram XML
        total_h = y + PAD
        total_w = W + PAD * 2

        return self._generate_diagram_xml(
            "Legend &amp; Specifications", "legendtab",
            [], [],  # no node/edge objects — we build cells directly
            total_w, total_h,
            extra_cells='\n'.join(cells),
        )

    def _node_to_xml(self, node: Dict) -> str:
        node_id = node['id']
        label = html_mod.escape(node['label'])
        x = int(node['x'])
        y = int(node['y'])
        width = int(node['width'])
        height = int(node['height'])
        node_type = node.get('type', 'device')
        tooltip = html_mod.escape(node.get('tooltip', ''))

        if node_type == 'title':
            style = (
                "rounded=1;whiteSpace=wrap;html=1;"
                "fillColor=#667eea;strokeColor=#5a67d8;"
                "fontColor=#ffffff;fontSize=16;fontStyle=1;"
                "align=center;verticalAlign=middle;"
            )
        elif node_type == 'site_container':
            site_type = node.get('site_type', 'branch')
            if site_type == 'dc':
                fill, stroke = '#f5f5f5', '#455a64'
            else:
                fill, stroke = '#fafafa', '#6d4c41'
            style = (
                f"rounded=1;whiteSpace=wrap;html=1;"
                f"fillColor={fill};strokeColor={stroke};"
                f"strokeWidth=2;arcSize=8;"
            )
        elif node_type == 'site_header':
            site_type = node.get('site_type', 'branch')
            sc = self.SITE_HEADER_COLORS.get(
                site_type, self.SITE_HEADER_COLORS['branch'])
            style = (
                f"rounded=1;whiteSpace=wrap;html=1;"
                f"fillColor={sc['fill']};strokeColor={sc['stroke']};"
                f"fontColor={sc['font']};fontSize=13;fontStyle=1;"
                f"align=center;verticalAlign=middle;"
            )
        elif node_type == 'section_separator':
            sc = SECTION_SEPARATOR_COLORS
            style = (
                f"rounded=0;whiteSpace=wrap;html=1;"
                f"fillColor={sc['fill']};strokeColor={sc['stroke']};"
                f"fontColor={sc['font']};fontSize=10;fontStyle=1;"
                f"align=center;verticalAlign=middle;"
                f"dashed=1;dashPattern=8 4;"
            )
        else:
            # Device node
            if node.get('force_refresh_colors'):
                colors = REFRESH_COLORS
            else:
                rating = node.get('rating')
                colors = RATING_COLORS.get(rating, RATING_COLORS[None])
            category = node.get('base_category', node.get('category', ''))
            icon_b64 = self._icon_cache.get(category, '')

            if icon_b64:
                style = (
                    f"shape=image;verticalLabelPosition=bottom;verticalAlign=top;"
                    f"imageAspect=0;aspect=fixed;html=1;"
                    f"image=data:image/svg+xml,{icon_b64};"
                    f"labelBackgroundColor={colors['fill']};"
                    f"fontSize=10;fontColor=#333333;"
                )
            else:
                style = (
                    f"rounded=1;whiteSpace=wrap;html=1;"
                    f"fillColor={colors['fill']};strokeColor={colors['stroke']};"
                    f"strokeWidth=2;"
                    f"fontColor={colors['font']};fontSize=11;"
                    f"align=center;verticalAlign=middle;"
                )

        tooltip_attr = f' tooltip="{tooltip}"' if tooltip else ''
        return (
            f'        <mxCell id="{node_id}" value="{label}" '
            f'style="{style}" vertex="1" parent="1"{tooltip_attr}>\n'
            f'          <mxGeometry x="{x}" y="{y}" width="{width}" '
            f'height="{height}" as="geometry"/>\n'
            f'        </mxCell>'
        )

    def _edge_to_xml(self, edge: Dict) -> str:
        edge_id = edge['id']
        source_id = edge['source']
        target_id = edge['target']
        stroke = NET_CONNECTION_COLORS['stroke']

        style = (
            f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
            f"jettySize=auto;html=1;strokeColor={stroke};"
            f"strokeWidth=1;endArrow=classic;endFill=1;"
        )

        return (
            f'        <mxCell id="{edge_id}" style="{style}" '
            f'edge="1" parent="1" source="{source_id}" target="{target_id}">\n'
            f'          <mxGeometry relative="1" as="geometry"/>\n'
            f'        </mxCell>'
        )
