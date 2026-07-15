#!/usr/bin/env python3
"""locale_check:主题 UI 译文完整性自检(踩过两次的坑:新语言只翻了商品,
   collection 筛选条 All/HOT/NEW、角标、header/footer/blog 等主题串还是英文,店面半英半外)。

   比对 locales/en.default.json(源)与 locales/<lang>.json,报:
     ① 缺失键(目标语言根本没有)
     ② 疑似未翻(值与英文一模一样、且含可翻译文字)—— 专名/占位符会误报,需人工/agent 复核。
   locale 文件路径 = config.theme.locales_dir(本地可覆盖)或 --theme-dir。
   同时可 --out gaps.json 把缺口导给 agent 翻译,填好合并回 <lang>.json 再 theme publish。

   用法: python3 locale_check.py [--lang es] [--theme-dir DIR] [--out gaps_es.json]
   注意:改完 locale 文件上线必须 `theme publish` 清 CDN 缓存(push 不清)。"""
import sys, os, json, re, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

# 目标语言 -> locale 文件名(Shopify 用 zh-CN/zh-TW 带区,其余用语言码)
def lang_file(lang): return f"{lang}.json"

def load_locale(path):
    """容错读:剥首个 /* */ 块注释(源码仓 locale 带自动生成头)、吞 BOM。"""
    s = open(path, encoding="utf-8-sig").read()
    s = re.sub(r'^\s*/\*.*?\*/\s*', '', s, count=1, flags=re.S)
    return json.loads(s)

def flat(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            nk = f"{p}.{k}" if p else k
            yield from flat(v, nk)
    else:
        yield p, o

# 去掉 Liquid 占位符 {{..}} / 复数 {..} 后,还剩可翻译字母才算「该翻」
def translatable(val):
    if not isinstance(val, str): return False
    stripped = re.sub(r'\{\{.*?\}\}|\{.*?\}', '', val)
    return any(c.isalpha() for c in stripped)

def locales_dir(cfg, override):
    d = override or (cfg.get("theme") or {}).get("locales_dir")
    if not d:
        print("✗ 未配 locale 目录:config.theme.locales_dir 或 --theme-dir DIR"); sys.exit(1)
    d = os.path.expanduser(d)
    if not os.path.isdir(d):
        print(f"✗ locale 目录不存在:{d}(改 config.theme.locales_dir 指向你的主题 checkout)"); sys.exit(1)
    return d

def check(cfg, langs, ldir, out):
    src = os.path.join(ldir, "en.default.json")
    if not os.path.exists(src):
        print(f"✗ 找不到源 {src}"); sys.exit(1)
    EN = dict(flat(load_locale(src)))
    print(f"源 en.default.json:{len(EN)} 个叶子键\n")
    any_issue = False; all_gaps = {}
    for lang in langs:
        fp = os.path.join(ldir, lang_file(lang))
        if not os.path.exists(fp):
            print(f"● {lang}: ✗ 无 {lang_file(lang)}(整门语言的主题译文都缺)"); any_issue = True; continue
        T = dict(flat(load_locale(fp)))
        miss = [k for k in EN if k not in T]
        untl = [k for k in EN if k in T and str(EN[k]) == str(T[k]) and translatable(EN[k])]
        status = "✓ 全翻" if not miss and not untl else "⚠ 有缺口"
        print(f"● {lang}: {status} — 缺失键 {len(miss)} · 疑似未翻 {len(untl)}")
        for k in (miss[:3]): print(f"    [缺失] {k} = {repr(EN[k])[:50]}")
        for k in (untl[:6]): print(f"    [未翻?] {k} = {repr(EN[k])[:50]}")
        if miss or untl:
            any_issue = True
            all_gaps[lang] = {k: EN[k] for k in miss + untl}
    if out and all_gaps:
        json.dump(all_gaps, open(out, "w"), ensure_ascii=False, indent=1)
        print(f"\n→ 缺口清单已导出 {out}(每语言 key→英文原值)。")
        print("  agent 翻译各值(专名/占位符 {{}} 保留不译),合并回对应 locales/<lang>.json,再 `theme publish`。")
    print("\n注:疑似未翻含专名/日期格式/占位符误报,需人工或 agent 复核;缺失键是硬缺。")
    return any_issue

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", help="只查某语言;默认 config.languages.alternates 全查")
    ap.add_argument("--theme-dir", help="locales 目录(覆盖 config.theme.locales_dir)")
    ap.add_argument("--out", help="把缺口清单导出到此文件给 agent 翻译")
    a = ap.parse_args()
    cfg = _lib.load_config()
    ldir = locales_dir(cfg, a.theme_dir)
    langs = [a.lang] if a.lang else (cfg.get("languages") or {}).get("alternates", [])
    if not langs: print("✗ 无目标语言"); sys.exit(1)
    issue = check(cfg, langs, ldir, a.out)
    sys.exit(1 if issue else 0)

if __name__ == "__main__":
    main()
