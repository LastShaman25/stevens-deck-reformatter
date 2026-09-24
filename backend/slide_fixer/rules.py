"""Stevens formatting rules (the locked rulebook, as data).

Everything the engine does is driven by this config so it can later be edited
from the UI without touching engine code.
"""
from dataclasses import dataclass, field
from . import palette


@dataclass
class Rules:
    # Fonts
    body_font: str = "Arial"
    code_font: str = "Consolas"

    # Type scale (points)
    title_content_pt: int = 40      # standard slide title
    title_section_pt: int = 44      # section / title-slide divider (44-48)
    subtitle_pt: int = 34           # 32-36
    body_pt: int = 18               # 16-20 preferred
    body_min_pt: int = 11           # fall back to 11-16 when dense
    body_max_pt: int = 20

    # Colors (HEX, no '#')
    text_color: str = palette.BLACK
    emphasis_color: str = palette.STEVENS_RED
    bullet_color: str = palette.DARK_BLUE
    box_border_color: str = palette.STEVENS_RED
    box_border_pt: float = 1.0

    # Bullets
    bullet_char: str = "\u00a7"     # renders as a filled square in Wingdings
    bullet_font: str = "Wingdings"

    # Behavior toggles
    retint_theme: bool = True       # rewrite theme color/font scheme to Stevens
    normalize_fonts: bool = True    # force Arial on every run
    force_black_text: bool = True   # all standard text -> black
    auto_emphasis: bool = True      # bold body runs -> Stevens Red
    shrink_to_fit: bool = True      # enable "shrink text on overflow" on body
    add_box_borders: bool = True    # 1pt red border on standalone text boxes
    square_bullets: bool = True     # convert bullets to dark-blue squares
    snap_colors: bool = True        # snap off-palette run colors to nearest Stevens

    # Dense-slide split trigger
    split_word_cap: int = 120       # backstop word count per slide body
    split_bullet_cap: int = 8       # backstop bullet count per slide body

    # Theme color-scheme mapping (slot -> HEX) used when retint_theme is on
    theme_scheme: dict = field(default_factory=lambda: {
        "dk1": palette.BLACK,
        "lt1": palette.WHITE,
        "dk2": palette.DARK_BLUE,
        "lt2": palette.LIGHT_GRAY,
        "accent1": palette.STEVENS_RED,
        "accent2": palette.MEDIUM_BLUE,
        "accent3": palette.MEDIUM_GOLD,
        "accent4": palette.MEDIUM_ORANGE,
        "accent5": palette.STEVENS_GRAY,
        "accent6": palette.DARK_GRAY,
        "hlink": palette.MEDIUM_BLUE,
        "folHlink": palette.STEVENS_RED,
    })


DEFAULT_RULES = Rules()
