"""Download a demo corpus: about 20,000 passages from questions and answers on
The Workplace (workplace.stackexchange.com), from the Stack Exchange data dump
at the Internet Archive.

Licence: CC BY-SA 4.0. Only posts created on or after 2018-05-02 are used.
Every passage keeps its author's display name, a link to the author's profile
and a link to the question it comes from.

    python -I examples/fetch_demo.py

Needs `bsdtar` or `7z` on PATH to unpack the archive. Writes the archive and
the two XML files it uses to examples/demo/raw/ and the passages to
examples/demo/passages.parquet. `--sample PATH` also writes a 200-row CSV.
The download is parsed as data only.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

SITE = "workplace.stackexchange.com"
ARCHIVE = f"https://archive.org/download/stackexchange/{SITE}.7z"
HERE = Path(__file__).resolve().parent
SINCE = "2018-05-02"        # contributions from this date on are CC BY-SA 4.0
MIN_SCORE = 2
MIN_WORDS, MAX_WORDS = 60, 200
PER_POST = 3                # passages kept per post
BLOCKS = {"p", "li", "h1", "h2", "h3", "blockquote"}
PERSONAL = re.compile(r"@\w+\.\w+|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def download(raw: Path) -> Path:
    archive = raw / f"{SITE}.7z"
    if not archive.exists():
        req = urllib.request.Request(ARCHIVE, headers={"User-Agent": "textchef-demo-fetch/0.1"})
        part = archive.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=120) as resp, open(part, "wb") as f:
            shutil.copyfileobj(resp, f)
        part.rename(archive)
    return archive


def unpack(archive: Path, raw: Path) -> None:
    """Extract only the two members used, by name, into the raw folder."""
    if (raw / "Posts.xml").exists() and (raw / "Users.xml").exists():
        return
    if shutil.which("bsdtar"):
        cmd = ["bsdtar", "-x", "-f", str(archive), "-C", str(raw), "Posts.xml", "Users.xml"]
    elif shutil.which("7z"):
        cmd = ["7z", "e", "-y", f"-o{raw}", str(archive), "Posts.xml", "Users.xml"]
    else:
        raise SystemExit("install bsdtar or 7z to unpack the archive")
    subprocess.run(cmd, check=True)


class Paragraphs(HTMLParser):
    """Text of each block element; code blocks are skipped."""

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.buf: list[str] = []
        self.skip = 0

    def _flush(self) -> None:
        text = " ".join("".join(self.buf).split())
        if text:
            self.out.append(text)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self.skip += 1
        if tag in BLOCKS or tag == "br":
            self._flush()

    def handle_endtag(self, tag):
        if tag == "pre":
            self.skip = max(0, self.skip - 1)
        if tag in BLOCKS:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def paragraphs(html: str) -> list[str]:
    parser = Paragraphs()
    parser.feed(html)
    parser._flush()
    return parser.out


def passages(paras: list[str]) -> list[str]:
    """Join short paragraphs and split long ones into 60-200 word passages."""
    pieces: list[str] = []
    for p in paras:
        if len(p.split()) <= MAX_WORDS:
            pieces.append(p)
            continue
        cur: list[str] = []
        for sentence in SENTENCE.split(p):
            if cur and len(" ".join(cur + [sentence]).split()) > MAX_WORDS:
                pieces.append(" ".join(cur))
                cur = []
            cur.append(sentence)
        pieces.append(" ".join(cur))
    out: list[str] = []
    cur, n = [], 0
    for piece in pieces:
        words = len(piece.split())
        if cur and n + words > MAX_WORDS:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(piece)
        n += words
        if n >= MIN_WORDS:
            out.append(" ".join(cur))
            cur, n = [], 0
    return [t for t in out if MIN_WORDS <= len(t.split()) <= MAX_WORDS]


def rows_of(xml: Path):
    for _, el in ET.iterparse(xml, events=("end",)):
        if el.tag == "row":
            yield el.attrib
            el.clear()


def build(raw: Path) -> pd.DataFrame:
    users = {u["Id"]: u.get("DisplayName", "") for u in rows_of(raw / "Users.xml")}
    tags: dict[str, str] = {}
    kept = []
    for post in rows_of(raw / "Posts.xml"):
        kind = post.get("PostTypeId")
        if kind == "1":
            found = re.findall(r"[^<>|]+", post.get("Tags", ""))
            tags[post["Id"]] = found[0] if found else ""
        if kind in ("1", "2") and post.get("CreationDate", "") >= SINCE \
                and int(post.get("Score", 0)) >= MIN_SCORE and users.get(post.get("OwnerUserId", "")):
            kept.append(post)

    out = []
    for post in kept:
        question = post["Id"] if post["PostTypeId"] == "1" else post.get("ParentId", "")
        texts = [t for t in passages(paragraphs(post.get("Body", ""))) if not PERSONAL.search(t)]
        for n, text in enumerate(texts[:PER_POST]):
            out.append({
                "post_id": post["Id"],
                "passage": n + 1,
                "text": text,
                "tag": tags.get(question) or None,
                "post_type": "Question" if post["PostTypeId"] == "1" else "Answer",
                "score": int(post.get("Score", 0)),
                "date": post["CreationDate"][:10],
                "year": int(post["CreationDate"][:4]),
                "author": users[post["OwnerUserId"]],
                "author_url": f"https://{SITE}/users/{post['OwnerUserId']}",
                "url": f"https://{SITE}/questions/{question}"
                       + ("" if post["PostTypeId"] == "1" else f"#{post['Id']}"),
            })
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20000)
    ap.add_argument("--out", type=Path, default=HERE / "demo")
    ap.add_argument("--raw", type=Path, help="folder for the download (default OUT/raw)")
    ap.add_argument("--sample", type=Path, help="also write a 200-row CSV here")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    raw = args.raw or args.out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    unpack(download(raw), raw)

    df = build(raw)
    df = df.sample(n=min(args.rows, len(df)), random_state=args.seed)
    df = df.sort_values(["post_id", "passage"], key=lambda c: c.astype(int)).reset_index(drop=True)
    df.to_parquet(args.out / "passages.parquet", index=False)
    print(f"wrote {len(df):,} passages from {df['post_id'].nunique():,} posts "
          f"-> {args.out / 'passages.parquet'}")
    if args.sample:
        # whole posts, so the sample has passages that share a post
        posts = df["post_id"].drop_duplicates().sample(frac=1, random_state=args.seed)
        sample = df[df["post_id"].isin(posts.head(175))].head(200)
        sample.to_csv(args.sample, index=False)
        print(f"wrote {len(sample)} rows -> {args.sample}")


if __name__ == "__main__":
    main()
