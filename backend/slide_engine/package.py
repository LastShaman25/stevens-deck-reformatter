"""Stable OOXML packaging, so retrying identical edits yields identical artifact IDs."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def save_deck(prs, path):
    raw=BytesIO()
    prs.save(raw)
    normalized=BytesIO()
    with ZipFile(raw) as source, ZipFile(normalized,'w',compression=ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            info=source.getinfo(name)
            info.date_time=(1980,1,1,0,0,0)
            target.writestr(info,source.read(name))
    Path(path).write_bytes(normalized.getvalue())
