#!/usr/bin/env python3
"""sync_pull:Shopify 资源 → 飞书表 upsert(实体感知,按 key 幂等)。
   ①镜像总刷 ②内容仅填空 ③新行状态=待补素材。纯读 Shopify。
   用法: python3 sync_pull.py [--entity product|collection] [--all|--status draft] [--dry-run] [--limit N]"""
import sys, os, json, time, argparse, re
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


def product_query_term(entity, product_id, all_records, status):
    if product_id:
        if entity != "product": raise ValueError("--product-id 只适用于 product")
        match=re.fullmatch(r"(?:gid://shopify/Product/)?(\d+)",product_id.strip())
        if not match: raise ValueError("--product-id 必须是 Shopify Product GID 或数字 ID")
        return f"id:{match.group(1)}"
    return "" if all_records else f"status:{status}"


def _select_values(value):
    if not isinstance(value,list): value=[value]
    return sorted(
      str(x.get("text",x.get("name","")) if isinstance(x,dict) else x).strip()
      for x in value if x not in (None,"")
    )


def cell_value_equal(current, desired, ftype):
    if ftype==4: return _select_values(current)==_select_values(desired)
    if ftype in (2,5):
        try: return int(current)==int(desired)
        except (TypeError,ValueError): return False
    if ftype==15:
        if isinstance(current,dict): current=current.get("link") or current.get("text") or ""
        if isinstance(desired,dict): desired=desired.get("link") or desired.get("text") or ""
        return str(current).strip()==str(desired).strip()
    return _lib.cell_text(current).strip()==_lib.cell_text(desired).strip()


def record_patch(mirror, content, current, field_types, sync_date_field, now_ms, mirror_only=False):
    patch={}
    for key,value in mirror.items():
        if key not in field_types: continue
        formatted=fmt(value,field_types.get(key,1))
        if formatted is None:
            if _lib.cell_text(current.get(key)).strip(): patch[key]=None
        elif not cell_value_equal(current.get(key),formatted,field_types.get(key,1)):
            patch[key]=formatted
    if not mirror_only:
        for key,value in content.items():
            if key not in field_types or _lib.cell_text(current.get(key)).strip(): continue
            formatted=fmt(value,field_types.get(key,1))
            if formatted is not None: patch[key]=formatted
    if patch: patch[sync_date_field]=fmt(now_ms,5)
    return patch


def new_record_fields(mirror, content, field_types, workflow_status_field, sync_date_field, now_ms, mirror_only=False):
    fields={}
    source=mirror if mirror_only else {**mirror,**content}
    for key,value in source.items():
        if key not in field_types: continue
        formatted=fmt(value,field_types.get(key,1))
        if formatted is not None: fields[key]=formatted
    if "运营优先级" in field_types: fields["运营优先级"]="待评估"
    if "Shopify写回状态" in field_types: fields["Shopify写回状态"]="未写回"
    if "FAQ JSON校验状态" in field_types: fields["FAQ JSON校验状态"]="待检查"
    fields[workflow_status_field]="待补素材"
    fields[sync_date_field]=fmt(now_ms,5)
    return fields


def _chunks(values, size=200):
    for start in range(0,len(values),size): yield values[start:start+size]


def _require_lark_success(result, action):
    if result.get("code")==0 or result.get("ok") is True: return
    raise RuntimeError(f"{action}失败: {result.get('msg') or result.get('error') or result}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--entity",default="product",choices=list(ENTITIES.keys()))
    ap.add_argument("--all",action="store_true"); ap.add_argument("--status",default="draft")
    ap.add_argument("--product-id",help="只同步一个 Shopify Product GID/数字 ID")
    ap.add_argument("--mirror-only",action="store_true",help="只刷新 Shopify 镜像字段,不填内容字段")
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
    try: query_term=product_query_term(a.entity,a.product_id,a.all,a.status)
    except ValueError as exc: ap.error(str(exc))
    if ent["supports_query"]: q=q % {"q":query_term}
    nodes=[]; cursor=None
    while True:
        d=_lib.shopify(q, store, {"cursor":cursor})
        pg=list(d.values())[0]
        nodes+=[e["node"] for e in pg["edges"]]
        if pg["pageInfo"]["hasNextPage"]: cursor=pg["pageInfo"]["endCursor"]
        else: break
    if a.product_id and (len(nodes)!=1 or nodes[0].get("id")!=f"gid://shopify/Product/{query_term.split(':',1)[1]}"):
        raise RuntimeError(f"未唯一找到商品 {a.product_id}")
    # 现有记录 index by key
    keyf=ent["key"]; recs=_lib.bitable_list(cfg); idmap={}
    for r in recs:
        k=_lib.cell_text(r["fields"].get(keyf)).strip()
        if k: idmap[k]=r
    # 字段类型
    app=cfg["feishu"]["app_token"];prof=_lib.feishu_profile(cfg)
    fd=_lib._lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tid}/fields","--params",'{"page_size":200}'],prof)
    ftype={f["field_name"]:f["type"] for f in (fd.get("data") or {}).get("items",[])}
    creates=[]; updates=[]; now_ms=int(time.time()*1000)
    for n in nodes:
        mirror,content=ent["build"](n,cfg); kv=mirror.get(keyf)
        if kv in idmap:
            cur=idmap[kv]["fields"]
            f=record_patch(mirror,content,cur,ftype,ent["date"],now_ms,a.mirror_only)
            if f: updates.append((idmap[kv]["record_id"], mirror.get(list(content.keys())[0]) or kv, f))
        else:
            f=new_record_fields(mirror,content,ftype,ent["status"],ent["date"],now_ms,a.mirror_only)
            creates.append((kv, f))
    if a.limit: updates=updates[:a.limit]; creates=creates[:a.limit]
    print(f"[{a.entity}] 拉取 {len(nodes)} | 新建 {len(creates)} | 更新 {len(updates)}")
    if a.dry_run:
        for _,f in creates[:10]: print("  [新建]", json.dumps(f,ensure_ascii=False)[:500])
        for _,t,f in updates[:20]: print(f"  [更新] {str(t)[:50]}:", json.dumps(f,ensure_ascii=False)[:500])
        return
    if updates:
        for batch in _chunks(updates):
            r=_lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tid}/records/batch_update",{"records":[{"record_id":rid,"fields":f} for rid,_,f in batch]},prof)
            _require_lark_success(r,"飞书批量更新")
            print("  更新写入:", r.get("code"), "条", len((r.get("data") or {}).get("records",[])))
            if len(updates)>200: time.sleep(0.7)
    if creates:
        for batch in _chunks(creates):
            r=_lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tid}/records/batch_create",{"records":[{"fields":f} for _,f in batch]},prof)
            _require_lark_success(r,"飞书批量新建")
            print("  新建写入:", r.get("code"))
            if len(creates)>200: time.sleep(0.7)

if __name__=="__main__": main()
