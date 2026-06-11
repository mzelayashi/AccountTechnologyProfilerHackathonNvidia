"""Layout/color/category constants for the SE Draw diagram engine (ported into ATLAS).

Pure constants only — no input/output path constants and no directory creation.
Per-customer input/output dirs live in the ATLAS vault (see atlas/sedraw/service.py).
`ICONS_DIR` (defined below) resolves to atlas/sedraw/icons/ where the 23 SVGs were copied.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

# Layout constants for Vision Board diagrams
TIER_X_POSITIONS = {
    'source': 80,
    'integration': 420,
    'hub': 760,
    'consumer': 1100,
    'ai': 1440,
}
TIER_LABELS = {
    'source': 'DATA SOURCES',
    'integration': 'INTEGRATION',
    'hub': 'DATA PLATFORM',
    'consumer': 'ANALYTICS & BI',
    'ai': 'AI / ML',
}
BOX_WIDTH = 260
BOX_HEIGHT = 90
VERTICAL_SPACING = 130
TIER_HEADER_HEIGHT = 40
TITLE_HEIGHT = 60
PADDING_X = 40
PADDING_Y = 100

# Status-based color scheme
STATUS_COLORS = {
    'current': {'fill': '#c8e6c9', 'stroke': '#2e7d32', 'font': '#1b5e20'},
    'retiring': {'fill': '#ffccbc', 'stroke': '#d84315', 'font': '#bf360c'},
    'new': {'fill': '#bbdefb', 'stroke': '#1565c0', 'font': '#0d47a1'},
    'planned': {'fill': '#e1bee7', 'stroke': '#7b1fa2', 'font': '#4a148c'},
}
TIER_HEADER_COLORS = {'fill': '#1a1a2e', 'stroke': '#333366', 'font': '#e0e0ff'}
TITLE_COLORS = {'fill': '#667eea', 'stroke': '#5a67d8', 'font': '#ffffff'}
CONNECTION_COLORS = {'stroke': '#666666', 'font': '#333333'}

# AI Configuration (shared with SE Account Map pattern)
AI_RETRY_ATTEMPTS = 3
AI_DELAY_BETWEEN_BATCHES = 1
AI_BATCH_SIZE = 10
API_AUTH_RETRY_ON_FAILURE = True

# Network Topology layout constants
NET_SITE_WIDTH = 520
NET_SITE_PADDING = 30
NET_SITE_GAP = 60
NET_GROUP_HEADER_HEIGHT = 30
NET_DEVICE_WIDTH = 460
NET_DEVICE_HEIGHT = 45
NET_DEVICE_SPACING = 120
NET_GROUP_GAP = 20
NET_TITLE_HEIGHT = 60

# Rating-based color scheme
RATING_COLORS = {
    5: {'fill': '#c8e6c9', 'stroke': '#2e7d32', 'font': '#1b5e20'},   # Green
    4: {'fill': '#dcedc8', 'stroke': '#558b2f', 'font': '#33691e'},   # Light green
    3: {'fill': '#fff9c4', 'stroke': '#f9a825', 'font': '#f57f17'},   # Amber
    2: {'fill': '#ffe0b2', 'stroke': '#ef6c00', 'font': '#e65100'},   # Orange
    1: {'fill': '#ffcdd2', 'stroke': '#c62828', 'font': '#b71c1c'},   # Red
    None: {'fill': '#e0e0e0', 'stroke': '#757575', 'font': '#424242'}, # Gray
}

# Category group definitions (23 categories)
NET_CATEGORY_GROUPS = {
    'storage': ['SAN Storage', 'HCI Storage', 'NAS', 'Backup', 'Object Storage'],
    'compute': ['Servers', 'Hypervisor', 'Blade Chassis'],
    'network': ['Firewalls', 'Core Switch', 'MDF Switch', 'IDF Switch',
                'Top of Rack Switch', 'Edge Switch', 'Campus Switch',
                'Router', 'SD-WAN', 'Load Balancer', 'WAN Optimizer',
                'Access Points', 'Wireless Controller'],
    'other': ['UPS / Power', 'Other Hardware/Appliances'],
}
NET_GROUP_LABELS = {
    'storage': 'STORAGE', 'compute': 'COMPUTE',
    'network': 'NETWORK', 'other': 'OTHER',
}
NET_CONNECTION_COLORS = {'stroke': '#999999', 'font': '#666666'}

# Flat ordered list of all 23 categories
NET_CATEGORIES = [
    cat for group in ['compute', 'network', 'storage', 'other']
    for cat in NET_CATEGORY_GROUPS[group]
]

# Grid layout constants for multi-site diagrams
NET_BRANCH_SITE_WIDTH = 340
NET_DC_COLUMNS = 2
NET_BRANCH_COLUMNS = 3
NET_ROW_GAP = 40

# BFS-tiered layout constants
NET_TIER_ROW_HEIGHT = 120     # Vertical spacing between tiers
NET_TIER_H_PAD = 20           # Horizontal padding within site container
NET_SITE_CONTAINER_PAD = 15   # Padding inside site container rectangle

# Icon configuration
ICONS_DIR = PROJECT_ROOT / "icons"

CATEGORY_ICON_MAP = {
    'SAN Storage':              'storage.svg',
    'HCI Storage':              'hci_storage.svg',
    'NAS':                      'storage.svg',
    'Backup':                   'backup.svg',
    'Object Storage':           'object_storage.svg',
    'Servers':                  'server.svg',
    'Hypervisor':               'hypervisor.svg',
    'Blade Chassis':            'blade_chassis.svg',
    'Firewalls':                'firewall.svg',
    'Core Switch':              'core_switch.svg',
    'MDF Switch':               'mdf_switch.svg',
    'IDF Switch':               'idf_switch.svg',
    'Top of Rack Switch':       'tor_switch.svg',
    'Edge Switch':              'switch.svg',
    'Campus Switch':            'campus_switch.svg',
    'Router':                   'router.svg',
    'SD-WAN':                   'sdwan.svg',
    'Load Balancer':            'load_balancer.svg',
    'WAN Optimizer':            'wan_optimizer.svg',
    'Access Points':            'access_point.svg',
    'Wireless Controller':      'wireless_controller.svg',
    'UPS / Power':              'ups.svg',
    'Other Hardware/Appliances': 'other_hardware.svg',
}

NET_ICON_WIDTH = 64
NET_ICON_HEIGHT = 45

# Dual-row current/refresh visual differentiation
REFRESH_COLORS = {'fill': '#bbdefb', 'stroke': '#1565c0', 'font': '#0d47a1'}
SECTION_SEPARATOR_COLORS = {'fill': '#90a4ae', 'stroke': '#607d8b', 'font': '#ffffff'}
NET_SECTION_SEPARATOR_HEIGHT = 24
