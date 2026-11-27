# 專題研討心得報告產生器

這是一個 [Claude Code](https://claude.com/claude-code) skill。給它演講錄音、簡報和照片，它會轉出逐字稿、撰寫演講摘要與心得，並填入系上的 Word 表單。

```
錄音檔 ──► LiteLLM Whisper ──► 逐字稿 ─┐
簡報 / 照片 ───────────────────────────┼─► 摘要與心得 ──► 心得報告 .docx
你的背景與想法 (profile.md、Claude 記憶) ┘
```

## 需求

- Claude Code
- Python 3.9 以上（只用標準函式庫，不需 `pip install`）
- 轉錄音檔需要一個提供 `/v1/audio/transcriptions` 的端點（Whisper 模型）：自架 [LiteLLM](https://docs.litellm.ai/) 或直接使用 [OpenAI API](#直接使用-openai)
- 音檔轉檔工具：macOS 內建 `afconvert`；其他系統或遇到不支援的格式請安裝 `ffmpeg`
- 開發與測試環境為 macOS，Windows / Linux 未測試

## 第一次設定

1. 複製範例設定檔：

   ```bash
   cp -n .env.example .env
   ```

2. 打開 `.env` 填寫：

   | 變數 | 說明 |
   |---|---|
   | `LITELLM_BASE_URL` | LiteLLM 或 OpenAI 位址，結尾有沒有 `/v1` 都可以 |
   | `LITELLM_API_KEY` | 該端點的 API 金鑰 |
   | `WHISPER_MODEL` | LiteLLM 設定中的 `model_name`；OpenAI 填 `whisper-1` |
   | `WHISPER_LANGUAGE` | 錄音語言，預設 `zh`；留空自動偵測 |
   | `STUDENT_NAME` | 你的姓名 |
   | `STUDENT_ID` | 你的學號 |

3. （建議）建立 `profile.md`，用幾句話寫下研究方向、工作背景和寫作語氣，心得會更像你自己寫的。

### 直接使用 OpenAI

沒有架 LiteLLM 也可以直接連 OpenAI，程式不用改。`.env` 這樣填（變數名稱雖然是 `LITELLM_` 開頭，一樣適用）：

```ini
LITELLM_BASE_URL=https://api.openai.com/v1
LITELLM_API_KEY=你的 OpenAI API 金鑰
WHISPER_MODEL=whisper-1
WHISPER_LANGUAGE=zh
```

- ChatGPT Plus / Pro 訂閱不包含 API 用量，需到 [OpenAI API 平台](https://platform.openai.com/) 建立金鑰並設定付款。
- 依錄音長度計費，價格以[官方定價頁](https://openai.com/api/pricing/)為準。
- OpenAI 單次上傳上限 25 MB。預設每 10 分鐘切一段（約 19 MB），`--chunk-minutes` 不要設到 13 以上。
- 建議用 `whisper-1`；其他轉錄模型未測試。
- 錄音會傳到 OpenAI。
- 此設定方式依 API 相容性撰寫，尚未用 OpenAI 金鑰實測。

### 使用 LiteLLM

LiteLLM 端的模型設定範例（寫在 LiteLLM 的 `config.yaml`，以 OpenAI Whisper 為例，自架模型請依實際情況調整）：

```yaml
model_list:
  - model_name: whisper-1
    litellm_params:
      model: openai/whisper-1
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      mode: audio_transcription
```

## 使用方式

1. 每場演講在 `record/` 開一個資料夾，放入素材：

   ```
   record/1151030/
   ├── 錄音.m4a      # 可多個，檔名依錄製順序排列
   ├── 簡報.pptx     # 選填，.pptx 或 .pdf
   └── 照片.jpg      # 選填，jpg / png / heic
   ```

2. 在專案根目錄啟動 `claude`，輸入：

   ```
   /seminar-report record/1151030
   ```

3. 成品在 `output/`，檔名如 `心得報告1151030專題.docx`。

也可以：

- **已經有逐字稿或筆記**：直接貼到對話裡，會跳過轉錄。
- **補充自己的想法**：例如「心得重點放在我想把這個方法用在量測系統上」。
- **資料還不齊**：請它先出草稿，日期、姓名、學號會留白。
- **附照片到報告**：預設照片只用來辨識講者與題目，需要附在報告中請直接說。

## 交出前請檢查

- 人名、專有名詞和數值（語音辨識容易聽錯）。
- 心得中提到的個人經驗是否屬實、是否適合讓老師看到。
- 心得是以你的名義寫的，請讀過並改成自己的想法，也請遵守課程對使用 AI 的規定。

## 隱私

- 錄音會傳到你設定的轉錄端點（及其背後的模型服務）；逐字稿、簡報、照片與記憶內容會由 Claude 處理。錄音前請取得講者或主辦單位同意。
- 撰寫心得時會讀取本機 Claude Code 記憶（`~/.claude/`）中與背景相關的內容。skill 指示不得寫入金鑰、客戶名稱等敏感資訊，但仍請自行確認成品。
- 分享本專案前，不要包含 `.env`、`profile.md`、`record/`、`work/`、`output/`，以及含真實姓名學號的 `example_result/`。`.gitignore` 已排除這些項目（只對 git 有效，手動壓縮時要自己移除）。
- `skill/seminar-report/references/example.md` 是虛構範例；如果換成真實報告，分享前請取得作者同意並去識別化。
- Word 檔可能帶有作者名稱與組織標籤等檔案資訊，更換表單後分享前請檢查。

## 更換表單（新學期）

表單抬頭（例如 `115-1專題研討(一)`）固定在 `skill/seminar-report/assets/blank_form.docx`，換學期時用新的空白表單覆蓋它。新表單需保留「學生姓名、演講日期、演講人、演講題目、演講內容摘要、心得：」這些欄位文字，且「演講內容摘要」與「心得：」下方各留一個空白行。

## 專案結構

```
.
├── .env.example                 # 範例設定
├── .claude/skills/seminar-report -> ../../skill/seminar-report
├── blank_form/                  # 原始空白表單
├── skill/seminar-report/
│   ├── SKILL.md                 # Claude 執行流程
│   ├── scripts/
│   │   ├── transcribe.py        # 錄音 → 逐字稿
│   │   ├── extract_slides.py    # .pptx → 文字與圖片
│   │   └── fill_report.py       # report.json → Word
│   ├── assets/blank_form.docx
│   └── references/example.md
├── record/                      # 演講素材
├── work/                        # 中間產物
└── output/                      # 成品
```

`.claude/skills/seminar-report` 是符號連結。如果複製專案後找不到 `/seminar-report`，重新建立：

```bash
mkdir -p .claude/skills && ln -sn ../../skill/seminar-report .claude/skills/seminar-report
```

## 常見問題

| 狀況 | 處理 |
|---|---|
| `未設定 LITELLM_BASE_URL` | 確認專案根目錄有 `.env`，並在專案目錄內執行 |
| HTTP 401 | 檢查 `LITELLM_API_KEY` |
| HTTP 400 / 404 | 檢查 `WHISPER_MODEL` 與 `LITELLM_BASE_URL` |
| HTTP 403 `error code: 1010` | 反向代理（如 Cloudflare）擋下請求，調整其安全規則 |
| SSL 憑證錯誤（macOS） | 執行 Python 安裝資料夾中的 `Install Certificates.command` |
| 轉檔失敗 | 安裝 `ffmpeg` |
| `檔案已存在` | 先改名舊檔，或請 Claude 覆蓋 |
| 舊版 `.ppt` | 另存成 `.pptx` 或 PDF |
