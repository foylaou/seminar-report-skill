#!/usr/bin/env python3
"""把 report.json 填入系上的空白心得報告表單。"""
import argparse
import datetime
import json
import os
import re
import struct
import sys
import zipfile
from pathlib import Path
from xml.dom import minidom

from common import load_env

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "blank_form.docx"
MAX_W, MAX_H = 5040000, 3780000  # 照片上限 14 × 10.5 cm（EMU）


def text_of(p):
    return "".join(t.firstChild.data for t in p.getElementsByTagName("w:t") if t.firstChild)


def set_text(doc, p, text):
    """以段落第一個 run 的格式重寫整段文字。"""
    runs = p.getElementsByTagName("w:r")
    if runs:
        rpr = runs[0].getElementsByTagName("w:rPr")
    else:
        rpr = p.getElementsByTagName("w:rPr")  # 空段落：用段落標記的格式
    rpr = rpr[0].cloneNode(True) if rpr else None
    for c in list(p.childNodes):
        if c.nodeName != "w:pPr":
            p.removeChild(c)
    r = doc.createElement("w:r")
    if rpr:
        r.appendChild(rpr)
    t = doc.createElement("w:t")
    t.setAttribute("xml:space", "preserve")
    t.appendChild(doc.createTextNode(re.sub(r"[\x00-\x1f]+", " ", text)))
    r.appendChild(t)
    p.appendChild(r)


def fill_body(doc, cell, heading, paragraphs):
    """在標題段落之後，以其下方的空白段落為樣板插入內文。"""
    ps = [c for c in cell.childNodes if c.nodeName == "w:p"]
    i = next(i for i, p in enumerate(ps) if text_of(p).startswith(heading))
    blank = ps[i + 1]
    for text in paragraphs:
        new = blank.cloneNode(True)
        set_text(doc, new, text.strip())
        cell.insertBefore(new, blank)
    cell.removeChild(blank)


def image_size(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i, rotated = 2, False
        while i + 9 < len(data):
            marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            seg = data[i + 4:i + 2 + length]
            if marker == 0xE1 and seg[:4] == b"Exif":
                tiff = seg[6:]
                e = "<" if tiff[:2] == b"II" else ">"
                off = struct.unpack(e + "I", tiff[4:8])[0]
                for k in range(struct.unpack(e + "H", tiff[off:off + 2])[0]):
                    ent = tiff[off + 2 + 12 * k:off + 14 + 12 * k]
                    if struct.unpack(e + "H", ent[:2])[0] == 0x0112:
                        rotated = struct.unpack(e + "H", ent[8:10])[0] > 1
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                if rotated:
                    sys.exit("照片帶有旋轉資訊，請先轉正（可用「預覽程式」旋轉後另存）")
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", (w, h)
            i += 2 + length
    sys.exit("照片只支援 jpg / png（HEIC 請先用 sips 轉檔）")


def photo_xml(n, cx, cy):
    return (
        '<w:p xmlns:w="w" xmlns:wp="wp" xmlns:r="r"><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
        f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:docPr id="{100 + n}" name="photo{n}"/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{100 + n}" name="photo{n}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="rIdPhoto{n}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("output"))
    ap.add_argument("--template", type=Path, default=TEMPLATE)
    ap.add_argument("--force", action="store_true", help="覆蓋同名檔案")
    ap.add_argument("--draft", action="store_true", help="允許日期、姓名、學號留白，產生草稿")
    args = ap.parse_args()

    load_env()
    data = json.loads(args.report.read_text(encoding="utf-8"))
    data.setdefault("student_name", "")
    data.setdefault("student_id", "")
    name = data["student_name"] or os.environ.get("STUDENT_NAME", "")
    sid = data["student_id"] or os.environ.get("STUDENT_ID", "")
    missing = [k for k in ("date", "speaker", "title", "summary", "reflection") if not data.get(k)]
    missing += [k for k, v in (("student_name", name), ("student_id", sid)) if not v]
    if args.draft:
        missing = [k for k in missing if k not in ("date", "student_name", "student_id")]
    if missing:
        sys.exit("缺少欄位：" + ", ".join(missing))
    for k in ("summary", "reflection"):
        if not isinstance(data[k], list):
            sys.exit(f"{k} 必須是段落字串的陣列")
    if data.get("date"):
        day = datetime.date.fromisoformat(data["date"])
        roc = day.year - 1911
        date_text, stamp = f"{roc}年{day.month}月{day.day}日", f"{roc}{day:%m%d}"
    else:
        date_text, stamp = "　　年　　月　　日", "_草稿"

    dest = args.outdir / f"心得報告{stamp}專題.docx"
    if dest.exists() and not args.force:
        sys.exit(f"檔案已存在：{dest}（要覆蓋請加 --force）")

    with zipfile.ZipFile(args.template) as z:
        parts = {i.filename: z.read(i) for i in z.infolist()}
    doc = minidom.parseString(parts["word/document.xml"])
    body = doc.getElementsByTagName("w:body")[0]

    def find(prefix):
        for p in doc.getElementsByTagName("w:p"):
            if text_of(p).startswith(prefix):
                return p
        sys.exit(f"表單中找不到「{prefix}」")

    set_text(doc, find("學生姓名"), f"學生姓名：{name}{' ' * 20}學號：{sid}")
    set_text(doc, find("演講日期"), f"演講日期：{date_text}")
    set_text(doc, find("演講人"), f"演講人：{data['speaker']}")
    set_text(doc, find("演講題目"), f"演講題目：{data['title']}")
    fill_body(doc, find("演講內容摘要").parentNode, "演講內容摘要", data["summary"])
    fill_body(doc, find("心得：").parentNode, "心得：", data["reflection"])

    new_rels, exts = "", set()
    sect = body.getElementsByTagName("w:sectPr")[-1]
    for n, photo in enumerate(data.get("photos") or [], 1):
        raw = Path(photo).read_bytes()
        ext, (w, h) = image_size(raw)
        scale = min(MAX_W / w, MAX_H / h)
        frag = minidom.parseString(photo_xml(n, int(w * scale), int(h * scale)))
        el = doc.importNode(frag.documentElement, True)
        for a in ("xmlns:w", "xmlns:wp", "xmlns:r"):
            el.removeAttribute(a)
        body.insertBefore(el, sect)
        parts[f"word/media/photo{n}.{ext}"] = raw
        exts.add(ext)
        new_rels += (f'<Relationship Id="rIdPhoto{n}" Type="http://schemas.openxmlformats.org/'
                     f'officeDocument/2006/relationships/image" Target="media/photo{n}.{ext}"/>')
    if new_rels:
        rel = "word/_rels/document.xml.rels"
        parts[rel] = parts[rel].replace(b"</Relationships>", new_rels.encode() + b"</Relationships>")
        ct = parts["[Content_Types].xml"]
        for ext in exts:
            if f'Extension="{ext}"'.encode() not in ct:
                mime = "image/png" if ext == "png" else "image/jpeg"
                ct = ct.replace(b"</Types>", f'<Default Extension="{ext}" ContentType="{mime}"/></Types>'.encode())
        parts["[Content_Types].xml"] = ct

    parts["word/document.xml"] = doc.toxml(encoding="UTF-8")
    args.outdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in parts.items():
            z.writestr(n, b)
    count = lambda k: sum(len(s) for s in data[k])
    print(f"已產生：{dest}\n摘要 {count('summary')} 字，心得 {count('reflection')} 字")


if __name__ == "__main__":
    main()
