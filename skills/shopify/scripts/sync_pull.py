#!/usr/bin/env python3
"""sync_pull:Shopify 资源 → 飞书表 upsert(实体感知,按 key 幂等)。
   ①镜像总刷 ②内容仅填空 ③新行状态=待补素材。纯读 Shopify。
   用法: python3 sync_pull.py [--entity product|collection] [--all|--status draft] [--dry-run] [--limit N]"""
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
from entities import ENTITIES

def fmt(val, ftype):
    if val in ("", None) or val==[]: return None
    if ftype==2: return int(val)
    if ftype==4: return val if isinstance(val,list) else [val]
    if ftype==5: return int(val)
    if ftype==15: return {"link": str(val), "text": str(val)}
    return val

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--entity",default="product",choices=list(ENTITIES.keys()))
    ap.add_argument("--all",action="store_true"); ap.add_argument("--status",default="draft")
    ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg); store=cfg["shopify_store"]
    ent=ENTITIES[a.entity]
    # 该实体的飞书表
    tid=(cfg.get("entities",{}).get(a.entity,{}) or {}).get("table_id","")
    if not tid or "SET_IN" in tid: print(f"❌ config.entities.{a.entity}.table_id 未设"); sys.exit(1)
    cfg["feishu"]["table_id"]=tid
    # 拉 Shopify(分页)
    q=ent["query"]
    if ent["supports_query"]: q=q % {"q":("" if a.all else f"status:{a.status}")}
    nodes=[]; cursor=None
    while True:
        d=_lib.shopify(q, store, {"cursor":cursor})
        pg=list(d.values())[0]
        nodes+=[e["node"] for e in pg["edges"]]
        if pg["pageInfo"]["hasNextPage"]: cursor=pg["pageInfo"]["endCursor"]
        else: break
    # 现有记录 index by key
    keyf=ent["key"]; recs=_lib.bitable_list(cfg); idmap={}
    for r in recs:
        k=_lib.cell_text(r["fields"].get(keyf)).strip()
        if k: idmap[k]=r
    # 字段类型
    app=cfg["feishu"]["app_token"];prof=_lib.feishu_profile(cfg)
    fd=_lib._lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tid}/fields","--params",'{"page_size":200}'],prof)
    ftype={f["field_name"]:f["type"] for f in (fd.get("data") or {}).get("items",[])}
    creates=[]; updates=[]
    for n in nodes:
        mirror,content=ent["build"](n,cfg); kv=mirror.get(keyf)
        if kv in idmap:
            cur=idmap[kv]["fields"]; f={}
            for k,val in mirror.items():
                fv=fmt(val,ftype.get(k,1))
                if fv is not None: f[k]=fv
            for k,val in content.items():
                if not _lib.cell_text(cur.get(k)).strip():
                    fv=fmt(val,ftype.get(k,1))
                    if fv is not None: f[k]=fv
            f[ent["date"]]=fmt(int(time.time()*1000),5)
            updates.append((idmap[kv]["record_id"], mirror.get(list(content.keys())[0]) or kv, f))
        else:
            f={}
            for k,val in {**mirror,**content}.items():
                fv=fmt(val,ftype.get(k,1))
                if fv is not None: f[k]=fv
            f[ent["status"]]="待补素材"; f[ent["date"]]=fmt(int(time.time()*1000),5)
            creates.append((kv, f))
    if a.limit: updates=updates[:a.limit]; creates=creates[:a.limit]
    print(f"[{a.entity}] 拉取 {len(nodes)} | 新建 {len(creates)} | 更新 {len(updates)}")
    if a.dry_run:
        for _,f in creates[:2]: print("  [新建]", json.dumps({k:f[k] for k in list(f)[:5]},ensure_ascii=False)[:150])
        for _,t,f in updates[:2]: print("  [更新] 填空:", json.dumps({k:v for k,v in f.items() if not k.startswith(('最近','Shopify写回'))},ensure_ascii=False)[:150])
        return
    if updates:
        r=_lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tid}/records/batch_update",{"records":[{"record_id":rid,"fields":f} for rid,_,f in updates]},prof)
        print("  更新写入:", r.get("code"), "条", len((r.get("data") or {}).get("records",[])))
    if creates:
        r=_lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tid}/records/batch_create",{"records":[{"fields":f} for _,f in creates]},prof)
        print("  新建写入:", r.get("code"))

if __name__=="__main__": main()
