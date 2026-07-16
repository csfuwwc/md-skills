#!/usr/bin/env python3
"""image_optimize:详情页正文图尺寸优化(不重传、可逆)。

   问题:商品描述 HTML 里的 <img> 常是原图直出(4000px、几 MB),浏览器为显示 ~750px
   宽的图下载整张原图,一个商品页十几 MB。Shopify CDN 支持 URL 加 ?width=N 实时缩放。
   本脚本改写正文 <img>:src 加 width 上限 + srcset 响应式 + loading=lazy,payload 骤降。
   纯改 descriptionHtml(productUpdate),不动 media、不重传,去掉 width 参数即可回退。

   用法:
     python3 image_optimize.py --dry-run                 # 全部商品,只看不改
     python3 image_optimize.py --handle <h> --dry-run     # 单个商品预览前后
     python3 image_optimize.py --apply [--handle <h>]     # 写回(需显式 --apply)
   选项:--width 1600(上限)  --no-srcset(只封顶不加响应式)  --no-lazy"""
import sys, os, re, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

CDN = "cdn.shopify.com"
DEFAULT_CAP = 1600
SRCSET_WIDTHS = [480, 800, 1200, 1600]
SIZES = "(max-width: 750px) 100vw, 750px"

def strip_width(url):
    u = re.sub(r'([?&])width=\d+', r'\1', url)
    return u.replace("?&", "?").rstrip("?&")

def capped(url, cap):
    u = strip_width(url); sep = "&" if "?" in u else "?"
    return f"{u}{sep}width={cap}"

def build_srcset(url, widths):
    base = strip_width(url)
    out = []
    for w in widths:
        sep = "&" if "?" in base else "?"
        out.append(f"{base}{sep}width={w} {w}w")
    return ", ".join(out)

def rewrite_html(html, cap, do_srcset, do_lazy):
    """返回 (新html, 改动的图数)。只动 cdn.shopify.com 且未封顶的 <img>。"""
    n = [0]
    def repl(m):
        tag = m.group(0)
        src_m = re.search(r'\ssrc="([^"]+)"', tag)
        if not src_m: return tag
        src = src_m.group(1)
        if CDN not in src: return tag
        if re.search(r'[?&]width=\d+', src): return tag  # 已封顶,跳过
        n[0] += 1
        new = tag
        new = re.sub(r'(\ssrc=")[^"]+(")', lambda x: x.group(1)+capped(src, cap)+x.group(2), new)
        if do_srcset and 'srcset=' not in new:
            ins = f' srcset="{build_srcset(src, SRCSET_WIDTHS)}" sizes="{SIZES}"'
            new = re.sub(r'(<img)(\s)', r'\1'+ins+r'\2', new, count=1)
        if do_lazy and 'loading=' not in new:
            new = re.sub(r'(<img)(\s)', r'\1 loading="lazy" decoding="async"\2', new, count=1)
        return new
    out = re.sub(r'<img\b[^>]*>', repl, html or "")
    return out, n[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle"); ap.add_argument("--width", type=int, default=DEFAULT_CAP)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-srcset", action="store_true"); ap.add_argument("--no-lazy", action="store_true")
    a = ap.parse_args()
    if not a.apply and not a.dry_run:
        print("需 --dry-run(预览)或 --apply(写回)"); sys.exit(1)
    cfg = _lib.load_config(); store = cfg["shopify_store"]
    qfilter = f'query:"handle:{a.handle}"' if a.handle else 'query:"status:active OR status:draft"'
    q = '{ products(first:100, %s){ edges{ node{ id title handle descriptionHtml } } } }' % qfilter
    d = _lib.shopify(q, store)
    prods = [e["node"] for e in d["products"]["edges"]]
    total_imgs = 0; changed_prods = 0; sample_shown = False
    for p in prods:
        new, n = rewrite_html(p["descriptionHtml"], a.width, not a.no_srcset, not a.no_lazy)
        if n == 0: continue
        total_imgs += n; changed_prods += 1
        if a.dry_run and not sample_shown:
            olds = re.findall(r'<img\b[^>]*>', p["descriptionHtml"] or "")[:1]
            news = re.findall(r'<img\b[^>]*>', new)[:1]
            print(f"\n样例「{p['title'][:30]}」前后对比:")
            print("  改前:", (olds[0] if olds else "")[:130])
            print("  改后:", (news[0] if news else "")[:200]); sample_shown = True
        if a.apply:
            r = _lib.shopify("mutation($i:ProductInput!){ productUpdate(input:$i){ userErrors{message} } }",
                store, {"i": {"id": p["id"], "descriptionHtml": new}}, allow_mutations=True)
            errs = r["productUpdate"]["userErrors"]
            print(f"  {'✗ '+errs[0]['message'] if errs else '✓'} {p['title'][:34]}  {n} 图封顶 {a.width}px")
    print(f"\n{'[DRY-RUN] 将' if a.dry_run else '已'}优化 {changed_prods} 个商品 / {total_imgs} 张正文图 → 封顶 {a.width}px"
          + (" + srcset 响应式" if not a.no_srcset else "") + (" + lazy" if not a.no_lazy else ""))
    if a.dry_run: print("确认无误后:python3 image_optimize.py --apply" + (f" --handle {a.handle}" if a.handle else ""))

if __name__ == "__main__":
    main()
