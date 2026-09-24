"""Official Stevens Institute brand palette (from brand guide section 2.3).

All values are the canonical HEX codes. Do NOT use the light colors as large
background fields (brand rule). Body text is pure black.
"""

# Primary brand colors
STEVENS_RED = "A32638"      # important/emphasis text, callout-box borders
STEVENS_GRAY = "7F7F7F"     # neutral labels / secondary text

# Secondary palette
DARK_GRAY = "363D45"        # strong headings / dark UI text
DARK_BLUE = "004380"        # "Stevens Blue" -> square bullets, strong headers
MEDIUM_BLUE = "4896CF"      # accent, links, highlights
MEDIUM_ORANGE = "E7842E"    # accent
MEDIUM_GOLD = "EBC73B"      # accent

# Light colors (panel/card fills only - never large backgrounds)
LIGHT_GRAY = "E4E5E6"
LIGHT_BLUE = "E7F2FB"
LIGHT_ORANGE = "FFF2E8"
LIGHT_GOLD = "FFFAE6"

# Neutrals used by rules
BLACK = "000000"            # all standard body text
WHITE = "FFFFFF"            # text on dark fills only

# Ordered list used to "snap" an off-palette color to the nearest Stevens color.
ALLOWED = [
    STEVENS_RED, STEVENS_GRAY, DARK_GRAY, DARK_BLUE, MEDIUM_BLUE,
    MEDIUM_ORANGE, MEDIUM_GOLD, LIGHT_GRAY, LIGHT_BLUE, LIGHT_ORANGE,
    LIGHT_GOLD, BLACK, WHITE,
]


def _rgb(hex6):
    return tuple(int(hex6[i:i + 2], 16) for i in (0, 2, 4))


def nearest_allowed(hex6):
    """Return the closest Stevens-allowed HEX to an arbitrary HEX (euclidean)."""
    hex6 = hex6.lstrip("#").upper()
    if len(hex6) != 6:
        return None
    r, g, b = _rgb(hex6)
    best, best_d = None, 1e18
    for c in ALLOWED:
        cr, cg, cb = _rgb(c)
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best_d:
            best, best_d = c, d
    return best
