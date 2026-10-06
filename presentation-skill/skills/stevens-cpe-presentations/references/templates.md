# Bundled template guidance

These rules describe the bundled files only. A user-supplied template takes precedence when selected. Do not import brand rules from one template into another.

## Assets and working copies

| Choice | Asset relative to the skill root | Format |
| --- | --- | --- |
| Stevens | `assets/stevens_template.pptx` | PowerPoint presentation |
| CPE | `assets/CPE_template.potx` | PowerPoint template |

Both use a 16:9 canvas, approximately 13.3333 by 7.5 inches. Confirm dimensions in the actual asset. Preserve artwork directly from the chosen file; do not regenerate logos or institutional photographs.

Some editors require a PPTX instead of a POTX. Changing the filename alone is insufficient. The helper changes only the package's presentation main content type when preparing CPE, keeping all other package member contents unchanged.

From the skill root, with Python available:

```sh
python scripts/template_tools.py inspect assets/CPE_template.potx
python scripts/template_tools.py prepare assets/CPE_template.potx /work/cpe-working.pptx
```

Replace `/work/cpe-working.pptx` with a writable output path in the current environment. For Stevens or an uploaded PPTX, `prepare` copies the presentation without changing its bytes. The helper refuses to overwrite files. Its inventory reports explicit XML properties, not computed inherited formatting or visual fit; render the template to assess appearance.

## Stevens

| Role | Exact layout name | Visual identity |
| --- | --- | --- |
| Opening | `Title Slide` | Mostly burgundy/red, faint tower at left, white Stevens mark at top-right; no statue photograph |
| Content | `Title Only` or another suitable content layout | White interior with template footer artwork |
| Section | `Section Header` | Existing section artwork and text regions |
| Closing | `1_Title Slide` | Statue photograph at left and burgundy text area at right |

The closing layout has a misleading title-slide name. Do not swap it with the opening. The separate `Thank You Slide` uses balloon artwork and is not the intended default closing for this workflow. Use it only if the user specifically requests it.

Useful safe-region starting points for the bundled default layouts, in inches:

| Region | Left | Top | Width | Height |
| --- | ---: | ---: | ---: | ---: |
| Interior content | 0.70 | 0.40 | 11.70 | 6.05 |
| Opening title | 4.648 | 2.739 | 7.962 | 2.255 |
| Opening details | 5.114 | 5.021 | 7.496 | 1.664 |
| Closing title | 7.967 | 2.80 | 4.643 | 2.15 |
| Closing details | 7.75 | 5.021 | 4.86 | 1.664 |

These are placement regions, not required font sizes or instructions to fill every region. For other layouts, use their own placeholders and rendered geometry.

## CPE

| Role | Exact layout name | Visual identity |
| --- | --- | --- |
| Opening | `Title slide 1` | Dark slate, white text at left, full College of Professional Education / Stevens branding at right |
| Content | `1-line - 1 tect box` or another suitable content layout | White interior, CPE mark at bottom-right |
| Section | `Section break` | Light gray geometric artwork |
| Closing | `end slide` | White text at left, branded panel at right |

The word `tect` is the template's actual layout spelling. Additional layouts support subheads, two text columns, or text and an image. Inspect all masters when selecting layouts. Keep the footer clear; do not introduce Stevens red-tower or statue artwork into CPE.

| Region | Left | Top | Width | Height |
| --- | ---: | ---: | ---: | ---: |
| Interior content | 0.66 | 0.40 | 11.48 | 5.55 |
| Opening title | 0.73 | 3.05 | 7.84 | 2.25 |
| Opening details | 0.73 | 5.45 | 8.20 | 1.35 |
| Closing title | 0.73 | 0.53 | 7.84 | 1.61 |
| Closing details | 0.73 | 3.90 | 8.20 | 2.57 |

Clear unused sample labels such as `Presenter:` so they do not remain orphaned in the branding panel. Retain the actual institutional wordmarks.

## Geometry and text

All table rectangles are **left, top, width, height**, not corner coordinates. Right = left + width; bottom = top + height. For example, the Stevens interior bottom is 0.40 + 6.05 = 6.45 inches. PowerPoint uses 914,400 EMU per inch.

Preserve source meaning when adapting typography. Fit long titles with sensible wrapping, and check them against the actual artwork. Substitute fonts only when necessary and disclose substitutions that materially affect appearance. Rendered inspection overrides assumptions based solely on layout names or bounding boxes.
