#!/usr/bin/env python3
"""從 .pptx 抽出各頁文字、備忘稿與內嵌圖片。"""
import argparse
import posixpath
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def rels(z, part):
    d, n = posixpath.split(part)
    name = f"{d}/_rels/{n}.rels"
    if name not in z.namelist():
        return {}
    out = {}
    for r in ET.fromstring(z.read(name)):
        if r.get("TargetMode") == "External":
            continue
        t = r.get("Target")
        t = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join(d, t))
        out[r.get("Id")] = (r.get("Type").rsplit("/", 1)[-1], t)
    return out


def texts(z, part):
    lines = []
    for p in ET.fromstring(z.read(part)).iter(A + "p"):
        s = "".join(t.text or "" for t in p.iter(A + "t")).strip()
        if s:
            lines.append(s)
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pptx", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("slides"))
    args = ap.parse_args()
    if not zipfile.is_zipfile(args.pptx):
        sys.exit("不是有效的 .pptx（舊版 .ppt 請另存成 .pptx 或 PDF）")
    media = args.outdir / "media"
    media.mkdir(parents=True, exist_ok=True)
    md = []
    with zipfile.ZipFile(args.pptx) as z:
        pres = "ppt/presentation.xml"
        pr = rels(z, pres)
        ids = [s.get(R + "id") for s in ET.fromstring(z.read(pres)).iter(P + "sldId")]
        for n, rid in enumerate(ids, 1):
            part = pr[rid][1]
            md.append(f"## 第 {n} 頁")
            md += texts(z, part)
            for kind, target in rels(z, part).values():
                if kind == "image" and target in z.namelist():
                    name = posixpath.basename(target)
                    (media / name).write_bytes(z.read(target))
                    md.append(f"[圖片: media/{name}]")
                elif kind == "notesSlide":
                    notes = [t for t in texts(z, target) if not t.isdigit()]
                    if notes:
                        md.append("備忘稿：" + " ".join(notes))
            md.append("")
    (args.outdir / "slides.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(ids)} 頁 → {args.outdir / 'slides.md'}")


if __name__ == "__main__":
    main()
