#!/usr/bin/env python3
"""translate:多语言机械 bookends(承接《多语言适配指南》)。
   --export:拉某实体的可翻译内容(EN源+digest)到文件,给 agent 逐条翻(填 target 字段)。
   --import:读文件,把译文 translationsRegister 回 Shopify。翻译本身是 agent 的活(守 DNT/去美元/去AI味)。
   用法: python3 translate.py --entity product --lang es --export out.json
          (agent 翻译 out.json,每 content 加 "target" 字段)
          python3 translate.py --entity product --lang es --import out.json"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
from entities import ML_METAFIELDS, LANG_SUFFIX, RES_LIST

RES_TYPE={"product":"PRODUCT","collection":"COLLECTION","article":"ARTICLE","page":"PAGE"}
TR_KEYS={"product":{"title","body_html","meta_title","meta_description"},
         "collection":{"title","body_html","meta_title","meta_description"},
         "article":{"title","body_html","summary_html","meta_title","meta_description"},
         "page":{"title","body_html","meta_title","meta_description"}}

def export(cfg, entity, lang, out):
    store=cfg["shopify_store"]; keys=TR_KEYS[entity]; rt=RES_TYPE[entity]
    q='''query($cursor:String){ translatableResources(first:30, resourceType: %s, after:$cursor){
      edges{ node{ resourceId translatableContent{ key value digest locale } } }
      pageInfo{ hasNextPage endCursor } } }'''%rt
    data=[]; cursor=None
    while True:
        d=_lib.shopify(q, store, {"cursor":cursor}); tr=d["translatableResources"]
        for e in tr["edges"]:
            n=e["node"]; cs=[{"key":c["key"],"digest":c["digest"],"en":c["value"],"target":""}
                for c in n["translatableContent"] if c["key"] in keys and c.get("value")]
            if cs: data.append({"resourceId":n["resourceId"],"contents":cs})
        if tr["pageInfo"]["hasNextPage"]: cursor=tr["pageInfo"]["endCursor"]
        else: break
    json.dump(data, open(out,"w"), ensure_ascii=False, indent=1)
    n=sum(len(r["contents"]) for r in data)
    print(f"导出 {entity} {len(data)} 资源 / {n} 字段 → {out}")
    print(f"→ agent 翻译:每个 content 的 'target' 填 {lang} 译文(DNT不译/非美元去$/去AI味/HTML结构一致),再 --import")

def imp(cfg, entity, lang, inp):
    store=cfg["shopify_store"]; data=json.load(open(inp)); ok=0; errs=[]
    for res in data:
        trans=[{"key":c["key"],"locale":lang,"value":c["target"],"translatableContentDigest":c["digest"]}
               for c in res["contents"] if c.get("target","").strip()]
        for i in range(0,len(trans),100):
            r=_lib.shopify("mutation($id:ID!,$t:[TranslationInput!]!){ translationsRegister(resourceId:$id, translations:$t){ userErrors{message} translations{key} } }",
                store, {"id":res["resourceId"],"t":trans[i:i+100]}, allow_mutations=True)
            rr=r["translationsRegister"]; errs+=rr["userErrors"]; ok+=len(rr.get("translations",[]) or [])
    print(f"注册 {lang} 译文 {ok} 字段,错误 {len(errs)}")
    for e in errs[:5]: print("  ",e)


def export_mf(cfg, entity, lang, out):
    store=cfg["shopify_store"]; mfs=ML_METAFIELDS.get(entity,[])
    if not mfs: print(f"{entity} 无需 _<lang> metafield 变体"); return
    if entity not in RES_LIST: print(f"{entity} 暂不支持 metafield 变体"); return
    suf=LANG_SUFFIX.get(lang, lang.lower().replace("-",""))
    sel=" ".join(f'm{i}:metafield(namespace:"{ns}",key:"{k}"){{ value }}' for i,(ns,k,ty) in enumerate(mfs))
    q='{ %s(first:60){ edges{ node{ id %s } } } }'%(RES_LIST[entity], sel)
    d=_lib.shopify(q, store); rows=[]
    for e in d[RES_LIST[entity]]["edges"]:
        n=e["node"]
        for i,(ns,k,ty) in enumerate(mfs):
            v=(n.get(f"m{i}") or {}).get("value")
            if v and str(v).strip():
                rows.append({"ownerId":n["id"],"namespace":ns,"key":f"{k}_{suf}","type":ty,"base":v,"target":""})
    json.dump(rows, open(out,"w"), ensure_ascii=False, indent=1)
    print(f"导出 {entity} 的 _<{suf}> metafield 变体 {len(rows)} 个 → {out}")
    print(f"→ agent 翻译每个 'target'(rich_text/json 保结构、只翻可见文字;DNT不译),再 --import-mf")

def import_mf(cfg, lang, inp):
    store=cfg["shopify_store"]; rows=json.load(open(inp))
    mset=[{"ownerId":r["ownerId"],"namespace":r["namespace"],"key":r["key"],"type":r["type"],"value":r["target"]}
          for r in rows if r.get("target","").strip()]
    ok=0; errs=[]
    for i in range(0,len(mset),25):
        r=_lib.shopify("mutation($m:[MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ metafields{id} userErrors{field message} } }",
            store, {"m":mset[i:i+25]}, allow_mutations=True)
        rr=r["metafieldsSet"]; errs+=rr["userErrors"]; ok+=len(rr.get("metafields",[]) or [])
    print(f"写入 _<lang> metafield 变体 {ok} 个,错误 {len(errs)}")
    for e in errs[:5]: print("  ",e)

def market_check(cfg, lang):
    """#2 校验:翻译完还得在 market 启用+发布该语言,否则前台不显示(翻完纳闷没变的坑)。"""
    store=cfg["shopify_store"]
    q='{ markets(first:50){ edges{ node{ name enabled webPresence{ defaultLocale{locale} alternateLocales{locale} } } } } }'
    d=_lib.shopify(q, store)
    hit=[]
    for e in d["markets"]["edges"]:
        n=e["node"]; wp=n.get("webPresence") or {}
        locs=[(wp.get("defaultLocale") or {}).get("locale")]+[a["locale"] for a in (wp.get("alternateLocales") or [])]
        if lang in locs: hit.append((n["name"], n["enabled"]))
    print(f"[market-check] 语言 {lang}:")
    if not hit:
        print(f"  ✗ 没有任何 market 启用了 {lang} —— 就算内容翻好了,前台也不会显示这门语言!")
        print(f"    去 Shopify 后台 设置→市场→选市场→语言,添加并发布 {lang}。")
        return False
    for name,en in hit:
        print(f"  {'✓' if en else '✗ 市场未启用'} {name}:含 {lang}")
    live=[n for n,en in hit if en]
    print(f"  → {lang} 已在 {len(live)} 个启用市场:{', '.join(live) if live else '(都没启用!)'}")
    return bool(live)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--entity",default="product",choices=list(RES_TYPE.keys()))
    ap.add_argument("--lang",required=True)  # zh-CN/zh-TW/th/es
    ap.add_argument("--export"); ap.add_argument("--import",dest="imp")
    ap.add_argument("--export-mf"); ap.add_argument("--import-mf",dest="impmf"); ap.add_argument("--metafields",action="store_true")
    ap.add_argument("--market-check",action="store_true",help="校验该语言是否已在 market 启用+发布")
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg)
    if a.market_check: sys.exit(0 if market_check(cfg,a.lang) else 1)
    if a.export: export(cfg,a.entity,a.lang,a.export)
    elif a.imp: imp(cfg,a.entity,a.lang,a.imp)
    elif a.export_mf: export_mf(cfg,a.entity,a.lang,a.export_mf)
    elif a.impmf: import_mf(cfg,a.lang,a.impmf)
    else: print("需 --export/-mf 或 --import/-mf FILE")
if __name__=="__main__": main()
