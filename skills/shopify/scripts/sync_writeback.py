#!/usr/bin/env python3
"""sync_writeback:飞书「待确认上线」行 → 写回 Shopify(实体感知)。
   字段级 diff;handle 不写回;写完回填状态=已上线。运行=同事「确认上线」闸。
   商品用法: python3 sync_writeback.py --inventory-policy 'PRODUCT_ID=CONTINUE|DENY'
   批量商品须逐个重复传入;库存策略无默认值。"""
import sys, os, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
from entities import ENTITIES

INVENTORY_POLICIES = {"CONTINUE", "DENY"}
INVENTORY_POLICY_MUTATION = """mutation($productId:ID!,$variants:[ProductVariantsBulkInput!]!){
  productVariantsBulkUpdate(productId:$productId,variants:$variants){
    productVariants{ id inventoryPolicy }
    userErrors{ field message }
  }
}"""


def parse_inventory_policy_args(values):
    """解析逐商品库存策略；空输入表示尚未确认，不代表任何默认策略。"""
    choices = {}
    for raw in values:
        product_id, sep, policy = raw.rpartition("=")
        product_id = product_id.strip()
        policy = policy.strip().upper()
        if not sep or not product_id or policy not in INVENTORY_POLICIES:
            raise ValueError(
                "库存策略格式必须是 PRODUCT_ID=CONTINUE 或 PRODUCT_ID=DENY；"
                "CONTINUE 或 DENY 必须由用户明确选择"
            )
        if product_id in choices and choices[product_id] != policy:
            raise ValueError(f"{product_id} 的库存策略重复且冲突")
        choices[product_id] = policy
    return choices


def missing_inventory_policy_ids(product_ids, choices):
    return [product_id for product_id in product_ids if product_id not in choices]


def variant_policy_updates(variants, confirmed_policy):
    if confirmed_policy not in INVENTORY_POLICIES:
        raise ValueError("库存策略只能是 CONTINUE 或 DENY")
    return [
        {"id": variant["id"], "inventoryPolicy": confirmed_policy}
        for variant in variants
        if variant.get("inventoryPolicy") != confirmed_policy
    ]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--entity",default="product",choices=list(ENTITIES.keys()))
    ap.add_argument("--status",default="待确认上线"); ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument(
        "--inventory-policy",
        action="append",
        default=[],
        metavar="PRODUCT_ID=CONTINUE|DENY",
        help="商品上架必填；每个待上架商品分别传一次，不提供默认策略",
    )
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg); store=cfg["shopify_store"]
    ent=ENTITIES[a.entity]; wb=ent["wb"]; keyf=ent["key"]
    tid=(cfg.get("entities",{}).get(a.entity,{}) or {}).get("table_id",""); cfg["feishu"]["table_id"]=tid
    rows=[r for r in _lib.bitable_list(cfg)
          if _lib.cell_text(r["fields"].get(ent["status"]))==a.status and _lib.cell_text(r["fields"].get(keyf)).strip()]
    if a.limit: rows=rows[:a.limit]
    print(f"[{a.entity}] 待写回(状态={a.status}) {len(rows)} 行")
    try:
        inventory_policy_choices=parse_inventory_policy_args(a.inventory_policy)
    except ValueError as exc:
        ap.error(str(exc))
    if a.entity=="product" and rows:
        product_ids=[_lib.cell_text(r["fields"].get(keyf)).strip() for r in rows]
        missing=missing_inventory_policy_ids(product_ids,inventory_policy_choices)
        if missing:
            print("⛔ 上架已停止：以下商品尚未由用户确认库存为 0 时的销售策略（不提供默认值）")
            for r in rows:
                oid=_lib.cell_text(r["fields"].get(keyf)).strip()
                if oid in missing:
                    title=_lib.cell_text(r["fields"].get(ent["wb"]["title_field"])) or "(无名商品)"
                    print(f"  · {title[:60]} · {oid} · 请选择 CONTINUE 或 DENY")
            print("确认后逐商品传入：--inventory-policy 'PRODUCT_ID=CONTINUE|DENY'")
            return 2
    app=cfg["feishu"]["app_token"];prof=_lib.feishu_profile(cfg); done=0
    for r in rows:
        F=r["fields"]; oid=_lib.cell_text(F.get(keyf)).strip()
        cur=_lib.shopify(wb["cur_query"], store, {"id":oid})[wb["cur_key"]]
        policy_updates=[]
        confirmed_policy=None
        if a.entity=="product":
            variants=cur["variants"]["nodes"]
            if cur["variants"]["pageInfo"]["hasNextPage"]:
                print(f"  ⚠️ {oid}: 变体超过 250 个，无法安全一次性确认库存策略，已跳过")
                continue
            confirmed_policy=inventory_policy_choices[oid]
            policy_updates=variant_policy_updates(variants,confirmed_policy)
        curmf={f"{m['namespace']}.{m['key']}":m["value"] for m in [e["node"] for e in cur["metafields"]["edges"]]}
        pin={"id":oid}; seo={}; changed=[]
        for col,fld in wb["pu_map"].items():
            v=_lib.cell_text(F.get(col)).strip()
            if v and v!=(cur.get(fld) or "").strip(): pin[fld]=v; changed.append(fld)
        for col,sk in wb["seo_map"].items():
            v=_lib.cell_text(F.get(col)).strip()
            if v and v!=((cur.get("seo") or {}).get(sk) or "").strip(): seo[sk]=v; changed.append("seo."+sk)
        if seo: pin["seo"]=seo
        if wb["tags_field"]:
            tags=_lib.cell_text(F.get(wb["tags_field"])).strip()
            if tags:
                tl=[t.strip() for t in tags.replace("|",",").split(",") if t.strip()]
                if set(tl)!=set(cur.get("tags") or []): pin["tags"]=tl; changed.append("tags")
        if wb["activate"] and cur.get("status")!="ACTIVE": pin["status"]="ACTIVE"; changed.append("status:ACTIVE")
        if wb.get("publish"): pin["isPublished"]=True
        mfs=[]
        for col,(ns,key,typ) in wb["mf_map"].items():
            v=_lib.cell_text(F.get(col)).strip()
            if v and v!=(curmf.get(f"{ns}.{key}") or "").strip():
                mfs.append({"ownerId":oid,"namespace":ns,"key":key,"type":typ,"value":v})
        want_cols=[]
        for cc in wb["target_collections"]:
            v=F.get(cc)
            if isinstance(v,list): want_cols+=[x.get("text",x.get("name","")) if isinstance(x,dict) else str(x) for x in v]
        title=_lib.cell_text(F.get(wb["title_field"]))[:36]
        if len(pin)<=1 and not mfs and not want_cols and not policy_updates: print(f"  · {title}: 无变化,跳过"); continue
        policy_note=(f" · 库存策略={confirmed_policy}"
                     + (f"(更新{len(policy_updates)}个变体)" if policy_updates else "(已一致)")) if confirmed_policy else ""
        print(f"  ✎ {title}: update={changed} · metafields={[m['key'] for m in mfs]}" + (f" · 集合+{want_cols}" if want_cols else "") + policy_note)
        if a.dry_run: continue
        if policy_updates:
            rp=_lib.shopify(INVENTORY_POLICY_MUTATION,store,{"productId":oid,"variants":policy_updates},allow_mutations=True)
            payload=rp["productVariantsBulkUpdate"]; ue=payload["userErrors"]
            returned=payload.get("productVariants") or []
            if ue or len(returned)!=len(policy_updates) or any(v.get("inventoryPolicy")!=confirmed_policy for v in returned):
                print("    ⚠️库存策略写入失败:",ue or "Shopify 返回结果不完整")
                continue
        if len([k for k in pin if k!="id"])>0:
            if wb.get("id_in_input", True): vv={wb.get("var","p"):pin}
            else: vv={"id":pin["id"], wb.get("var","a"):{k:v for k,v in pin.items() if k!="id"}}
            r1=_lib.shopify(wb["update_mutation"], store, vv, allow_mutations=True)
            ue=list(r1.values())[0]["userErrors"]
            if ue: print("    ⚠️update err:",ue)
        if mfs:
            r2=_lib.shopify("mutation($m:[MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ userErrors{field message} } }", store, {"m":mfs}, allow_mutations=True)
            ue=r2["metafieldsSet"]["userErrors"]
            if ue: print("    ⚠️metafieldsSet err:",ue)
        for h in want_cols:
            cd=_lib.shopify("query($h:String!){ collectionByHandle(handle:$h){ id } }", store, {"h":h})
            cid=(cd.get("collectionByHandle") or {}).get("id")
            if cid:
                rc=_lib.shopify("mutation($id:ID!,$p:[ID!]!){ collectionAddProducts(id:$id, productIds:$p){ userErrors{message} } }", store, {"id":cid,"p":[oid]}, allow_mutations=True)
                ue=rc["collectionAddProducts"]["userErrors"]
                if ue and "automated" not in str(ue).lower(): print(f"    ⚠️集合{h}:",ue)
        _lib.lark_post(f"/bitable/v1/apps/{app}/tables/{tid}/records/batch_update",{"records":[{"record_id":r["record_id"],"fields":{ent["status"]:"已上线","Shopify写回状态":"成功","Shopify写回时间":int(time.time()*1000)}}]},prof)
        done+=1
    if not a.dry_run: print(f"写回完成 {done} 行(已回填状态=已上线)")
    return 0

if __name__=="__main__": raise SystemExit(main())
