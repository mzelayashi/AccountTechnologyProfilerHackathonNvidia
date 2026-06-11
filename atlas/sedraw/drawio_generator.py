"""Draw.io Vision Board Diagram Generator.

Generates editable .drawio XML files showing current state and future state
technology architectures in a tiered column layout.
"""
import html as html_mod
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from atlas.sedraw.constants import (
    TIER_X_POSITIONS, TIER_LABELS, BOX_WIDTH, BOX_HEIGHT,
    VERTICAL_SPACING, TIER_HEADER_HEIGHT, TITLE_HEIGHT,
    PADDING_X, PADDING_Y, STATUS_COLORS, TIER_HEADER_COLORS,
    TITLE_COLORS, CONNECTION_COLORS,
)


class VisionBoardGenerator:
    """Generate Draw.io XML for Current State / Future State vision boards."""

    def generate(self, customer_name: str, diagram_title: str,
                 systems: List[Dict], data_flows: List[Dict],
                 output_path: Path) -> Path:
        """
        Generate a single .drawio file from structured data.

        Args:
            customer_name: Customer name (e.g., "Magnolia")
            diagram_title: Diagram title (e.g., "Current State")
            systems: List of system dicts from ExcelReader
            data_flows: List of flow dicts from ExcelReader
            output_path: Where to save the .drawio file

        Returns:
            Path to the generated file
        """
        # Layout nodes in tiered columns
        nodes, node_map = self._layout_nodes(systems, customer_name, diagram_title)

        # Resolve data flows to edges
        edges = self._resolve_edges(data_flows, node_map)

        # Generate XML
        full_title = f"{customer_name} - {diagram_title}"
        xml_content = self._generate_xml(full_title, nodes, edges)

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)

        return output_path

    def generate_combined(self, customer_name: str, states, output_path: Path) -> Path:
        """Stack multiple boards into ONE .drawio (first on top, others below).

        states: list of (title, systems, data_flows). Empty boards are skipped. Used by the Vision
        Studio to render Current State on top and Future State below it in a single file.
        """
        GAP = 140
        all_nodes, all_edges = [], []
        y_off, nid, eid = 0, 2, 1000
        for title, systems, flows in states:
            if not systems:
                continue
            nodes, node_map, nid, bottom = self._layout_nodes_ex(
                systems, customer_name, title, y_offset=y_off, start_id=nid)
            edges, eid = self._resolve_edges_ex(flows, node_map, start_id=eid)
            all_nodes += nodes
            all_edges += edges
            y_off = bottom + GAP
        xml_content = self._generate_xml(f"{customer_name} - Vision Board", all_nodes, all_edges)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xml_content, encoding='utf-8')
        return output_path

    # ------------------------------------------------------------------
    # Layout Engine
    # ------------------------------------------------------------------

    def _layout_nodes(self, systems: List[Dict], customer_name: str,
                      diagram_title: str) -> Tuple[List[Dict], Dict[str, str]]:
        """Back-compat wrapper: position nodes in tiered columns (single board)."""
        nodes, node_map, _next_id, _bottom = self._layout_nodes_ex(systems, customer_name, diagram_title)
        return nodes, node_map

    def _layout_nodes_ex(self, systems: List[Dict], customer_name: str, diagram_title: str,
                         y_offset: int = 0, start_id: int = 2):
        """Position nodes in tiered columns, offset vertically by `y_offset` and allocating ids
        from `start_id`. Returns (nodes, node_map, next_id, bottom_y) so several boards can be
        stacked into one diagram (see generate_combined)."""
        nodes = []
        node_map = {}  # system_name_lower -> node_id
        node_id = start_id

        # Group systems by tier
        tiers = {}
        for sys in systems:
            tier = sys.get('tier', 'source')
            tiers.setdefault(tier, []).append(sys)

        # Calculate vertical heights per tier for centering
        tier_heights = {}
        for tier, tier_systems in tiers.items():
            tier_heights[tier] = (
                TIER_HEADER_HEIGHT + 20 +  # header + gap
                len(tier_systems) * BOX_HEIGHT +
                (len(tier_systems) - 1) * (VERTICAL_SPACING - BOX_HEIGHT)
            )
        max_height = max(tier_heights.values()) if tier_heights else 300

        # Title node spanning the top of THIS board
        active_tiers = [t for t in TIER_X_POSITIONS if t in tiers]
        if active_tiers:
            min_x = min(TIER_X_POSITIONS[t] for t in active_tiers)
            max_x = max(TIER_X_POSITIONS[t] for t in active_tiers) + BOX_WIDTH
            title_width = max_x - min_x
        else:
            min_x = PADDING_X
            title_width = 600
        title_label = f"{customer_name}\\n{diagram_title}"
        nodes.append({
            'id': str(node_id), 'label': title_label,
            'x': min_x, 'y': y_offset + PADDING_Y - TITLE_HEIGHT - 20,
            'width': title_width, 'height': TITLE_HEIGHT,
            'type': 'title',
        })
        node_id += 1

        # Build tier columns
        for tier_key in ['source', 'integration', 'hub', 'consumer', 'ai']:
            if tier_key not in tiers:
                continue

            tier_systems = tiers[tier_key]
            x = TIER_X_POSITIONS[tier_key]

            # Center this tier vertically within this board's band
            this_height = tier_heights[tier_key]
            y_center = y_offset + PADDING_Y + (max_height - this_height) // 2

            # Tier header
            tier_label = TIER_LABELS.get(tier_key, tier_key.upper())
            nodes.append({
                'id': str(node_id), 'label': tier_label,
                'x': x, 'y': y_center,
                'width': BOX_WIDTH, 'height': TIER_HEADER_HEIGHT,
                'type': 'header',
            })
            node_id += 1
            y = y_center + TIER_HEADER_HEIGHT + 20

            # System nodes
            for sys in tier_systems:
                name = sys['system_name']
                vendor = sys.get('vendor', '')
                role = sys.get('role', '')
                status = sys.get('status', 'current')
                color_hint = sys.get('color_hint', '')
                notes = sys.get('notes', '')
                description = sys.get('description', '')
                use_cases = sys.get('use_cases', '')
                pain_points = sys.get('pain_points', '')

                # Build rich HTML label
                label = self._build_html_label(name, vendor, role, description, status)

                # Build rich tooltip from all detail fields
                tooltip = self._build_tooltip(description, use_cases, pain_points, notes)

                node = {
                    'id': str(node_id), 'label': label,
                    'x': x, 'y': y,
                    'width': BOX_WIDTH, 'height': BOX_HEIGHT,
                    'type': 'system', 'status': status,
                    'color_hint': color_hint, 'tooltip': tooltip,
                }
                nodes.append(node)
                node_map[name.lower()] = str(node_id)
                node_id += 1
                y += VERTICAL_SPACING

        bottom_y = max((n['y'] + n['height'] for n in nodes), default=y_offset + PADDING_Y)
        return nodes, node_map, node_id, bottom_y

    def _resolve_edges(self, data_flows: List[Dict],
                       node_map: Dict[str, str]) -> List[Dict]:
        """Back-compat wrapper."""
        edges, _next = self._resolve_edges_ex(data_flows, node_map)
        return edges

    def _resolve_edges_ex(self, data_flows: List[Dict], node_map: Dict[str, str],
                          start_id: int = 1000):
        """Match flow source/target names to node IDs; ids from start_id. Returns (edges, next_id)."""
        edges = []
        edge_id = start_id

        for flow in data_flows:
            source_name = flow.get('source', '').lower()
            target_name = flow.get('target', '').lower()
            label = flow.get('label', '')
            flow_type = flow.get('flow_type', 'data_feed')
            line_style = flow.get('line_style', 'solid')

            source_id = node_map.get(source_name)
            target_id = node_map.get(target_name)

            if source_id and target_id and source_id != target_id:
                edges.append({
                    'id': str(edge_id),
                    'source': source_id,
                    'target': target_id,
                    'label': label,
                    'flow_type': flow_type,
                    'line_style': line_style,
                })
                edge_id += 1

        return edges, edge_id

    # ------------------------------------------------------------------
    # XML Generation
    # ------------------------------------------------------------------

    def _generate_xml(self, diagram_name: str, nodes: List[Dict],
                      edges: List[Dict]) -> str:
        """Build complete Draw.io XML document."""
        # Calculate diagram bounds
        max_x = max((n['x'] + n['width'] for n in nodes), default=800) + PADDING_X
        max_y = max((n['y'] + n['height'] for n in nodes), default=600) + PADDING_Y

        xml_parts = []
        xml_parts.append('<?xml version="1.0" encoding="UTF-8"?>')
        xml_parts.append(
            f'<mxfile host="app.diagrams.net" modified="2024-01-01T00:00:00.000Z" '
            f'agent="SE Draw" version="22.1.0">')
        xml_parts.append(
            f'  <diagram name="{html_mod.escape(diagram_name)}" id="visionboard">')
        xml_parts.append(
            f'    <mxGraphModel dx="{int(max_x)}" dy="{int(max_y)}" grid="1" '
            f'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            f'fold="1" page="1" pageScale="1" '
            f'pageWidth="{int(max_x + 100)}" pageHeight="{int(max_y + 100)}" '
            f'math="0" shadow="0">')
        xml_parts.append('      <root>')
        xml_parts.append('        <mxCell id="0"/>')
        xml_parts.append('        <mxCell id="1" parent="0"/>')

        # Add nodes
        for node in nodes:
            xml_parts.append(self._node_to_xml(node))

        # Add edges
        for edge in edges:
            xml_parts.append(self._edge_to_xml(edge))

        xml_parts.append('      </root>')
        xml_parts.append('    </mxGraphModel>')
        xml_parts.append('  </diagram>')
        xml_parts.append('</mxfile>')

        return '\n'.join(xml_parts)

    def _node_to_xml(self, node: Dict) -> str:
        """Convert a node dict to Draw.io XML mxCell."""
        node_id = node['id']
        label = html_mod.escape(node['label'])
        x = int(node['x'])
        y = int(node['y'])
        width = int(node['width'])
        height = int(node['height'])
        node_type = node.get('type', 'system')
        tooltip = html_mod.escape(node.get('tooltip', ''))

        if node_type == 'title':
            colors = TITLE_COLORS
            style = (
                f"rounded=1;whiteSpace=wrap;html=1;"
                f"fillColor={colors['fill']};strokeColor={colors['stroke']};"
                f"fontColor={colors['font']};fontSize=16;fontStyle=1;"
                f"align=center;verticalAlign=middle;"
            )
        elif node_type == 'header':
            colors = TIER_HEADER_COLORS
            style = (
                f"rounded=1;whiteSpace=wrap;html=1;"
                f"fillColor={colors['fill']};strokeColor={colors['stroke']};"
                f"fontColor={colors['font']};fontSize=12;fontStyle=1;"
                f"align=center;verticalAlign=middle;"
            )
        else:
            # System node - use status colors or color_hint override
            status = node.get('status', 'current')
            color_hint = node.get('color_hint', '')

            if color_hint and self._valid_hex(color_hint):
                fill = color_hint
                stroke = self._darken_hex(color_hint, 0.3)
                font = self._contrast_font(color_hint)
            else:
                colors = STATUS_COLORS.get(status, STATUS_COLORS['current'])
                fill = colors['fill']
                stroke = colors['stroke']
                font = colors['font']

            style = (
                f"rounded=1;whiteSpace=wrap;html=1;"
                f"fillColor={fill};strokeColor={stroke};strokeWidth=2;"
                f"fontColor={font};fontSize=11;"
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
        """Convert an edge dict to Draw.io XML mxCell."""
        edge_id = edge['id']
        source_id = edge['source']
        target_id = edge['target']
        label = html_mod.escape(edge.get('label', ''))
        flow_type = edge.get('flow_type', 'data_feed')
        line_style = edge.get('line_style', 'solid')

        style = self._get_edge_style(flow_type, line_style)

        if label:
            return (
                f'        <mxCell id="{edge_id}" value="{label}" '
                f'style="{style}fontSize=9;fontColor={CONNECTION_COLORS["font"]};" '
                f'edge="1" parent="1" source="{source_id}" target="{target_id}">\n'
                f'          <mxGeometry relative="1" as="geometry"/>\n'
                f'        </mxCell>'
            )
        else:
            return (
                f'        <mxCell id="{edge_id}" style="{style}" '
                f'edge="1" parent="1" source="{source_id}" target="{target_id}">\n'
                f'          <mxGeometry relative="1" as="geometry"/>\n'
                f'        </mxCell>'
            )

    # ------------------------------------------------------------------
    # Label and Tooltip Builders
    # ------------------------------------------------------------------

    def _build_html_label(self, name: str, vendor: str, role: str,
                          description: str, status: str) -> str:
        """Build a rich HTML label for a system node.

        Format:
            <b>System Name</b>
            (Vendor)
            <i>Role</i>
            Description snippet...
        """
        parts = [f"<b>{name}</b>"]
        if vendor and vendor.lower() != name.lower():
            parts.append(f"({vendor})")
        if role:
            parts.append(f"<i>{role}</i>")
        if description:
            # Truncate to ~60 chars for the label; full text goes in tooltip
            snippet = description[:60] + "..." if len(description) > 63 else description
            parts.append(f'<font point-size="8">{snippet}</font>')
        return "<br>".join(parts)

    def _build_tooltip(self, description: str, use_cases: str,
                       pain_points: str, notes: str) -> str:
        """Build a rich tooltip string from all detail fields."""
        sections = []

        if description:
            sections.append(f"What it does: {description}")

        if use_cases:
            items = [u.strip() for u in use_cases.split('|') if u.strip()]
            if items:
                bullet_list = "\n".join(f"  - {item}" for item in items)
                sections.append(f"Use cases:\n{bullet_list}")

        if pain_points:
            items = [p.strip() for p in pain_points.split('|') if p.strip()]
            if items:
                bullet_list = "\n".join(f"  - {item}" for item in items)
                sections.append(f"Pain points:\n{bullet_list}")

        if notes:
            sections.append(f"Notes: {notes}")

        return "\n\n".join(sections)

    def _get_edge_style(self, flow_type: str, line_style: str) -> str:
        """Return draw.io style string based on flow_type and line_style."""
        base = (
            f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
            f"jettySize=auto;html=1;strokeColor={CONNECTION_COLORS['stroke']};"
        )

        # Flow type determines weight and arrow style
        if flow_type == 'etl':
            base += "strokeWidth=3;endArrow=block;endFill=1;"
        elif flow_type == 'sync':
            base += "strokeWidth=2;endArrow=classic;endFill=1;startArrow=classic;startFill=1;"
        elif flow_type == 'query':
            base += "strokeWidth=1;endArrow=classic;endFill=1;"
        elif flow_type == 'api':
            base += "strokeWidth=2;endArrow=classic;endFill=1;"
        elif flow_type == 'integration':
            base += "strokeWidth=1;endArrow=classic;endFill=1;"
        else:
            # data_feed default
            base += "strokeWidth=2;endArrow=classic;endFill=1;"

        # Line style overrides
        if line_style == 'dashed':
            base += "dashed=1;dashPattern=8 8;"
        elif line_style == 'dotted':
            base += "dashed=1;dashPattern=2 4;"

        return base

    # ------------------------------------------------------------------
    # Color Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _valid_hex(c: str) -> bool:
        """True only for a 6-digit hex color (optionally #-prefixed)."""
        s = (c or '').lstrip('#')
        if len(s) != 6:
            return False
        try:
            int(s, 16)
            return True
        except ValueError:
            return False

    @staticmethod
    def _darken_hex(hex_color: str, factor: float = 0.3) -> str:
        """Darken a hex color by a factor (0-1). Falls back safely on any bad input."""
        try:
            hex_color = hex_color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            r = int(r * (1 - factor))
            g = int(g * (1 - factor))
            b = int(b * (1 - factor))
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError, TypeError):
            return '#333366'

    @staticmethod
    def _contrast_font(hex_color: str) -> str:
        """Return dark or light font color based on background luminance (safe on bad input)."""
        try:
            hex_color = hex_color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            return '#1a1a2e' if luminance > 0.5 else '#ffffff'
        except (ValueError, IndexError, TypeError):
            return '#1a1a2e'
