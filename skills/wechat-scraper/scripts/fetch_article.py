#!/usr/bin/env python3
import argparse
import html as html_lib
import json
import re
import ssl
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit(
        "Missing dependency: beautifulsoup4. Install it with "
        "`python3 -m pip install beautifulsoup4`."
    )

try:
    import certifi
except ImportError:
    certifi = None


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
ALLOWED_IMAGE_HOST_SUFFIXES = (
    ".qpic.cn",
    ".qlogo.cn",
    ".wx.qq.com",
)
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where() if certifi else None)


def validate_article_url(value):
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "mp.weixin.qq.com"
        or not (parsed.path == "/s" or parsed.path.startswith("/s/"))
    ):
        raise ValueError(
            "Expected a full HTTPS WeChat article URL under mp.weixin.qq.com/s."
        )
    return value


def fetch_html(url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://mp.weixin.qq.com/",
            "Origin": "https://mp.weixin.qq.com",
        },
    )
    with urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
        final_url = response.geturl()
        if urlparse(final_url).hostname != "mp.weixin.qq.com":
            raise RuntimeError(f"Unexpected redirect host: {final_url}")
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def decode_js_string(value):
    value = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda item: chr(int(item.group(1), 16)),
        value,
    )
    value = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda item: chr(int(item.group(1), 16)),
        value,
    )
    return (
        value.replace(r"\/", "/")
        .replace(r"\'", "'")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace(r"\\", "\\")
    )


def js_string(raw_html, name):
    match = re.search(
        rf"(?m)^\s*{re.escape(name)}:\s*'((?:\\.|[^'])*)'",
        raw_html,
    )
    return decode_js_string(match.group(1)) if match else ""


def text_page_content(raw_html):
    match = re.search(
        r"text_page_info\s*:\s*\{.*?\bcontent\s*:\s*'((?:\\.|[^'])*)'",
        raw_html,
        re.DOTALL,
    )
    return decode_js_string(match.group(1)) if match else ""


def js_number(raw_html, name):
    match = re.search(
        rf"(?m)^\s*{re.escape(name)}:\s*(?:'(\d+)'\s*\*\s*1|(\d+))",
        raw_html,
    )
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def meta_content(soup, *selectors):
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content") or node.get_text(" ", strip=True)
        if value:
            return value.strip()
    return ""


def normalize_text(value):
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    result = []
    previous_blank = False
    for line in lines:
        blank = not line
        if blank and previous_blank:
            continue
        result.append(line)
        previous_blank = blank
    return "\n".join(result).strip()


def extension_for(url, content_type):
    query_format = parse_qs(urlparse(url).query).get("wx_fmt", [""])[0].lower()
    formats = {
        "jpeg": ".jpg",
        "jpg": ".jpg",
        "png": ".png",
        "gif": ".gif",
        "webp": ".webp",
    }
    if query_format in formats:
        return formats[query_format]
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }.get(media_type, ".bin")


def localize_images(content, output_dir, article_url, skip_assets):
    errors = []
    localized = 0
    assets_dir = output_dir / "assets"
    for image in content.select("img"):
        if "赞赏二维码" in (image.get("alt") or ""):
            image.decompose()
            continue
        source = image.get("data-src") or image.get("src")
        if not source or source.startswith("data:"):
            continue
        if skip_assets:
            image["src"] = source
            continue
        parsed = urlparse(source)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(ALLOWED_IMAGE_HOST_SUFFIXES)
        ):
            errors.append({"url": source, "error": "image host not allowlisted"})
            continue
        try:
            request = Request(
                source,
                headers={"User-Agent": USER_AGENT, "Referer": article_url},
            )
            with urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
                payload = response.read()
                suffix = extension_for(source, response.headers.get("Content-Type"))
            localized += 1
            assets_dir.mkdir(parents=True, exist_ok=True)
            filename = f"img-{localized:03d}{suffix}"
            assets_dir.joinpath(filename).write_bytes(payload)
            image["src"] = f"assets/{filename}"
            image.attrs.pop("data-src", None)
        except Exception as error:
            errors.append({"url": source, "error": str(error)})
    return localized, errors


def standalone_html(title, body_html):
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{html_lib.escape(title)}</title></head>"
        f"<body><article id=\"js_article\">{body_html}</article></body></html>\n"
    )


def extract(raw_html, article_url, output_dir, skip_assets):
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.joinpath("raw.html").write_text(raw_html, encoding="utf-8")
    soup = BeautifulSoup(raw_html, "html.parser")
    error_node = soup.select_one(".weui-msg, .mesg-block")
    content = soup.select_one("#js_content")

    metadata = {
        "title": js_string(raw_html, "title")
        or meta_content(soup, 'meta[property="og:title"]', "#activity-name", "title"),
        "account_name": js_string(raw_html, "nick_name")
        or meta_content(
            soup,
            "#js_name",
            "#js_author_name_text",
            "#js_author_name",
        ),
        "author": js_string(raw_html, "author"),
        "summary": js_string(raw_html, "desc")
        or meta_content(
            soup,
            'meta[property="og:description"]',
            'meta[name="description"]',
        ),
        "cover_url": js_string(raw_html, "cdn_url")
        or meta_content(soup, 'meta[property="og:image"]'),
        "published_at": js_string(raw_html, "create_time"),
        "source_url": js_string(raw_html, "link") or article_url,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "is_async": js_number(raw_html, "is_async"),
        "page_type": js_number(raw_html, "page_type"),
        "item_show_type": js_number(raw_html, "item_show_type"),
        "links": [],
        "localized_images": 0,
        "asset_errors": [],
    }

    dom_has_content = bool(
        content
        and (
            content.get_text(" ", strip=True)
            or content.select_one("img, video, iframe, mpvoice")
        )
    )
    if dom_has_content:
        for selector in (
            "script",
            "style",
            "noscript",
            "#js_article_bottom_bar",
            ".qr_code_pc",
            ".rich_media_tool",
        ):
            for node in content.select(selector):
                node.decompose()
        metadata["links"] = [
            {
                "text": link.get_text(" ", strip=True),
                "url": link.get("href"),
            }
            for link in content.select("a[href]")
            if link.get("href")
        ]
        localized, errors = localize_images(
            content,
            output_dir,
            article_url,
            skip_assets,
        )
        metadata["localized_images"] = localized
        metadata["asset_errors"] = errors
        metadata["fetch_method"] = "static-dom"
        content_text = normalize_text(content.get_text("\n"))
        content_html = standalone_html(metadata["title"], content.decode_contents())
    else:
        content_text = (
            js_string(raw_html, "content_noencode")
            or text_page_content(raw_html)
        ).strip()
        if not content_text:
            detail = (
                error_node.get_text(" ", strip=True)
                if error_node
                else "Static HTML has no usable #js_content or cgiDataNew text."
            )
            raise RuntimeError(detail + " Playwright fallback is required.")
        metadata["fetch_method"] = "static-cgiDataNew"
        paragraphs = [
            f"<p>{html_lib.escape(paragraph)}</p>"
            for paragraph in re.split(r"\n{2,}", content_text)
            if paragraph.strip()
        ]
        content_html = standalone_html(metadata["title"], "".join(paragraphs))

    output_dir.joinpath("content.txt").write_text(
        content_text.rstrip() + "\n",
        encoding="utf-8",
    )
    output_dir.joinpath("content.html").write_text(
        content_html,
        encoding="utf-8",
    )
    output_dir.joinpath("metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata, content_text


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and archive one public WeChat article."
    )
    parser.add_argument("--url", required=True, type=validate_article_url)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--input-html",
        type=Path,
        help="Parse a saved raw HTML file instead of requesting the URL.",
    )
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Keep remote image URLs instead of downloading them.",
    )
    args = parser.parse_args()

    try:
        raw_html = (
            args.input_html.read_text(encoding="utf-8")
            if args.input_html
            else fetch_html(args.url)
        )
        metadata, content = extract(
            raw_html,
            args.url,
            args.output_dir,
            args.skip_assets,
        )
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "ok": True,
                "title": metadata["title"],
                "account_name": metadata["account_name"],
                "fetch_method": metadata["fetch_method"],
                "content_chars": len(content),
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
