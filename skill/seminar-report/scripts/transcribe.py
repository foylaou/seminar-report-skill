#!/usr/bin/env python3
"""透過 LiteLLM 的 /v1/audio/transcriptions 將錄音轉成逐字稿。"""
import argparse
import array
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

from common import load_env

RATE = 16000
SEARCH_SEC = 20  # 在切點前這段範圍內找最安靜處，避免切在字中間
PROMPT = "以下是繁體中文的學術演講，內容夾雜英文專有名詞。"


def to_wav(src, dst):
    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
               "-vn", "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(dst)]
    elif shutil.which("afconvert"):
        cmd = ["afconvert", "-f", "WAVE", "-d", f"LEI16@{RATE}", "-c", "1", str(src), str(dst)]
    else:
        sys.exit("找不到 ffmpeg 或 afconvert，無法轉檔")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"轉檔失敗：{src}\n{r.stderr.strip()}\n（格式不支援時請安裝 ffmpeg）")


def quietest_cut(pcm):
    """回傳 pcm（int16 bytes）最後 SEARCH_SEC 秒內最安靜 0.2 秒的中點（byte 位置）。"""
    win = RATE // 5 * 2
    start = max(0, len(pcm) - SEARCH_SEC * RATE * 2)
    best, best_e = len(pcm), None
    for i in range(start, len(pcm) - win + 1, win):
        e = sum(map(abs, array.array("h", pcm[i:i + win])))
        if best_e is None or e < best_e:
            best, best_e = i + win // 2, e
    return best


def split_wav(path, chunk_sec, outdir):
    size = chunk_sec * RATE * 2
    chunks, buf, offset = [], b"", 0
    with wave.open(str(path), "rb") as w:
        while True:
            if len(buf) <= size:
                more = w.readframes((size - len(buf)) // 2 + 1)
                buf += more
                if more and len(buf) <= size:
                    continue
            if not buf:
                break
            cut = quietest_cut(buf[:size]) if len(buf) > size else len(buf)
            f = Path(outdir) / f"chunk{len(chunks):03d}.wav"
            with wave.open(str(f), "wb") as o:
                o.setnchannels(1)
                o.setsampwidth(2)
                o.setframerate(RATE)
                o.writeframes(buf[:cut])
            chunks.append((offset / (RATE * 2), f))
            offset += cut
            buf = buf[cut:]
    return chunks


def post(url, key, fields, file):
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n').encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file.name}"\r\n'
             "Content-Type: audio/wav\r\n\r\n").encode()
    body += file.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
               # 部分反向代理（如 Cloudflare）會擋 Python-urllib 預設值（error code 1010）
               "User-Agent": "seminar-report/1.0"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.load(r)["text"].strip()
        except urllib.error.HTTPError as e:
            msg = f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}"
            if e.code < 500 and e.code not in (408, 429):
                sys.exit(f"轉錄請求被拒絕 {msg}\n請檢查 LITELLM_API_KEY 與 WHISPER_MODEL")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            msg = str(e)
        except (ValueError, KeyError) as e:
            sys.exit(f"端點回應格式不符（缺少 text 欄位）：{e!r}\n請檢查 LITELLM_BASE_URL")
        if attempt < 3:
            print(f"  失敗，重試中：{msg}", file=sys.stderr)
            time.sleep(2 ** (attempt + 1))
    sys.exit(f"無法完成轉錄：{msg}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("audio", nargs="+", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("transcript.txt"))
    ap.add_argument("--chunk-minutes", type=int, default=10, help="每段分鐘數（10 分鐘約 19 MB）")
    args = ap.parse_args()
    if args.chunk_minutes < 1:
        ap.error("--chunk-minutes 至少為 1")

    load_env()
    base = os.environ.get("LITELLM_BASE_URL", "").rstrip("/")
    if not base:
        sys.exit("未設定 LITELLM_BASE_URL（請填寫專案根目錄的 .env）")
    url = base + ("" if base.endswith("/v1") else "/v1") + "/audio/transcriptions"
    key = os.environ.get("LITELLM_API_KEY", "")
    fields = {"model": os.environ.get("WHISPER_MODEL") or "whisper-1",
              "response_format": "json", "temperature": "0", "prompt": PROMPT}
    if lang := os.environ.get("WHISPER_LANGUAGE"):
        fields["language"] = lang

    for a in args.audio:
        if not a.is_file():
            sys.exit(f"找不到錄音檔：{a}")

    cache = args.output.parent / ".chunks"
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for audio in args.audio:
        print(f"處理 {audio.name}", flush=True)
        out.append(f"=== {audio.name} ===")
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "full.wav"
            to_wav(audio, wav)
            chunks = split_wav(wav, args.chunk_minutes * 60, tmp)
            if not chunks:
                sys.exit(f"錄音沒有內容：{audio}")
            for i, (start, f) in enumerate(chunks, 1):
                h = hashlib.sha256(f.read_bytes() + json.dumps(fields).encode()).hexdigest()
                hit = cache / f"{h}.txt"
                if hit.exists():
                    text = hit.read_text(encoding="utf-8")
                    print(f"  [{i}/{len(chunks)}] 使用快取", flush=True)
                else:
                    print(f"  [{i}/{len(chunks)}] 轉錄中…", flush=True)
                    text = post(url, key, fields, f)
                    hit.write_text(text, encoding="utf-8")
                m, s = divmod(int(start), 60)
                out.append(f"[{m:02d}:{s:02d}] {text}")

    args.output.write_text("\n\n".join(out) + "\n", encoding="utf-8")
    print(f"逐字稿：{args.output}（{sum(map(len, out))} 字元）")


if __name__ == "__main__":
    main()
