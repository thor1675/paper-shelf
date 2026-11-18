# paper-shelf

arXiv の論文を登録して、タグ・読書ステータス・メモで整理する個人用の Web アプリです。PBL（2026 年度 秋学期）で作っています。

PDF 本文は扱わず、arXiv API から取れるメタデータ（タイトル・著者・abstract・公開日）だけを保存します。

## できること

- **登録**：arXiv の ID か URL を貼ると、タイトルなどを arXiv から取ってきて保存する（`1706.03762`、`https://arxiv.org/abs/1706.03762v7`、`arXiv:1706.03762` などどれでも可）
- **まとめて登録**：ID や URL を 1 行に 1 件で 50 件まで貼ると、arXiv への 1 回の問い合わせでまとめて登録し、1 件ずつ結果を出す
- **arXiv 検索**（`/search`）：キーワードで arXiv を検索し、結果からそのまま登録する。登録済みのものは分かるように表示する
- **BibTeX 書き出し**：一覧の今の絞り込み条件のまま `.bib` をダウンロードする（キーは `vaswani2017attention` の形）
- **新着**（`/watches`）：キーワードを登録しておくと、毎朝 9 時に arXiv の新着を Slack に知らせる。画面の「新着を見る」でいつでも確かめられる
- **一覧と絞り込み**：タグ（複数選ぶと AND）・読書ステータス・タイトルと abstract のキーワード・著者名（部分一致）で絞り込み、並べ替える。条件は URL に入るので、ブックマークできる
- **詳細と編集**：タグ・ステータス・メモを編集する。メモは Markdown（表・チェックリスト・数式 `$...$`）で書け、チェックボックスはその場で押せる
- **引用の図**（`/citations`）：1 本を中心に、左に参考文献、右に引用している論文を並べる。円を押すとその論文を中心にした図に移り、次々にたどれる。登録していない論文でも見られる
- **似ている論文**：詳細画面の下に出る
- **日本語で読む**：arXiv の HTML 版を、この PC の翻訳モデル（Hugging Face の FuguMT）で訳す。見出し・数式・図・表・参考文献の構造はそのままで、段落ごとに「原文」も見られる。**訳文は自分で読むためだけに使い、公開や共有はしない**（私的使用の範囲）
- **被引用数**：一覧のカードに出し、被引用の多い順にも並べられる
- **一覧でまとめて操作**：チェックを付けた論文に、まとめてタグを付け外しする・状態を変える・削除する
- **タグの管理**（`/tags`）：名前を変える、既にある名前にして 2 つを 1 つにまとめる、全部の論文から外す
- **図で見る**（`/insights`）：公開年ごとの本数、タグのつながり、共著者のつながり、登録した論文どうしの引用、よく引用されているのに未登録の論文、月ごとに読んだ本数
- **Slack 連携**（任意）：ボットを招待したチャンネルに arXiv のリンクを貼ると自動で保存し、投稿文をメモに残す。新着の投稿には「保存」ボタンが付く

## 構成

```
paper-shelf/
├── docker-compose.yml   4 つのコンテナの設定
├── frontend/            Next.js 16（App Router / TypeScript / Tailwind）
├── backend/             FastAPI + SQLModel + Alembic
│   ├── main.py          API
│   ├── models.py        テーブルと入出力の形
│   ├── arxiv.py         arXiv API からの取得と検索
│   ├── bibtex.py        BibTeX の書き出し
│   ├── scholar.py       OpenAlex（引用関係）とのやり取り
│   ├── citations.py     引用の図・同期・登録した論文どうしの引用の API
│   ├── migrations/      テーブルの変更履歴
│   └── tests/           pytest
├── translator/          英→日の翻訳（FuguMT を CTranslate2 の int8 で CPU で動かす）
└── slackbot/            Slack ボット（Socket Mode）
    ├── bot.py           リンクの保存と「保存」ボタン
    └── notify.py        毎朝の新着の通知
```

| コンテナ | 役割 | ポート |
| --- | --- | --- |
| frontend | 画面 | 3000 |
| backend | API | 8000 |
| db | PostgreSQL 18 | 5432 |
| translator | 英→日の翻訳（backend からだけ使う） | — |
| slackbot | Slack 連携（トークンが無ければ起動しない） | — |

ポートは `127.0.0.1` だけで開いています。手元の PC で使う前提なので、同じネットワークの他の人からは開けないようにしています。

## 起動のしかた

Docker と Docker Compose が必要です。

```bash
cp .env.example .env     # POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB を書く
docker compose up -d --build
```

- 画面：http://localhost:3000
- API の一覧（FastAPI の自動ドキュメント）：http://localhost:8000/docs

テーブルは backend の起動時に `alembic upgrade head` で自動で作られます。

### ログイン

使うにはログインが必要です。本棚（登録した論文・ステータス・タグ・メモ・読書の記録）と新着のキーワードは人ごとに分かれます。論文の題名・著者・被引用数・訳文は全員で共有するので、ほかの人が登録済みの論文は arXiv に問い合わせずにすぐ入ります。

1. 最初の 1 人は http://localhost:3000/register から招待コード無しで登録できます。ログインを付ける前に登録した論文とキーワードは、この人が引き継ぎます
2. 2 人目からは招待コードが要ります。登録済みの人が「設定」で発行します（1 つのコードで 1 人、7 日間有効）
3. ユーザー名とパスワードは「設定」で変えられます（今のパスワードが要ります）。パスワードを変えると、ほかの端末ではログインし直しになります

パスワードは scrypt でハッシュにして保存し、ログイン中かどうかは HttpOnly の Cookie で見ます（30 日間有効）。

## テスト

```bash
docker compose exec backend pytest              # API と arXiv 取得のテスト
docker compose run --rm --no-deps slackbot pytest   # Slack ボットのテスト
docker compose exec translator pytest              # 翻訳（文の区切り方）のテスト
```

backend のテストは、本番とは別の DB（`papershelf_test`）を自動で作って使うので、登録した論文には影響しません。arXiv への問い合わせは偽物に差し替えているので、ネットワークが無くても動きます。

## Slack 連携の設定（任意）

1. https://api.slack.com/apps →「Create New App」→「From an app manifest」で、`slackbot/manifest.yml` の中身を貼り付けて作る
2. 「Basic Information」→「App-Level Tokens」で `connections:write` のトークンを作る（`xapp-...`）
3. 「Install App」でワークスペースにインストールし、`Bot User OAuth Token`（`xoxb-...`）をコピーする
4. `.env` に書いて、backend と slackbot を起動し直す。`BOT_TOKEN` は slackbot と backend の合言葉で、`python3 -c "import secrets;print(secrets.token_urlsafe(32))"` で作った値を入れる

   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   BOT_TOKEN=...
   ```

   ```bash
   docker compose up -d backend slackbot
   ```

5. 使いたいチャンネルで `/invite @paper-shelf`
6. 使う人はそれぞれ、画面の「設定」→「紐づけのコードを発行」を押し、出てきた `ps-link-…` をボットのいるチャンネルに投稿する（10 分間有効。投稿した瞬間に使われるので、ほかの人が見ても使えない）

紐づけた人が貼ったリンクは、その人の本棚に入ります。リンクごとに、保存したら ✅、登録済みなら 👀、失敗したら ⚠️ のリアクションが付きます。紐づけていない人が貼ったリンクは保存せず、その人にだけ見える返事で紐づけを促します。Socket Mode なので、公開 URL は要りません。

### 新着の通知（任意）

画面の「新着」でキーワードを登録し、知らせるチャンネルの ID を `.env` に書いて slackbot を起動し直します。チャンネルにはボットを招待しておきます。キーワードは人ごとで、Slack を紐づけた人の分だけ、その人をメンションして知らせます。「保存」は押した人の本棚に入り、通知のスレッドに誰が保存したかが書かれます。

```
SLACK_NOTIFY_CHANNEL=C0123456789   # チャンネル名を右クリック →「リンクをコピー」の末尾
NOTIFY_HOUR=9                      # 日本時間の何時に知らせるか
```

```bash
docker compose up -d slackbot
docker compose run --rm slackbot python bot.py notify   # 9 時を待たずに 1 回だけ試す
```

## 決めていること

- arXiv ID はバージョンを落とした形（`1706.03762`）で保存し、同じ論文は二重登録できない
- URL は保存しない（ID から組み立てる）
- タグは小文字にそろえる
- arXiv API の利用規約に合わせて、問い合わせは 3 秒に 1 回まで（画面と Slack から同時に登録しても守る）。429（問い合わせが多すぎる）が返ったら少し待って 1 回だけやり直す
- まとめて登録は、arXiv に 1 回の問い合わせでまとめて取りに行く（1 件ずつだと 20 件に 1 分かかる）
- 新着かどうかは日付ではなく「一度知らせた論文の ID」で判定する。公開日と通知の時刻がずれても、同じ論文を二度知らせず、取りこぼしもしない
- 引用関係は OpenAlex から取る。Semantic Scholar はキー無しだと 429（問い合わせが多すぎる）が続いて使えなかった。取った結果は 7 日間 DB にとっておく。`.env` に `OPENALEX_MAILTO=自分のメールアドレス` を書くと、OpenAlex の空いている枠を使える（任意）
- 被引用数と参考文献は、登録した直後に裏で取りに行く。「図で見る」の「引用の情報を更新」でも取り直せる（7 日以内に取ったものは問い合わせない）
- 「読んだ」にした日時を記録し、読んだ以外に戻したら消す
- 翻訳は GPU の無い PC（メモリ 3GB）でも動くよう、FuguMT（約 6,000 万パラメータ）を CTranslate2 の int8 に変換して使う。メモリは 300MB ほど、1 本（120 段落ほど）を 30 秒前後で訳す。数式や引用は XMATH1 / XREF2 という目印に置き換えて訳し、訳したあとで元に戻す
- 訳した HTML は arXiv から取ってきたものなので、スクリプトを一切動かさない（CSP と iframe の sandbox）
- BibTeX は `@article{..., journal = {arXiv preprint arXiv:番号}}` の形（Google Scholar と同じ）。`junsrt` など `eprint` 欄を表示しないスタイルでも番号が出るように
- ライブラリのバージョンは固定している（固定しないと、イメージを作り直しただけで壊れることがある）

## つまずきやすい所

- **ポートが使われていて起動しない**：`docker ps` で、他のプロジェクトのコンテナが 3000 / 8000 / 5432 を使っていないか確認する
- **コンテナ内で作ったファイルを VS Code で保存できない**：コンテナは root で動くので、`sudo chown -R $(id -u):$(id -g) backend` で持ち主を戻す
- **編集中にブラウザの「戻る」で離れると、警告が出ない**：Next.js にそれを止める仕組みが無いため。画面内の「← 一覧へ」やタブを閉じる操作では警告が出る
