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

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--entity",required=True,choices=list(RES_TYPE.keys()))
    ap.add_argument("--lang",required=True)  # zh-CN/zh-TW/th/es
    ap.add_argument("--export"); ap.add_argument("--import",dest="imp")
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg)
    if a.export: export(cfg,a.entity,a.lang,a.export)
    elif a.imp: imp(cfg,a.entity,a.lang,a.imp)
    else: print("需 --export FILE 或 --import FILE")
if __name__=="__main__": main()
