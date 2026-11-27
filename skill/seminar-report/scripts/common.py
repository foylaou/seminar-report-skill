import os
from pathlib import Path


def load_env():
    """讀取目前目錄或其上層的第一個 .env；已存在的環境變數優先。"""
    here = Path.cwd()
    for d in (here, *here.parents):
        f = d / ".env"
        if f.is_file():
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.removeprefix("export ").strip()
                v = v.strip()
                if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                os.environ.setdefault(k, v)
            return
