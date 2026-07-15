#!/usr/bin/env python3
"""sync_pull:Shopify 商品 → 飞书表 upsert(按 Product ID 幂等)。
   ①镜像字段总是刷新;②内容字段仅填空不覆盖;新草稿状态=待补素材。纯读 Shopify。
   用法: python3 sync_pull.py [--all|--status draft] [--dry-run] [--skill-dir PATH]"""
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

PROD_Q = """query($cursor:String){ products(first:50, query:"%s", after:$cursor){
  edges{ cursor node{
    id handle onlineStoreUrl status vendor
    title descriptionHtml seo{ title description }
    featuredImage{ url }
    variants(first:100){ edges{ node{ sku price inventoryQuantity } } }
    collections(first:30){ edges{ node{ handle } } }
    metafields(first:60){ edges{ node{ namespace key value } } }
  } } pageInfo{ hasNextPage endCursor } } }"""

MF = {  # 飞书列名 -> shopify metafield namespace.key
 "custom.material 材质":"custom.material","custom.height_cm 高度":"custom.height_cm",
 "custom.box_size_cm 单盒尺寸：长|宽|高":"custom.box_size","custom.hidden_odds 隐藏款概率":"custom.hidden_odds",
 "custom.series 系列":"custom.series","custom.scenario_copy 场景文案":"custom.scenario_copy","custom.faq 常见问题":"custom.faq"}

def build(node, cfg):
    v=[e["node"] for e in node["variants"]["edges"]]
    prices=[float(x["price"]) for x in v if x.get("price")]
    cols=[e["node"]["handle"] for e in node["collections"]["edges"]]
    cc=cfg.get("collections",{})
    mfv={f"{m['namespace']}.{m['key']}":m["value"] for m in [e["node"] for e in node["metafields"]["edges"]]}
    mirror={
      "Shopify Product ID": node["id"], "Handle短名URL": node["handle"],
      "商品URL": node.get("onlineStoreUrl") or "", "状态": node["status"], "Vendor": node.get("vendor") or "",
      "变体数": len(v), "SKU汇总": ", ".join(x["sku"] for x in v if x.get("sku")),
      "价格区间USD": (f"{min(prices):g}-{max(prices):g}" if prices else ""),
      "总库存": sum(int(x.get("inventoryQuantity") or 0) for x in v),
      "变体摘要": " , ".join(f"SKU:{x.get('sku','')}/${x.get('price','')}/stock{x.get('inventoryQuantity',0)}" for x in v),
      "主图URL": (node.get("featuredImage") or {}).get("url","") }
    content={
      "商品名称": node.get("title") or "", "商品描述EN": node.get("descriptionHtml") or "",
      "SEO Title EN": (node.get("seo") or {}).get("title") or "", "SEO描述EN": (node.get("seo") or {}).get("description") or "",
      "目标IP集合": [c for c in cols if c in cc.get("ip",[])],
      "目标品类集合": [c for c in cols if c in cc.get("category",[])],
      "目标场景集合": [c for c in cols if c in cc.get("scenario",[])] }
    for col,key in MF.items(): content[col]=mfv.get(key,"")
    return mirror, content

def fmt(val, ftype):
    if val in ("", None) or val==[]: return None      # 空值 -> None(调用处跳过)
    if ftype==2: return int(val)
    if ftype==4: return val if isinstance(val,list) else [val]
    if ftype==5: return int(val)
    if ftype==15: return {"link": str(val), "text": str(val)}  # URL 字段要对象
    return val  # 1/3 文本/单选

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--all",action="store_true"); ap.add_argument("--status",default="draft")
    ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--limit",type=int,default=0); ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg); store=cfg["shopify_store"]
    q=PROD_Q % ("" if a.all else f"status:{a.status}")
    # 拉全部商品(分页)
    nodes=[]; cursor=None
    while True:
        d=_lib.shopify(q, store, {"cursor":cursor}); pg=d["products"]
        nodes+=[e["node"] for e in pg["edges"]]
        if pg["pageInfo"]["hasNextPage"]: cursor=pg["pageInfo"]["endCursor"]
        else: break
    # 现有记录 index by Product ID
    recs=_lib.bitable_list(cfg)
    idmap={}
    for r in recs:
        pid=_lib.cell_text(r["fields"].get("Shopify Product ID")).strip()
        if pid: idmap[pid]=r
    # 字段类型
    app=cfg["feishu"]["app_token"];tbl=cfg["feishu"]["table_id"];prof=cfg["feishu"]["profile"]
    fd=_lib._lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tbl}/fields","--params",'{"page_size":200}'],prof)
    ftype={f["field_name"]:f["type"] for f in (fd.get("data") or {}).get("items",[])}
    creates=[]; updates=[]
    for n in nodes:
        pid=n["id"]; mirror,content=build(n,cfg)
        if pid in idmap:  # update: mirror 总刷 + content 仅填空
            cur=idmap[pid]["fields"]; f={}
            for k,val in mirror.items():
                fv=fmt(val,ftype.get(k,1))
                if fv is not None: f[k]=fv
            for k,val in content.items():
                if not _lib.cell_text(cur.get(k)).strip():
                    fv=fmt(val,ftype.get(k,1))
                    if fv is not None: f[k]=fv
            f["最近Shopify同步日期"]=fmt(int(time.time()*1000),5)
            updates.append((idmap[pid]["record_id"], n.get("title"), f))
        else:  # create
            f={}
            for k,val in {**mirror,**content}.items():
                fv=fmt(val,ftype.get(k,1))
                if fv is not None: f[k]=fv
            f["内容审核状态"]="待补素材"; f["最近Shopify同步日期"]=fmt(int(time.time()*1000),5)
            creates.append((n.get("title"), f))
    print(f"拉取商品 {len(nodes)} | 新建 {len(creates)} | 更新 {len(updates)}")
    if a.dry_run:
        print("\n=== DRY-RUN(不写入)===")
        for t,f in creates[:3]: print(f"  [新建] {t}\n     {json.dumps({k:f[k] for k in list(f)[:6]},ensure_ascii=False)}")
        for rid,t,f in updates[:3]:
            filled={k:v for k,v in f.items() if k.startswith('目标') or k.startswith('custom')}
            print(f"  [更新] {t}  会填空的内容字段: {json.dumps(filled,ensure_ascii=False)[:160]}")
        return
    # 实写
    app=cfg["feishu"]["app_token"];tbl=cfg["feishu"]["table_id"];prof=cfg["feishu"]["profile"]
    up=updates[:a.limit] if a.limit else updates
    cr=creates[:a.limit] if a.limit else creates
    if up:
        payload={"records":[{"record_id":rid,"fields":f} for rid,_,f in up]}
        r=_lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tbl}/records/batch_update", payload, prof)
        print("更新写入:", r.get("code"), r.get("msg"), "条数", len((r.get("data") or {}).get("records",[])))
    if cr:
        payload={"records":[{"fields":f} for _,f in cr]}
        r=_lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tbl}/records/batch_create", payload, prof)
        print("新建写入:", r.get("code"), r.get("msg"))

if __name__=="__main__": main()
