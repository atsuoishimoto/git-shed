# git-shed 企画書

## 概要

`git-shed` は、**Git remote に応じてローカルの保存用ディレクトリを用意し、リポジトリ内からリンクするための CLI ツール**。

開発中には、次のような「Git には入れたくないが、そのリポジトリと一緒に扱いたいファイル」がよく発生する。

- 個人的なメモ
- 調査用 SQL
- デバッグ用スクリプト
- ローカル専用設定
- API レスポンスのサンプル
- 一時的な検証コード
- AI に渡す作業メモ
- テストデータ

`git-shed` は、remote repository identity にマッチする shed を判定し、デフォルトで `~/.shed/<name>` を作成する。
そのうえで、対象リポジトリの `.shed/<name>` からリンクする。

例:

```text
~/.shed/
├── company/
└── backend/

~/src/foo/
└── .shed/
    ├── company -> ~/.shed/company
    └── backend -> ~/.shed/backend
```

`git-shed` はリンク先ディレクトリの中身には関与しない。


---

## コンセプト

`shed` は「物置」の意味。

> リポジトリ本体には入れないが、そのリポジトリに関係するものを置いておく場所。

ツール名、Git サブコマンド、マウントポイントを以下で統一する。

```text
tool:       git-shed
command:    git shed
mountpoint: .shed/
```

例:

```text
repo/
├── .git/
├── src/
└── .shed/
    ├── company/
    ├── backend/
    └── project-x/
```

`.shed/` 自体にはデータを保存せず、各エントリがリポジトリ外の実データ領域を指す。

---

## 解決したい問題

### 1. Git には入れたくない

`.gitignore` に追加すると、そのルール自体がチーム共有される。

個人用のファイルについては、本体リポジトリの履歴や設定を汚したくない。

### 2. clone を削除しても残したい

リポジトリ内部に ignored directory を作るだけでは、

```bash
rm -rf repo
```

で一緒に消える。

`shed` の実データはリポジトリ外に保存する。

### 3. 同じ remote の複数 clone から使いたい

例えば以下がすべて同じ remote を向いている場合、

```text
~/src/foo
~/tmp/foo-debug
~/work/foo-test
```

同じ shed にアクセスできるようにする。

### 4. 複数リポジトリで同じ領域を共有したい

例えば、

```text
github.com/acme/foo
github.com/acme/bar
github.com/acme/baz
```

をすべて `company` shed に接続する。

ファイル名衝突やディレクトリ構成は、ツールではなくユーザーの運用規約で管理する。

---

## 基本モデル

`git-shed` は remote repository identity を取得し、設定された shed の match rule にマッチさせる。

```text
Git remote
    ↓
canonical repository identity
    ↓
shed matcher
    ↓
0個以上の shed
    ↓
.shed/<shed>
```

重要なのは、**shed は排他的ではない**こと。

1つの repository が複数 shed にマッチしてよい。

例:

```text
repository:
  github.com/acme/api

matches:
  github.com/acme/*   -> company
  github.com/acme/api -> backend
```

結果:

```text
.shed/
├── company/
└── backend/
```

---

## 保存領域

MVP では shed の保存先を固定する。

```text
~/.shed/<shed-name>
```

例えば、

```toml
[[shed]]
name = "company"
match = ["github.com/acme/*"]

[[shed]]
name = "backend"
match = ["github.com/acme/api"]
```

なら、必要に応じて次のディレクトリを自動作成する。

```text
~/.shed/
├── company/
└── backend/
```

shed ごとの任意 `path` 指定や storage root の変更は MVP では扱わない。

複数 repository が同じ shed にマッチする場合は、同じ `~/.shed/<name>` を参照する。


---

## `.shed/` の構造

`.shed/` 自体は通常の directory とする。

各 shed entry のみ外部領域へのリンクにする。

Unix:

```text
.shed/
├── company -> ~/.shed/company
├── backend -> ~/.shed/backend
└── foo     -> ~/.shed/foo
```

Windows:

```text
.shed\
├── company\   Junction
├── backend\   Junction
└── foo\       Junction
```

Git には `.shed/` 全体を見せない。

`.git/info/exclude` に以下を追加する。

```gitignore
/.shed/
```

`.gitignore` は変更しない。

---

## Remote Identity

shed matching のキーには remote URL をそのまま使わず、canonical repository identity に正規化する。

例えば以下をすべて同じ identity とみなす。

```text
git@github.com:acme/foo.git
https://github.com/acme/foo.git
ssh://git@github.com/acme/foo.git
https://github.com/acme/foo
```

正規化後:

```text
github.com/acme/foo
```

### 正規化ルール案

1. protocol を除去
2. user 名を除去
3. hostname を小文字化
4. SCP-style SSH URL を path 形式へ変換
5. path 先頭の `/` を除去
6. 末尾の `.git` を除去
7. 末尾の `/` を除去

---

## Remote の選択

基本は `origin` を利用する。

```bash
git remote get-url origin
```

fork などで別 remote を基準にしたい場合は、設定で変更できるようにする。

例:

```text
origin
  git@github.com:user/foo.git

upstream
  git@github.com/acme/foo.git
```

`upstream` を identity として使いたい場合:

```bash
git config --local shed.remote upstream
```

あるいは将来的に CLI で:

```bash
git shed remote upstream
```

---

## Shed

この企画では、管理単位そのものを `shed` と呼ぶ。

1つの shed は1つの実データ保存領域を持ち、match rule に一致した複数の repository から参照できる。
repository は複数の shed に同時にマッチしてよい。

例:

```toml
[[shed]]
name = "company"
match = ["github.com/acme/*"]

[[shed]]
name = "backend"
match = [
  "github.com/acme/api",
  "github.com/acme/worker"
]

[[shed]]
name = "personal"
match = ["github.com/me/*"]
```

`github.com/acme/api` は `company` と `backend` の両方の shed にマッチする。

```text
.shed/
├── company/
└── backend/
```

---

## Pattern Matching

初期実装では repository identity を `/` 区切りの segment として扱う。

候補:

```text
github.com/acme/foo
github.com/acme/*
github.com/*
*
```

将来的には GitLab のサブグループ などを考慮して `**` も扱えるようにする。

```text
*   = 1 segment
**  = 0個以上の segment
```

例:

```text
gitlab.com/company/**
```

shed は複数マッチしてよいため、priority や specificity による勝者決定は不要。

---


## 設定ファイル

shed 定義は独立した設定ファイルに置く。

例:

```text
~/.config/git-shed/config.toml
```

設定例:

```toml
[[shed]]
name = "company"
match = [
  "github.com/acme/*"
]

[[shed]]
name = "backend"
match = [
  "github.com/acme/api",
  "github.com/acme/worker"
]

[[shed]]
name = "personal"
match = [
  "github.com/me/*"
]
```


---

## CLI 案

### `git shed`

現在の repository に対して必要な shed mount を作成・同期する。

初回実行でも利用可能にする。

処理:

```text
remote を取得
↓
canonicalize
↓
matching sheds を取得
↓
~/.shed/<name> を必要に応じて作成
↓
repo/.shed/ を必要に応じて作成
↓
repo/.shed/<name> にリンクを作成
↓
.git/info/exclude を更新
```

---

### `git shed sync`

現在マッチする shed と `.shed/` の状態を同期する。

マッチする shed が0件の場合は、デフォルトで対話モードに入り、新しい shed の作成を案内する。

例:

現在:

```text
.shed/
├── company
├── backend
└── old-shed
```

現在マッチする shed:

```text
company
backend
foo
```

実行後:

```text
+ foo
- old-shed
```

削除するのは `.shed/old-shed` の link / junction のみ。

**実データは絶対に削除しない。**

---

### `git shed status`

例:

```text
repository: github.com/acme/api
remote:     origin

sheds:
  company   github.com/acme/*
  backend   github.com/acme/api

mounts:
  .shed/company
  .shed/backend
```

---

### `git shed list`

現在の repository にマッチしている shed を表示する。

```text
company
backend
```

---

### `git shed list --all`

定義済み shed をすべて表示する。

---

### `git shed path <shed>`

shed の実データ path を返す。

```bash
git shed path company
```

出力:

```text
/home/user/.shed/company
```

shell script との連携にも使える。

---

### `git shed open <shed>`

対象 shed を OS の file manager で開く。

---


## 対話モード

対話モードは `git shed sync` と `git shed add` の両方で利用する。

### `git shed sync` の対話モード

`git shed sync` 実行時、現在の repository にマッチする shed が1件もない場合だけ対話モードに入る。

```text
0 matches
  → interactive setup

1+ matches
  → sync only
```

現在の repository identity が:

```text
github.com/acme/foo
```

の場合:

```text
$ git shed sync

No shed matches:
  github.com/acme/foo

Create a new shed? [Y/n] y

Shed name [foo]: company
Match pattern [github.com/acme/foo]: github.com/acme/*

Add another match pattern? [y/N] n

Create shed:
  name:  company
  match:
    - github.com/acme/*
  path:  ~/.shed/company

Create? [Y/n] y

Created shed:
  company

Created directory:
  ~/.shed/company

Linked:
  .shed/company -> ~/.shed/company
```

作成を確定した場合は shed 定義の追加後、そのまま現在の repository に対する sync を続行する。

### `git shed add` の対話モード

`git shed add` は不足している引数を対話的に補完する。

引数なし:

```text
$ git shed add

Shed name [foo]: company
Match pattern [github.com/acme/foo]: github.com/acme/*
Add another match pattern? [y/N] n

Create? [Y/n] y
```

shed 名だけ指定:

```text
$ git shed add company

Match pattern [github.com/acme/foo]: github.com/acme/*
Add another match pattern? [y/N] n

Create? [Y/n] y
```

完全指定:

```bash
git shed add company --match 'github.com/acme/*'
```

この場合は対話せず追加する。

### デフォルト値

Git repository 内で実行している場合:

```text
repository:
  github.com/acme/foo

Shed name default:
  foo

Match pattern default:
  github.com/acme/foo
```

そのまま Enter を押せば repository 固有の shed になる。

owner 配下で共有したい場合は:

```text
github.com/acme/*
```

のように wildcard を入力する。

Git repository 外では repository identity を取得できないため、shed 名と最初の match pattern は必須入力とする。

### 複数 match pattern

1つの shed に複数 pattern を設定できる。

対話モードでは最初の pattern 入力後に追加確認を行う。

```text
Match pattern: github.com/acme/api
Add another match pattern? [y/N] y
Match pattern: github.com/acme/worker
Add another match pattern? [y/N] n
```

### 非対話モード

`git shed sync` には `--no-interactive` を用意する。

```bash
git shed sync --no-interactive
```

マッチする shed がない場合は何も作成せず、状態を表示して終了する。

```text
No shed matches github.com/acme/foo
```

非対話で shed を追加する場合は必要な値をすべて指定する。

```bash
git shed add company --match 'github.com/acme/*'
git shed sync --no-interactive
```

`git shed add` に `--no-interactive` は設けない。
必要な値が不足していて標準入力が対話利用できない場合はエラーとする。

### 終了コード

MVP では以下を基本方針とする。

```text
0
  sync 自体は正常
  マッチする shed が0件でもエラーにはしない

non-zero
  設定ファイルの解析失敗
  Git repository の取得失敗
  remote URL の解釈失敗
  shed add に必要な入力不足
  link / junction の作成失敗
  その他の実行エラー
```


---

## Windows 対応

Windows では **Directory Junction** を使用する。

`git-shed` が扱うリンクは、常に directory から local directory への接続なので、MVP では symbolic link を使用しない。

例:

```text
repo\.shed\company
    ↓ junction
C:\Users\user\.shed\company
```

実装方針:

```text
Linux / macOS
  → symbolic link

Windows
  → directory junction
```

`.shed` 自体は通常の directory とし、各 shed entry ごとに junction を作成する。

概念的な API:

```text
mountShed(name, target)
unmountShed(name)
```

OS ごとの差異はこの mount / unmount 処理の内部に閉じ込める。


---

## 安全性

このツールには「Git 管理外だが捨てたくないデータ」が置かれるため、破壊的操作を極力避ける。

### 原則

- `sync` は link / junction のみ削除可能
- shed の実データは自動削除しない
- remote URL が変わっても既存データを自動移動しない
- repository 削除後も shed data は残す
- `.gitignore` は変更しない
- `.git/info/exclude` のみ変更する

### Remote 変更

例えば、

```text
before:
github.com/oldorg/foo

after:
github.com/neworg/foo
```

となった場合、自動 migration はしない。

`status` で差異を確認できるようにする。

---

## 非目標

初期バージョンでは以下は扱わない。

### Shed 内部の管理

`git-shed` は shed の中身を管理しない。

以下はすべてユーザー側の運用に任せる。

- ファイルやディレクトリの構成
- ファイル名の衝突回避
- shed 内の Git 管理
- バックアップ
- 同期
- 暗号化
- secrets 管理

### 保存先のカスタマイズ

MVP では shed の保存先を `~/.shed/<name>` に固定する。

shed ごとの `path` 指定や storage root の変更は扱わない。

### 大容量ファイル専用管理

git-annex や Git LFS の代替ではない。


---

## 設計原則

### 1. リンク作成に徹する

`git-shed` の中心的な責務は、repository identity に応じて shed を解決し、リンクを作ること。

shed 内のファイル内容や構造には関与しない。

### 2. Shed は複数マッチ可能

1つの repository が複数の shed に同時にマッチしてよい。

```text
repository
    │
    ├──→ company shed
    └──→ backend shed
```

### 3. 保存先は規約で決める

MVP では保存先を固定する。

```text
target(shed) = ~/.shed/<shed.name>
```

設定項目を増やさず、挙動を予測しやすくする。

### 4. Clone は使い捨て可能

shed の実データは clone の外側にあるため、repository を削除しても残る。

```text
clone
  ↓ delete

~/.shed/<name>
  ↓ remains
```

### 5. Repository identity は remote を基準にする

filesystem path や clone UUID ではなく、remote repository identity を match のキーにする。

### 6. データを自動削除しない

`sync` などで削除してよいのは repository 内の link / junction だけとする。

`~/.shed/<name>` の実データは自動削除しない。


---

## 想定ユースケース

### 会社 repository 群

```toml
[[shed]]
name = "company"
match = ["github.com/acme/*"]
```

各 repository から、

```text
.shed/company/
```

が見える。

用途:

```text
notes/
queries/
fixtures/
debug-scripts/
```

---

### Backend repository 群

```toml
[[shed]]
name = "backend"
match = [
  "github.com/acme/api",
  "github.com/acme/worker"
]
```

対象 repository では、

```text
.shed/
├── company/
└── backend/
```

となる。

---

### Repository 固有 shed

```toml
[[shed]]
name = "foo"
match = ["github.com/acme/foo"]
```

`foo` repository だけ、

```text
.shed/foo/
```

を利用できる。

---

## MVP

初期バージョンは、repository-aware link creation に絞る。

### 必須機能

- Git repository 検出
- `origin` URL 取得
- remote URL canonicalization
- TOML 設定読み込み
- shed pattern matching
- 複数 shed match
- `~/.shed/<name>` の自動作成
- `repo/.shed/` の自動作成
- Linux / macOS での symbolic link 作成
- Windows での directory junction 作成
- `.git/info/exclude` への `/.shed/` 追加
- `git shed`（usage表示のみ）
- `git shed sync`
- `git shed sync --no-interactive`
- `git shed add`
- `git shed remove`
- `git shed status`
- `git shed list`
- `git shed path`

### MVP では扱わない

- shed ごとの任意 `path`
- storage root の変更
- repository ごとの例外指定
- shed 内部の管理
- backup / file sync
- orphan cleanup
- GC
- migration
- shell completion
- worktree / clone 固有 scope


---


## 類似プロジェクト

完全に同一の用途ではないが、近い発想を持つ既存ツールがある。

- **Foursquare gitshed**
  - Git 外の content store と repository 内の symlink を組み合わせるツール。
  - 大容量ファイル管理が主目的で、本企画とは用途が異なる。
  - 同名だが、かなり以前に開発が停止しており、現在の利用実態は不明。

- **GNU Stow**
  - 中央のディレクトリから symlink を配置する仕組み。
  - repository の remote identity による自動選択は行わない。

- **chezmoi**
  - dotfiles やローカル設定を中央管理し、各配置先へ反映するツール。
  - 開発 repository ごとの remote match を主目的とはしていない。

- **local-config-sync**
  - Git 管理外のローカル設定を別領域で管理し、symlink や `.git/info/exclude` を利用する。
  - ファイル同期や別 Git repository の管理まで含むため、本企画より責務が広い。

本企画の差分は、機能を **remote-aware なローカル directory link 管理**に絞る点にある。


---

## 実装言語

Go が有力。

理由:

- 単一バイナリ配布が容易
- Windows / macOS / Linux 対応
- filesystem 操作が容易
- Git command の実行が容易
- `git-shed` を PATH に置くだけで `git shed` として利用可能

Git は、

```bash
git shed
```

が呼ばれた場合、PATH 上の、

```text
git-shed
```

を実行する。

Git 本体への plugin API は不要。

---

## 最小内部モデル

```text
Repository {
    remote_name
    remote_url
    canonical_identity
}

Shed {
    name
    match[]
}

MatchResult {
    repository
    sheds[]
}
```

shed の保存先は設定値ではなく規約で決まる。

```text
shedPath(name) = ~/.shed/<name>
```

処理フロー:

```text
discover repository
      ↓
resolve remote
      ↓
canonicalize identity
      ↓
load sheds
      ↓
match all sheds
      ↓
mkdir ~/.shed/<name>
      ↓
mkdir repo/.shed
      ↓
link repo/.shed/<name> -> ~/.shed/<name>
```


---

## 一文で説明するなら

> **Git remote にマッチする shed を `~/.shed` に用意し、repository の `.shed/` からリンクするツール。**

英語なら:

> **A repository-aware link manager for local files kept outside Git.**
