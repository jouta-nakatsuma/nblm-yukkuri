NotebookLM-Yukkuri
=========

NotebookLM が生成した **ナレーション音声**をそのまま使い、**Notta の SRT** と **Rhubarb** のリップシンク、**MoviePy** の合成で「ゆっくり風」二人会話動画を作るツール群です。

- 🔉 音声: NotebookLM 出力の音声ファイル（例: `data/tts/mix.wav`）
- 📝 字幕: Notta で書き起こした SRT（例: `data/transcripts/final_std.srt`）
- 👄 口パク: Rhubarb が出力した viseme JSON（例: `data/lipsync/charA.json` / `charB.json`）
- 🖼️ 合成: MoviePy（PNG レイヤー合成＋字幕＋BGM/音声）

> 現状は **TTS を使わず**、NotebookLM の音声を信頼して字幕と口パクを当てる運用です。

---

## 1. 動作要件

- Python 3.11（推奨）
- FFmpeg（`ffmpeg` が PATH 上で実行できること）
- ImageMagick（`magick` または `convert` が PATH 上で実行できること）
- Rhubarb （リップシンク CLI。`rhubarb` が PATH 上で実行できること）
- pip パッケージ
  - `moviepy`, `pillow`, `srt`, `numpy`, `requests` （など）

### macOS のインストール例（Homebrew）

```bash
brew install ffmpeg imagemagick
# Rhubarb は配布バイナリを入手して PATH を通すか、ビルドしてください。
# 例: export PATH="/Users/you/opt/rhubarb/bin:$PATH"
````

### ImageMagick パスの指定（MoviePy の TextClip 用）

MoviePy の `TextClip` は ImageMagick を使います。環境変数でコマンドのパスを明示してください。

```bash
# magick コマンドがある場合
export IMAGEMAGICK_BINARY=$(command -v magick)
# convert コマンドしかない場合
# export IMAGEMAGICK_BINARY=$(command -v convert)
```

* * *

2\. セットアップ
----------

```bash
python -m venv .venv
source .venv/bin/activate  # Windows は .venv\Scripts\activate
pip install --upgrade pip
pip install moviepy pillow srt numpy requests
```

> **Pillow ≥ 10 での互換対策**は `nblm_auto/render.py` 冒頭で吸収済み（`Image.ANTIALIAS` の互換定義）。

* * *

3\. ディレクトリ構成
------------

```
nblm_yukkuri/
├─ nblm_auto/
│  ├─ main_dual.py
│  ├─ render.py
│  ├─ lipsync_rhubarb.py
│  ├─ speaker_segments.py
│  └─ …（他モジュール）
├─ assets/
│  └─ characters/
│     ├─ charA/
│     │  ├─ base.png
│     │  ├─ mouth_open.png
│     │  └─ mouth_closed.png
│     └─ charB/
│        ├─ base.png
│        ├─ mouth_open.png
│        └─ mouth_closed.png
├─ data/
│  ├─ tts/
│  │  └─ mix.wav      # NotebookLM の音声
│  ├─ lipsync/
│  │  ├─ charA.json   # Rhubarb 出力（A）
│  │  └─ charB.json   # Rhubarb 出力（B）
│  └─ transcripts/
│     └─ final_std.srt # Notta → 正規化した標準 SRT
└─ output.mp4
```

> **SRT の正規化**: Notta の「話者 1」「話者 2」などの前置きは SRT として非標準なので、下記のように削るのが安全です（例）。
> 
> ```bash
> perl -pe 's/^話者\s*\d+\s+(?=\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3})//' \
>   data/transcripts/final.srt > data/transcripts/final_std.srt
> ```

* * *

4\. クイックスタート
------------

すでに `data/tts/mix.wav`、`data/lipsync/charA.json`/`charB.json`、`data/transcripts/final_std.srt` がある前提。

```bash
python -m nblm_auto.main_dual \
  --stage render \
  --input data/tts/mix.wav \
  --charA assets/characters/charA \
  --charB assets/characters/charB \
  --transcript data/transcripts/final_std.srt \
  --out output.mp4
```

生成される `output.mp4` に、左右キャラ＋口パク＋字幕が合成されます。

* * *

5\. アセット仕様（最小）
--------------

*   `assets/characters/charA/base.png` … キャラ全身（透過 PNG 推奨）
*   `assets/characters/charA/mouth_open.png` … 開口差分（背景透明・同一基準位置）
*   `assets/characters/charA/mouth_closed.png` … 閉口差分（同上）
*   `charB` も同様

> 口 PNG は「口の部分だけ」を切り出した画像で OK。`render.py` で **口パーツの座標**と**スケール**を調整できます。

* * *

6\. レイアウトと口位置の調整
----------------

`nblm_auto/render.py` 冒頭の定数を編集:

```python
W, H = 1920, 1080   # 出力解像度
MARGIN = 40
CHAR_H = int(H * 0.82)
FPS = 30
```

キャラの配置・口位置は `render_two_chars_dual()` 内で調整します（該当コメント付き）。

*   **左右のベース位置**: `posA_base`, `posB_base`（もしくは `baseA.set_position`, `baseB.set_position` のロジック）
*   **口 PNG の位置とサイズ**: `mouth_clips_fast(char*_dir, timeline, pos_xy=?, mouth_h=?)`
    *   `pos_xy`: 口レイヤーの左上座標（画面座標）
    *   `mouth_h`: None で原寸、数値で高さ指定

**charB の口が見えない場合のチェック:**

1.  `assets/characters/charB/mouth_open.png` / `mouth_closed.png` の存在・透過
2.  `data/lipsync/charB.json` にセグメントが入っている（0 長秒ばかりでない）
3.  `mouth_clips_B` の `pos_xy` が画面内にあること（負値や右に寄りすぎていない）
4.  レイヤー順: `CompositeVideoClip([bg, baseA, *mouthA_clips, baseB, *mouthB_clips, ...])` の並び

* * *

7\. トラブルシューティング
---------------

### ❗ `OSError: MoviePy Error: creation of None failed ... 'unset'`（TextClip）

*   ImageMagick のパスを環境変数で指定:
    ```bash
    export IMAGEMAGICK_BINARY=$(command -v magick)  # または convert
    ```

### ❗ `AttributeError: PIL.Image has no attribute 'ANTIALIAS'`

*   Pillow ≥10 の仕様変更によるもの。`render.py` 冒頭で互換定義済み。パッケージのダウングレードは不要。

### ❗ `rhubarb: command not found`

*   PATH を通す:
    ```bash
    export PATH="/path/to/rhubarb/bin:$PATH"
    ```
*   `which rhubarb` で確認。`data/lipsync/*.json` が正しく生成できているか確認。

### ❗ `list object has no attribute 'end'`（CompositeVideoClip）

*   クリップ配列の中に **リストがネスト**されていると起きるので、`[*mouthA_clips, *mouthB_clips]` のように **アンパック**してフラット化。

* * *

8\. ライセンス / 謝辞
--------------

*   各依存ライブラリのライセンスに従います。NotebookLM, Notta, Rhubarb, MoviePy に感謝します。

````

---

# PROJECT_HANDOFF.md

```markdown
# PROJECT_HANDOFF — nblm_yukkuri（Codex 向け引き継ぎ）

## 目的
- NotebookLM が吐き出した高品質な **ナレーション音声**をそのまま使い、Notta の **高精度 SRT** を活用して **二人のキャラクターの口パク**と字幕をオーバーレイした動画を量産可能にする。
- 既存の TTS/話者分離に頼らず、収録済み音声 × SRT × Rhubarb のスリムな合成パイプラインを確立。

## 現状アーキテクチャ
````

NotebookLM audio (mix.wav)  
│  
├─► Rhubarb（手動/別コマンド） → data/lipsync/charA.json, charB.json  
│  
Notta SRT（final\_std.srt）  
│  
└─► nblm\_auto/main\_dual.py --stage render  
├─ lipsync\_rhubarb.py # JSON→タイムライン整形（open/close）  
├─ render.py # MoviePy 合成（ベースPNG＋口PNG＋字幕）  
└─ speaker\_segments.py # （将来）話者ごとの活性制御ユーティリティ

````

- **入力**: `data/tts/mix.wav`, `data/lipsync/charA.json`, `data/lipsync/charB.json`, `data/transcripts/final_std.srt`
- **アセット**: `assets/characters/charA|B/{base,mouth_open,mouth_closed}.png`
- **出力**: `output.mp4`

## 現状の使い方（再掲）
```bash
python -m nblm_auto.main_dual \
  --stage render \
  --input data/tts/mix.wav \
  --charA assets/characters/charA \
  --charB assets/characters/charB \
  --transcript data/transcripts/final_std.srt \
  --out output.mp4
````

既知の課題 / 改善ポイント
--------------

1.  **口位置・スケールの調整がコード埋め込み**
    *   キャラごとに PNG の切り抜き基準が異なるため、座標調整が必須。現状は `render.py` を直接編集。
2.  **charB の口が表示されないケース**
    *   パス/透明色/画面外座標/レイヤー順のいずれか。デバッグ支援が弱い。
3.  **Notta の「話者 N」情報の活用**（将来）
    *   セリフ区間と口活性（A/B）を連動させれば、自然な「交互発話」に近づく。
4.  **ビルド再現性**
    *   Pillow や ImageMagick のバージョン差で詰まりやすい。requirements/pin・環境チェックが必要。
5.  **パフォーマンス**
    *   長尺で MoviePy の合成が遅い。
        *   画像のキャッシュ化、`set_duration` の最適化、FFmpeg フィルタへの寄せなどで改善余地あり。
6.  **レイアウトのテンプレート化**
    *   解像度、余白、左右配置、字幕スタイルなどをプリセットで切り替えできるようにしたい。

実装フェーズ提案
--------

### Phase 1: 安定化と外部設定化（優先度高）

*    **キャラごとの外部設定**（YAML/JSON）
    *   `assets/characters/charA/config.yml`:
        ```yaml
        mouth:
          x: 520    # 画面座標 or base 左上からの相対座標（方式は統一）
          y: 580
          height: 120
        base:
          height: 820
          align: left   # left/right
          margin: 40
        ```
    *   `render.py` はこの設定を読み込んで配置。
*    **デバッグオーバーレイ**（開発時のみ）
    *   口の当たり判定（矩形）を半透明の `ColorClip` で重ねられるフラグ（`--debug-overlay`）。
*    **クリップ配列の安全化**
    *   `CompositeVideoClip([...])` に渡す要素を常に 1D に正規化するユーティリティ。

### Phase 2: 話者アクティベーションの導入

*    Notta SRT をパースして **話者1→A / 話者2→B** の **口活性ゲート**を作る（`speaker_segments.py` を活用）。
*    Rhubarb タイムラインに **話者ごとのミュート**を掛けて、非アクティブ話者は「閉口（または半開）」にする。

### Phase 3: テンプレート&CLI の拡張

*    `--template {side_by_side, stacked, picture_in_picture}` でレイアウト切替
*    `--subtitle-style` プリセット（フォント/縁取り/位置）
*    出力設定の外部化（解像度、fps、コーデック、preset、threads）

コード構成（主要ファイル）
-------------

*   `nblm_auto/main_dual.py`
    *   CLI 入口。`--stage render` 時に
        *   lipsync JSON → タイムライン化
        *   `render_two_chars_dual(...)` 呼び出し
*   `nblm_auto/lipsync_rhubarb.py`
    *   Rhubarb の JSON（`[{ "time": 0.12, "value": "A" }, ...]` 等）を open/close の timeline に変換
    *   出力: `[(t0, t1, is_open), ...]`
*   `nblm_auto/render.py`
    *   画像合成・字幕・音声をまとめて `CompositeVideoClip` で書き出し
    *   Pillow≥10 互換（`Image.ANTIALIAS`）対応済み
    *   ImageMagick（`TextClip`）使用
*   `nblm_auto/speaker_segments.py`
    *   Notta SRT の話者単位セグメントを抽象化（今後の Phase 2 で本格使用）

Dev 環境とチェックリスト
--------------

*    `python --version` が 3.11 系
*    `which ffmpeg`, `which magick`（or `convert`）, `which rhubarb`
*    `export IMAGEMAGICK_BINARY=$(command -v magick)` を設定
*    `pip freeze`（`moviepy`, `pillow`, `srt` が入っている）
*    `data/tts/mix.wav` が 1 チャンネル or 2 チャンネルでも OK（MoviePy 合成時に問題ないこと）
*    `data/lipsync/*.json` が **JSON 配列**である（先頭が `[` で始まる）

Issue 候補（そのまま起票可）
-----------------

*   feat: キャラごとの `config.yml` を読み込んで口位置/サイズ/左右配置を外部化
*   feat: `--debug-overlay` で口の当たり判定を描画
*   fix: `CompositeVideoClip` に渡すクリップ配列のフラット化ユーティリティ
*   feat: Notta SRT の話者情報を用いた口活性ゲート
*   chore: `requirements.txt` と `pip-tools` 導入、Pillow と MoviePy の相性ピン止め
*   perf: 画像クリップのキャッシュ、FFmpeg フィルタベースの最適化検討
*   docs: アセット作成ガイド（推奨キャンバス、口パーツの切り抜き手順）

簡易テスト計画
-------

*   **単体**: lipsync JSON → timeline 変換（境界条件: 0 長秒、オーバーラップ）
*   **結合**: ダミー PNG（ベース/口）＋短尺 WAV（5〜10秒）で `output.mp4` が生成されること
*   **目視**: 口 PNG の当たり判定（debug overlay）と viseme が概ね一致していること
*   **回帰**: ImageMagick の有無/指定パスで TextClip が失敗しないこと

* * *

参考メモ
----

*   Pillow≥10 の `Image.ANTIALIAS` 廃止 → `Image.Resampling.LANCZOS` に置換（`render.py` で吸収）
*   TextClip は ImageMagick 必須。環境変数 `IMAGEMAGICK_BINARY` で指定。
*   Rhubarb の進捗出力が JSON に混ざる問題は、`-o` ファイル出力を読み込む実装で回避済み。

```
