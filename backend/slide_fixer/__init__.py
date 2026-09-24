"""Stevens Slide Fixer - automation engine that reformats PPTX decks to the
Stevens Template (colors, fonts, type scale, bullets, borders) with an optional
vision-model visual QA loop.
"""
from .rules import Rules, DEFAULT_RULES
from .engine import reformat

__all__ = ["Rules", "DEFAULT_RULES", "reformat"]
__version__ = "0.1.0"
