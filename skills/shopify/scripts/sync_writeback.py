#!/usr/bin/env python3
"""sync_writeback:飞书表「待确认上线」行 → 写回 Shopify(productUpdate + metafieldsSet)。
   字段级 diff(只写与线上不同的);handle 绝不写回;写完回填状态=已上线。
   ★同事运行本脚本 = 「确认上线」这个人工闸★。
   v1 范围:EN title/描述/SEO/type/tags + custom.* metafield。集合/多语言写回=v1.1(归各自步骤)。
   用法: python3 sync_writeback.py [--status 待确认上线] [--dry-run] [--limit N]"""
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

# 飞书列 -> productUpdate 字段
PU = {"商品名称":"title", "商品描述EN":"descriptionHtml"}
SEO = {"SEO Title EN":"title", "SEO描述EN":"description"}
# 飞书列 -> (metafield namespace, key, type)
MF = {
 "custom.material 材质":("custom","material","single_line_text_field"),
 "custom.height_cm 高度":("custom","height_cm","single_line_text_field"),
 "custom.box_size_cm 单盒尺寸：长|宽|高":("custom","box_size","single_line_text_field"),
 "custom.hidden_odds 隐藏款概率":("custom","hidden_odds","single_line_text_field"),
 "custom.series 系列":("custom","series","single_line_text_field"),
 "custom.scenario_copy 场景文案":("custom","scenario_copy","multi_line_text_field"),
 "custom.faq 常见问题":("custom","faq","json"),
}
CUR_Q = """query($id:ID!){ product(id:$id){
  title descriptionHtml productType tags seo{title description}
  metafields(first:60){ edges{ node{ namespace key value } } } } }"""

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--status",default="待确认上线"); ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); store=cfg["shopify_store"]
    rows=[r for r in _lib.bitable_list(cfg)
          if _lib.cell_text(r["fields"].get("内容审核状态"))==a.status
          and _lib.cell_text(r["fields"].get("Shopify Product ID")).strip()]
    if a.limit: rows=rows[:a.limit]
    print(f"待写回(状态={a.status}) {len(rows)} 行")
    done=0
    for r in rows:
        F=r["fields"]; pid=_lib.cell_text(F.get("Shopify Product ID")).strip()
        cur=_lib.shopify(CUR_Q, store, {"id":pid})["product"]
        curmf={f"{m['namespace']}.{m['key']}":m["value"] for m in [e["node"] for e in cur["metafields"]["edges"]]}
        # 组 productUpdate(仅 diff)
        pin={"id":pid}; seo={}; changed=[]
        for col,fld in PU.items():
            v=_lib.cell_text(F.get(col)).strip()
            if v and v!=(cur.get(fld) or "").strip(): pin[fld]=v; changed.append(fld)
        for col,sk in SEO.items():
            v=_lib.cell_text(F.get(col)).strip()
            if v and v!=((cur.get("seo") or {}).get(sk) or "").strip(): seo[sk]=v; changed.append("seo."+sk)
        if seo: pin["seo"]=seo
        tags=_lib.cell_text(F.get("Tags|标签")).strip()
        if tags:
            tl=[t.strip() for t in tags.replace("|",",").split(",") if t.strip()]
            if set(tl)!=set(cur.get("tags") or []): pin["tags"]=tl; changed.append("tags")
        # 组 metafieldsSet(仅 diff)
        mfs=[]
        for col,(ns,key,typ) in MF.items():
            v=_lib.cell_text(F.get(col)).strip()
            if v and v!=(curmf.get(f"{ns}.{key}") or "").strip():
                mfs.append({"ownerId":pid,"namespace":ns,"key":key,"type":typ,"value":v})
        # 上架:DRAFT->ACTIVE
        if cur.get("status")!="ACTIVE": pin["status"]="ACTIVE"; changed.append("status:ACTIVE")
        # 集合归属(读表的目标集合 -> collectionAddProducts)
        want_cols=[]
        for cc in ["目标IP集合","目标品类集合","目标场景集合"]:
            v=F.get(cc)
            if isinstance(v,list): want_cols+=[x.get("text",x.get("name","")) if isinstance(x,dict) else str(x) for x in v]
        title=_lib.cell_text(F.get("商品名称"))[:40]
        if len(pin)<=1 and not mfs and not want_cols:
            print(f"  · {title}: 无变化,跳过"); continue
        print(f"  ✎ {title}: productUpdate={changed} · metafields={[m['key'] for m in mfs]}")
        if a.dry_run: continue
        # 实写
        if len(pin)>1:
            r1=_lib.shopify("mutation($p:ProductInput!){ productUpdate(input:$p){ userErrors{field message} } }", store, {"p":pin}, allow_mutations=True)
            ue=r1["productUpdate"]["userErrors"]
            if ue: print("    ⚠️productUpdate err:",ue); 
        if mfs:
            r2=_lib.shopify("mutation($m:[MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ userErrors{field message} } }", store, {"m":mfs}, allow_mutations=True)
            ue=r2["metafieldsSet"]["userErrors"]
            if ue: print("    ⚠️metafieldsSet err:",ue)
        # 集合归属
        for h in want_cols:
            cd=_lib.shopify("query($h:String!){ collectionByHandle(handle:$h){ id } }", store, {"h":h})
            cid=(cd.get("collectionByHandle") or {}).get("id")
            if cid:
                rc=_lib.shopify("mutation($id:ID!,$p:[ID!]!){ collectionAddProducts(id:$id, productIds:$p){ userErrors{message} } }", store, {"id":cid,"p":[pid]}, allow_mutations=True)
                ue=rc["collectionAddProducts"]["userErrors"]
                if ue and "automated" not in str(ue).lower(): print(f"    ⚠️集合{h}:",ue)
        # 闭环:回填飞书状态
        app=cfg["feishu"]["app_token"];tbl=cfg["feishu"]["table_id"];prof=cfg["feishu"]["profile"]
        upd={"records":[{"record_id":r["record_id"],"fields":{
            "内容审核状态":"已上线","Shopify写回状态":"成功","Shopify写回时间":int(time.time()*1000)}}]}
        _lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tbl}/records/batch_update", upd, prof)
        done+=1
    if not a.dry_run: print(f"写回完成 {done} 行(已回填:状态=已上线·写回状态=成功·写回时间)")

if __name__=="__main__": main()
