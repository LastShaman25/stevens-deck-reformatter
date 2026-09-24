"""Slide -> PNG rendering for the visual QA loop.

Uses LibreOffice headless (`soffice`) to convert PPTX -> PDF, then pdftoppm /
pdf2image to rasterize pages. LibreOffice is not bundled; install it and either
put `soffice` on PATH or pass its path. Falls back with a clear error so the
re-skin engine still works without rendering.
"""
import os
import shutil
import subprocess
import tempfile

_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"


def find_soffice(explicit=None):
    for cand in (explicit, shutil.which("soffice"), shutil.which("libreoffice"), _MAC_SOFFICE):
        if cand and os.path.exists(cand):
            return cand
    return None


def render_slides(pptx_path, out_dir, dpi=120, soffice=None):
    """Render every slide to out_dir/slide-<n>.png. Returns list of paths."""
    soffice = find_soffice(soffice)
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install it (e.g. `brew install --cask libreoffice`) "
            "to enable slide rendering / visual QA."
        )
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, pptx_path],
            check=True, capture_output=True,
        )
        pdf = os.path.join(tmp, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
        if not os.path.exists(pdf):
            raise RuntimeError("PDF conversion failed.")
        prefix = os.path.join(out_dir, "slide")
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), pdf, prefix],
            check=True, capture_output=True,
        )
    pngs = sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".png")
    )
    return pngs
