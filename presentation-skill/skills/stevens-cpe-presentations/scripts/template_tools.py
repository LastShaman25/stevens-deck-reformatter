#!/usr/bin/env python3
"""Inspect OOXML templates or prepare a working PPTX; Python stdlib only."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
PRESENTATION = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
TEMPLATE = "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml"
EMU = 914400


def validate_package(package):
    names = package.namelist()
    if len(names) != len(set(names)):
        raise ValueError("Duplicate ZIP members are not supported.")
    # Bound decompression for uploaded files; no entries are extracted to disk.
    if sum(item.file_size for item in package.infolist()) > 512 * 1024 * 1024:
        raise ValueError("Package exceeds the helper's 512 MiB uncompressed limit.")
    for required in ("[Content_Types].xml", "ppt/presentation.xml"):
        if required not in names:
            raise ValueError("Missing OOXML part: " + required)
    root = ET.fromstring(package.read("[Content_Types].xml"))
    entries = [e for e in root.findall("ct:Override", NS)
               if e.get("PartName") == "/ppt/presentation.xml"]
    if len(entries) != 1 or entries[0].get("ContentType") not in (PRESENTATION, TEMPLATE):
        raise ValueError("Expected a non-macro PPTX or POTX presentation package.")
    return entries[0].get("ContentType")


def natural_key(name):
    return [int(piece) if piece.isdigit() else piece
            for piece in re.split(r"(\d+)", name)]


def inspect(source):
    with ZipFile(source) as package:
        content_type = validate_package(package)
        root = ET.fromstring(package.read("ppt/presentation.xml"))
        size = root.find("p:sldSz", NS)
        layouts = []
        for name in sorted(package.namelist(), key=natural_key):
            if not re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", name):
                continue
            layout = ET.fromstring(package.read(name))
            common = layout.find("p:cSld", NS)
            placeholders = []
            for shape in layout.findall(".//p:sp", NS):
                placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
                if placeholder is None:
                    continue
                row = dict(placeholder.attrib)
                off = shape.find("p:spPr/a:xfrm/a:off", NS)
                ext = shape.find("p:spPr/a:xfrm/a:ext", NS)
                if off is not None and ext is not None:
                    row["explicit_bounds_inches"] = {
                        key: round(int(element.get(attr)) / EMU, 5)
                        for key, element, attr in (("left", off, "x"), ("top", off, "y"),
                                                   ("width", ext, "cx"), ("height", ext, "cy"))
                    }
                row["sample_text"] = " ".join(t.text or "" for t in shape.findall(".//a:t", NS))
                placeholders.append(row)
            layouts.append({"part": name, "name": common.get("name", "") if common is not None else "",
                            "type": layout.get("type"), "placeholders": placeholders})
        themes = []
        for name in sorted(package.namelist(), key=natural_key):
            if re.fullmatch(r"ppt/theme/theme\d+\.xml", name):
                theme = ET.fromstring(package.read(name))
                colors = theme.find("a:themeElements/a:clrScheme", NS)
                themes.append({
                    "part": name,
                    "fonts": sorted({node.get("typeface") for node in theme.iter()
                                     if node.get("typeface")}),
                    "colors": {entry.tag.split("}")[-1]: [dict(child.attrib) for child in entry]
                               for entry in colors} if colors is not None else {},
                })
        return {
            "file": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "kind": "potx" if content_type == TEMPLATE else "pptx",
            "size_inches": {"width": round(int(size.get("cx")) / EMU, 5),
                            "height": round(int(size.get("cy")) / EMU, 5)} if size is not None else None,
            "slide_count": len(root.findall("p:sldIdLst/p:sldId", NS)),
            "master_count": len(root.findall("p:sldMasterIdLst/p:sldMasterId", NS)),
            "layouts": layouts,
            "themes": themes,
            "limitations": "Explicit XML inventory only; inherited geometry and rendered appearance are not evaluated.",
        }


def prepare(source, destination):
    if destination.suffix.lower() != ".pptx":
        raise ValueError("The working copy must have a .pptx extension.")
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("Choose a new output path; originals and existing files are never overwritten.")
    with ZipFile(source) as package:
        content_type = validate_package(package)
        manifest = package.read("[Content_Types].xml")
        if content_type == TEMPLATE:
            old, new = TEMPLATE.encode("ascii"), PRESENTATION.encode("ascii")
            if manifest.count(old) != 1:
                raise ValueError("Unexpected template manifest encoding; use an OOXML-capable editor.")
            manifest = manifest.replace(old, new, 1)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidentally replacing a user's output.
        with destination.open("xb") as output:
            try:
                if content_type == PRESENTATION:
                    with source.open("rb") as original:
                        shutil.copyfileobj(original, output)
                else:
                    with ZipFile(output, "w") as prepared:
                        prepared.comment = package.comment
                        for item in package.infolist():
                            blob = manifest if item.filename == "[Content_Types].xml" else package.read(item)
                            prepared.writestr(item, blob)
            except Exception:
                output.close()
                destination.unlink(missing_ok=True)
                raise
    return {"output": str(destination.resolve()), "kind": "pptx",
            "template_main_type_converted": content_type == TEMPLATE}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inspect", help="Print layout/theme inventory as JSON")
    inventory.add_argument("source", type=Path)
    copy = commands.add_parser("prepare", help="Create a new working PPTX without modifying the original")
    copy.add_argument("source", type=Path)
    copy.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.source) if args.command == "inspect" else prepare(args.source, args.destination)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (OSError, ValueError, BadZipFile, ET.ParseError, KeyError) as error:
        print("Template helper: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
