"""Slide preview rendering.

LibreOffice or installed Windows PowerPoint -> PDF -> PNG via PyMuPDF.
The legacy schematic helper below is not used by the API or verification.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import json
from pathlib import Path
from threading import Lock

_RENDER_LOCK = Lock()
RENDER_TIMEOUT = int(os.environ.get("STEVENS_RENDER_TIMEOUT", "120"))

from PIL import Image, ImageDraw, ImageFont

_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
_LO_PROFILE = "file:///tmp/lo_profile_studio"

RED = (163, 38, 56)
BLUE = (0, 67, 128)
LIGHT_BLUE = (231, 242, 251)
GRAY = (150, 156, 163)
LIGHT = (228, 229, 230)
INK = (26, 29, 33)
WHITE = (255, 255, 255)

W, H = 640, 360  # 16:9 thumbnail


def find_soffice(explicit=None):
    for cand in (explicit, shutil.which("soffice"), shutil.which("libreoffice"), _MAC_SOFFICE, r"C:\Program Files\LibreOffice\program\soffice.exe"):
        if cand and os.path.exists(cand):
            return _soffice_cli(cand)
    return None


def _soffice_cli(executable):
    # Windows' GUI launcher is not the supported console/redirected-output entry point.
    path = Path(executable)
    console = path.with_suffix('.com')
    if path.name.lower() == 'soffice.exe' and console.is_file():
        return str(console)
    return str(path)


def _render_diagnostic(result):
    parts = [getattr(result, name, b'') or b'' for name in ('stdout', 'stderr')]
    text = ' '.join(p.decode('utf-8', errors='replace') if isinstance(p, bytes) else p for p in parts)
    return ' '.join(text.split())[:1200] or 'No diagnostic output.'


def _fitz():
    try:
        import fitz  # PyMuPDF
        return fitz
    except Exception:
        return None


def libreoffice_available():
    return find_soffice() is not None and _fitz() is not None


def renderer_info():
    executable = find_soffice()
    if executable:
        return {"name": "LibreOffice", "executable": executable}
    pp = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Microsoft Office/root/Office16/POWERPNT.EXE'
    if os.name == 'nt' and pp.exists():
        return {"name": "Microsoft PowerPoint", "executable": str(pp)}
    return None


def available():
    return renderer_info() is not None and _fitz() is not None


def pptx_to_pdf(pptx_path, out_dir, soffice=None):
    info = {"name": "LibreOffice", "executable": _soffice_cli(soffice)} if soffice else renderer_info()
    if not info:
        raise RuntimeError("No supported renderer found. Install LibreOffice or PowerPoint.")
    os.makedirs(out_dir, exist_ok=True)
    pdf = Path(out_dir).resolve() / (Path(pptx_path).stem + '.pdf')
    if pdf.exists():
        raise RuntimeError("Render destination must be fresh")
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with _RENDER_LOCK, tempfile.TemporaryDirectory(prefix='stevens-render-', dir=out_dir) as profile:
        if info['name'] == 'LibreOffice':
            lo_command = [info['executable'], '--headless', '--nologo', '--norestore',
                          '-env:UserInstallation=' + Path(profile).resolve().as_uri()]
            command = lo_command + ['--convert-to', 'pdf:impress_pdf_Export',
                                    '--outdir', str(Path(out_dir).resolve()), str(Path(pptx_path).resolve())]
        else:
            script = Path(__file__).with_name('powerpoint_render.ps1').read_text(encoding='utf-8')
            command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                       '& { ' + script + ' } -InputDeck $env:STEVENS_RENDER_INPUT -OutputPdf $env:STEVENS_RENDER_OUTPUT']
        environment={**os.environ,
                                    'STEVENS_RENDER_INPUT': str(Path(pptx_path).resolve()),
                                    'STEVENS_RENDER_OUTPUT': str(pdf)}
        try:
            result = subprocess.run(command, capture_output=True, timeout=RENDER_TIMEOUT,
                                    check=True, creationflags=flags, env=environment)
        except subprocess.TimeoutExpired as exc:
            if info['name'] == 'Microsoft PowerPoint':
                # Close only the task-owned deck path. Never terminate the user's Office process.
                cleanup = """try {
                  $app = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')
                  for ($i=$app.Presentations.Count; $i -ge 1; $i--) {
                    $deck=$app.Presentations.Item($i)
                    if ($deck.FullName -eq $env:STEVENS_RENDER_INPUT) { $deck.Close() }
                    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($deck)
                  }
                  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)
                } catch { }"""
                try:
                    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',cleanup],
                                   capture_output=True,timeout=10,creationflags=flags,env=environment)
                except (subprocess.TimeoutExpired,OSError):
                    pass
            raise RuntimeError(f"{info['name']} exceeded the {RENDER_TIMEOUT}s render timeout; verification did not complete.") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"{info['name']} could not render this file (exit {exc.returncode}); verification did not complete. "
                               + _render_diagnostic(exc)) from exc
        if not pdf.exists() or not pdf.stat().st_size:
            raise RuntimeError('Renderer did not create a PDF. ' + _render_diagnostic(result))
        if info['name'] == 'Microsoft PowerPoint':
            metadata = json.loads(result.stdout.decode('utf-8-sig').strip())
        else:
            # Reuse this completed job's private profile, never initialize the interactive default profile.
            try:
                version_result = subprocess.run(lo_command + ['--version'], capture_output=True,
                                                timeout=30, check=True, creationflags=flags, env=environment)
                version = version_result.stdout.decode('utf-8', errors='replace').strip()
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
                raise RuntimeError('LibreOffice version check did not complete; verification did not complete.') from exc
            if not version:
                raise RuntimeError('LibreOffice version check returned no version; verification did not complete.')
            metadata = {'renderer': info['name'], 'version': version}
        pdf.with_suffix('.renderer.json').write_text(json.dumps(metadata), encoding='utf-8')
    return str(pdf)


def render_to_pdf(pptx_path, pdf_out_path, soffice=None):
    """Render a deck to a specific PDF path (used for vision crops + before/after)."""
    with tempfile.TemporaryDirectory(dir=Path(pdf_out_path).resolve().parent) as tmp:
        pdf = pptx_to_pdf(pptx_path, tmp, soffice=soffice)
        shutil.copyfile(pdf, pdf_out_path)
        shutil.copyfile(Path(pdf).with_suffix(".renderer.json"), Path(pdf_out_path).with_suffix(".renderer.json"))
    return pdf_out_path


def rasterize_pdf(pdf_path, name_fn, dpi=120):
    """Rasterize each page of a PDF to PNG via PyMuPDF. name_fn(i)->path.
    Returns the written paths."""
    fitz = _fitz()
    if not fitz or not os.path.exists(pdf_path):
        raise RuntimeError("PyMuPDF unavailable or PDF missing")
    zoom = dpi / 72.0
    paths = []
    doc = fitz.open(pdf_path)
    for i in range(doc.page_count):
        path = name_fn(i)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        doc.load_page(i).get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(path)
        paths.append(path)
    doc.close()
    return paths


def render_deck(pptx_path, out_dir, name_fn=None, dpi=120, soffice=None):
    """Render every slide to a PNG. name_fn(i)->path names each 0-based slide;
    default writes out_dir/slide-<n>.png. Returns the list of written paths.
    Raises RuntimeError if LibreOffice/PyMuPDF are unavailable."""
    fitz = _fitz()
    if not fitz:
        raise RuntimeError("PyMuPDF (fitz) not available")
    os.makedirs(out_dir, exist_ok=True)
    zoom = dpi / 72.0
    paths = []
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        pdf = pptx_to_pdf(pptx_path, tmp, soffice=soffice)
        doc = fitz.open(pdf)
        for i in range(doc.page_count):
            path = name_fn(i) if name_fn else os.path.join(out_dir, f"slide-{i}.png")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            doc.load_page(i).get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(path)
            paths.append(path)
        doc.close()
    return paths


# --------------------------------------------------------------------------- #
# schematic fallback
# --------------------------------------------------------------------------- #
def _font(size, bold=False):
    candidates = [
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def schematic(meta, variant, path):
    """Draw a Stevens-styled thumbnail from an analyzed slide meta dict.
    variant: 'after' (rebuilt) or 'before' (original, shown as neutral clutter)."""
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, H - 1], outline=LIGHT, width=2)
    kind = meta.get("kind", "content")
    title = meta.get("title") or ""
    issues = set(meta.get("issues") or [])

    if variant == "before":
        d.rectangle([26, 22, 360, 40], fill=(201, 206, 211))
        y = 70
        for _ in range(6):
            d.rectangle([26, y, 610, y + 12], fill=(233, 235, 238))
            y += 26
        if "diagram" in issues:
            d.rectangle([430, 150, 610, 320], fill=(224, 226, 230))
        if "dense" in issues:
            d.rectangle([300, 300, 610, 330], outline=RED, width=2)
        return img.save(path)

    # ---- after (rebuilt Stevens) ----
    if kind in ("title", "thankyou"):
        d.rectangle([0, 0, W, H], fill=WHITE)
        d.rectangle([W - 210, 0, W, H], fill=RED)
        d.rectangle([70, 150, 250, 156], fill=RED)
        f = _font(30, True)
        for i, ln in enumerate(_wrap(d, title or ("Thank you!" if kind == "thankyou" else "Presentation"), f, 300)):
            d.text((70, 165 + i * 34), ln, font=f, fill=INK)
        return img.save(path)

    if kind == "section":
        d.rectangle([0, 150, W, 210], fill=LIGHT_BLUE)
        f = _font(26, True)
        d.text((40, 165), (title or "Section")[:40], font=f, fill=BLUE)
        return img.save(path)

    # content: black title on white, Stevens Red rule (headings are never blue)
    tf = _font(22, True)
    tline = _wrap(d, title, tf, W - 60)[:1]
    d.text((28, 22), tline[0] if tline else "", font=tf, fill=INK)
    d.rectangle([28, 56, min(W - 28, 28 + 240), 60], fill=RED)

    if "sparse" in issues:
        d.rectangle([90, 150, W - 90, 250], outline=RED, width=3)
        f = _font(20, True)
        d.text((120, 190), (title or "Key point")[:34], font=f, fill=INK)
        return img.save(path)

    has_img = "diagram" in issues
    body_right = W - 220 if has_img else W - 40
    bf = _font(16)
    y = 100
    n_lines = 4 if has_img else 6
    for i in range(n_lines):
        d.rectangle([34, y + 4, 46, y + 16], fill=BLUE)          # square bullet
        d.rectangle([56, y + 4, body_right, y + 16], fill=(58, 64, 72))
        y += 34
    if has_img:
        # vector "pyramid" motif
        cx = W - 110
        d.polygon([(cx, 120), (cx - 80, 300), (cx + 80, 300)], fill=BLUE)
        d.line([(cx - 53, 240), (cx + 53, 240)], fill=WHITE, width=2)
        d.line([(cx - 27, 180), (cx + 27, 180)], fill=WHITE, width=2)
    img.save(path)
