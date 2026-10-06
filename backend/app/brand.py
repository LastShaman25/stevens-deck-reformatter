"""Locked Stevens brand + formatting constants for the Studio builder.

Single source of truth for the productized rules (mirrors slide_fixer.rules /
palette, plus the V1-locked additions the reviewer signed off on).
"""

# ---- official Stevens palette ----
# Locked to the TEMPLATE THEME (assets/stevens_template.pptx) so tool-generated
# slides match what PowerPoint auto-applies when content is pasted into the
# template. (Source of truth = the .pptx theme, not the older brand image:
# image said A32638/004380/000000; the shipped template uses these.)
RED = "A32537"         # theme accent1  (Stevens Red)
BLUE = "00427F"        # theme dk2      -> square/arrow bullets, subheads
MED_BLUE = "4895CF"    # theme accent2
GRAY = "7F7F7F"
DARK_GRAY = "363D45"   # theme dk1      (body "ink")
INK = DARK_GRAY        # standard body text color (charcoal, per template theme)
LIGHT_GRAY = "E3E5E6"  # theme lt2
LIGHT_BLUE = "E7F2FB"  # theme accent5
GOLD = "EBC73A"        # theme accent3
ORANGE = "E6832E"      # theme accent4
BLACK = "000000"
WHITE = "FFFFFF"

# Locked rule: standard TEXT may only be ink (charcoal), white, or Stevens Red.
# BLACK is still allowed for in-diagram label text ("box red, rest black").
ALLOWED_TEXT = {INK, BLACK, WHITE, RED}

FONT = "Arial"

# Type scale (points)
TITLE_PT = 40          # standard content title
TITLE_SECTION_PT = 44  # title-slide / section divider
SUBTITLE_PT = 32       # 32-36
SUBHEAD_PT = 28        # in-slide subhead differentiator
BODY_PT = 20           # 16-20 preferred
BODY_MIN_PT = 11       # dense fallback floor
BODY_STEP = 2

# Per-level bullet: (char, font, color)
BULLETS = {
    0: ("\u00a7", "Wingdings", BLUE),   # filled square
    1: ("\u00d8", "Wingdings", BLUE),   # arrow
    2: ("\u2013", "Arial", BLACK),      # dash
}

# Callout / text-box border
BOX_BORDER = RED
BOX_BORDER_PT = 1.0

# Dense-split triggers
SPLIT_BULLET_CAP = 9
SPLIT_WORD_CAP = 130

# Template layout names (in assets/stevens_template.pptx)
L_TITLE = "Title Slide"
L_TITLE_ONLY = "Title Only"
L_SECTION = "Section Header"
L_THANKYOU = "1_Title Slide"

EMU_PER_INCH = 914400


def in_to_emu(v):
    return int(round(v * EMU_PER_INCH))
