# paper-shelf

arXiv の論文を登録して、タグ・読書ステータス・メモで整理する個人用の Web アプリです。PBL（2026 年度 秋学期）で作っています。

PDF 本文は扱わず、arXiv API から取れるメタデータ（タイトル・著者・abstract・公開日）だけを保存します。

## できること

- **登録**：arXiv の ID か URL を貼ると、タイトルなどを arXiv から取ってきて保存する（`1706.03762`、`https://arxiv.org/abs/1706.03762v7`、`arXiv:1706.03762` などどれでも可）
- **一覧と絞り込み**：タグ（複数選ぶと AND）・読書ステータス・タイトルと abstract のキーワード・著者名（部分一致）で絞り込み、並べ替える。条件は URL に入るので、ブックマークできる
- **詳細と編集**：タグ・ステータス・メモを編集する。メモは Markdown（表・チェックリスト・数式 `$...$`）で書け、チェックボックスはその場で押せる
- **図で見る**（`/insights`）：公開年ごとの本数、タグのつながり、共著者のつながり
- **Slack 連携**（任意）：ボットを招待したチャンネルに arXiv のリンクを貼ると自動で保存し、投稿文をメモに残す

## 構成

```
paper-shelf/
├── docker-compose.yml   4 つのコンテナの設定
├── frontend/            Next.js 16（App Router / TypeScript / Tailwind）
├── backend/             FastAPI + SQLModel + Alembic
│   ├── main.py          API
│   ├── models.py        テーブルと入出力の形
│   ├── arxiv.py         arXiv API からの取得
│   ├── migrations/      テーブルの変更履歴
│   └── tests/           pytest
└── slackbot/            Slack ボット（Socket Mode）
```

| コンテナ | 役割 | ポート |
| --- | --- | --- |
| frontend | 画面 | 3000 |
| backend | API | 8000 |
| db | PostgreSQL 18 | 5432 |
| slackbot | Slack 連携（トークンが無ければ起動しない） | — |

ポートは `127.0.0.1` だけで開いています。ログインの無いアプリなので、同じネットワークの他の人からは開けないようにしています。

## 起動のしかた

Docker と Docker Compose が必要です。

```bash
cp .env.example .env     # POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB を書く
docker compose up -d --build
```

- 画面：http://localhost:3000
- API の一覧（FastAPI の自動ドキュメント）：http://localhost:8000/docs

テーブルは backend の起動時に `alembic upgrade head` で自動で作られます。

## テスト

```bash
docker compose exec backend pytest              # API と arXiv 取得のテスト
docker compose run --rm --no-deps slackbot pytest   # Slack ボットのテスト
```

backend のテストは、本番とは別の DB（`papershelf_test`）を自動で作って使うので、登録した論文には影響しません。arXiv への問い合わせは偽物に差し替えているので、ネットワークが無くても動きます。

## Slack 連携の設定（任意）

1. https://api.slack.com/apps →「Create New App」→「From an app manifest」で、`slackbot/manifest.yml` の中身を貼り付けて作る
2. 「Basic Information」→「App-Level Tokens」で `connections:write` のトークンを作る（`xapp-...`）
3. 「Install App」でワークスペースにインストールし、`Bot User OAuth Token`（`xoxb-...`）をコピーする
4. `.env` に書いて、slackbot を起動する

   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   ```

   ```bash
   docker compose up -d slackbot
   ```

5. 使いたいチャンネルで `/invite @paper-shelf`

貼られたリンクごとに、保存したら ✅、登録済みなら 👀、失敗したら ⚠️ のリアクションが付きます。Socket Mode なので、公開 URL は要りません。

## 決めていること

- arXiv ID はバージョンを落とした形（`1706.03762`）で保存し、同じ論文は二重登録できない
- URL は保存しない（ID から組み立てる）
- タグは小文字にそろえる
- arXiv API の利用規約に合わせて、問い合わせは 3 秒に 1 回まで（画面と Slack から同時に登録しても守る）
- ライブラリのバージョンは固定している（固定しないと、イメージを作り直しただけで壊れることがある）

## つまずきやすい所

- **ポートが使われていて起動しない**：`docker ps` で、他のプロジェクトのコンテナが 3000 / 8000 / 5432 を使っていないか確認する
- **コンテナ内で作ったファイルを VS Code で保存できない**：コンテナは root で動くので、`sudo chown -R $(id -u):$(id -g) backend` で持ち主を戻す
- **編集中にブラウザの「戻る」で離れると、警告が出ない**：Next.js にそれを止める仕組みが無いため。画面内の「← 一覧へ」やタブを閉じる操作では警告が出る
