#!/usr/bin/env python3
"""sync_writeback:飞书「待确认上线」行 → 写回 Shopify(实体感知)。
   字段级 diff;handle 不写回;写完回填状态=已上线。运行=同事「确认上线」闸。
   商品用法: python3 sync_writeback.py --inventory-policy 'PRODUCT_ID=CONTINUE|DENY'
   批量商品须逐个重复传入;库存策略无默认值。"""
import sys, os, time, argparse, re, json, subprocess, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
from entities import ENTITIES, PRODUCT_QUERY, build_product
from qa import faq_json_issues, faq_status_patch, product_priority_issues
from sync_pull import product_query_term, record_patch

INVENTORY_POLICIES = {"CONTINUE", "DENY"}
ONLINE_STORE_APP_ID = "gid://shopify/App/580111"
INVENTORY_POLICY_MUTATION = """mutation($productId:ID!,$variants:[ProductVariantsBulkInput!]!){
  productVariantsBulkUpdate(productId:$productId,variants:$variants){
    productVariants{ id inventoryPolicy }
    userErrors{ field message }
  }
}"""
SELLABILITY_PROFILE_QUERY = """query($id:ID!){
  deliveryProfile(id:$id){ id name
    profileItems(first:250){ nodes{ product{ id } variants(first:250){ nodes{ id } pageInfo{ hasNextPage } } } pageInfo{ hasNextPage } }
    profileLocationGroups{
      locationGroup{ locations(first:50){ nodes{ id name isActive fulfillsOnlineOrders } pageInfo{ hasNextPage } } }
      locationGroupZones(first:50){ nodes{
        zone{ id name countries{ code{ countryCode restOfWorld } } }
        methodDefinitions(first:50){ nodes{ id active } pageInfo{ hasNextPage } }
      } pageInfo{ hasNextPage } }
    }
  }
}"""
SELLABILITY_PRODUCT_QUERY = """query($id:ID!){ product(id:$id){ id handle status onlineStoreUrl
  variants(first:250){ nodes{ id sku inventoryPolicy sellableOnlineQuantity
    inventoryItem{ id tracked requiresShipping inventoryLevels(first:50){
      nodes{ location{ id name isActive fulfillsOnlineOrders } quantities(names:[\"available\"]){ name quantity } }
      pageInfo{ hasNextPage }
    } }
  } pageInfo{ hasNextPage } }
} }"""
DELIVERY_PROFILE_ASSOCIATE_MUTATION = """mutation($id:ID!,$variantIds:[ID!]!){
  deliveryProfileUpdate(id:$id,profile:{variantsToAssociate:$variantIds}){
    profile{ id name }
    userErrors{ field message }
  }
}"""


def _connection_nodes(connection):
    return ((connection or {}).get("nodes") or [])


def _quantity_value(level, name="available"):
    for quantity in (level or {}).get("quantities") or []:
        if quantity.get("name") == name:
            return quantity.get("quantity") or 0
    return 0


def shipping_profile_issues(profile, product, required_country_codes):
    """验证商品变体、履约仓、运费区和库存是否形成区域可售闭环。"""
    issues=[]; profile=profile or {}; product=product or {}
    product_id=product.get("id")
    variants=_connection_nodes(product.get("variants"))
    variant_ids={variant.get("id") for variant in variants if variant.get("id")}
    items=profile.get("profileItems") or {}
    if (items.get("pageInfo") or {}).get("hasNextPage"):
        issues.append("配送方案商品超过 250 个，无法完整验证")
    item=next(
        (candidate for candidate in _connection_nodes(items)
         if (candidate.get("product") or {}).get("id")==product_id),
        None,
    )
    attached_ids=set()
    if item:
        item_variants=item.get("variants") or {}
        if (item_variants.get("pageInfo") or {}).get("hasNextPage"):
            issues.append("商品变体超过 250 个，无法完整验证配送方案")
        attached_ids={node.get("id") for node in _connection_nodes(item_variants)}
    for variant_id in sorted(variant_ids-attached_ids):
        issues.append(f"{variant_id} 未关联当前配送方案")
    for variant in variants:
        if (variant.get("inventoryPolicy")=="DENY"
                and (variant.get("sellableOnlineQuantity") or 0)<=0):
            issues.append(
                f"{variant.get('id') or '未知变体'} sellableOnlineQuantity<=0"
            )

    eligible_locations={str(code).upper():set() for code in required_country_codes}
    for group in profile.get("profileLocationGroups") or []:
        locations=(group.get("locationGroup") or {}).get("locations") or {}
        if (locations.get("pageInfo") or {}).get("hasNextPage"):
            issues.append("配送方案仓库超过 50 个，无法完整验证")
        online_location_ids={
            location.get("id") for location in _connection_nodes(locations)
            if location.get("id") and location.get("isActive")
            and location.get("fulfillsOnlineOrders")
        }
        zones=group.get("locationGroupZones") or {}
        if (zones.get("pageInfo") or {}).get("hasNextPage"):
            issues.append("配送区域超过 50 个，无法完整验证")
        for group_zone in _connection_nodes(zones):
            methods=group_zone.get("methodDefinitions") or {}
            if (methods.get("pageInfo") or {}).get("hasNextPage"):
                issues.append("区域运费方式超过 50 个，无法完整验证")
            if not any(method.get("active") for method in _connection_nodes(methods)):
                continue
            for country in (group_zone.get("zone") or {}).get("countries") or []:
                code=(country.get("code") or {}).get("countryCode")
                code=str(code or "").upper()
                if code in eligible_locations:
                    eligible_locations[code].update(online_location_ids)

    for country_code, location_ids in eligible_locations.items():
        if not location_ids:
            issues.append(f"{country_code} 没有启用运费方式的线上履约仓")
            continue
        for variant in variants:
            variant_id=variant.get("id") or "未知变体"
            item_data=variant.get("inventoryItem") or {}
            levels=item_data.get("inventoryLevels") or {}
            if (levels.get("pageInfo") or {}).get("hasNextPage"):
                issues.append(f"{variant_id} 库存地点超过 50 个，无法完整验证")
                continue
            matching_levels=[
                level for level in _connection_nodes(levels)
                if ((level.get("location") or {}).get("id") in location_ids)
            ]
            if not matching_levels:
                issues.append(f"{variant_id} 在 {country_code} 可履约仓没有库存记录")
            elif variant.get("inventoryPolicy")=="DENY" and not any(
                _quantity_value(level)>0 for level in matching_levels
            ):
                issues.append(f"{variant_id} 在 {country_code} 可履约仓没有正库存")
    return list(dict.fromkeys(issues))


def storefront_sellability_issues(payload, expected_variant_ids):
    """验证区域 storefront 商品 JSON 中每个目标变体都真实可售。"""
    payload=payload or {}; issues=[]
    expected={str(variant_id).rsplit("/",1)[-1]:variant_id for variant_id in expected_variant_ids}
    actual={str(variant.get("id")):variant for variant in payload.get("variants") or []}
    for numeric_id,variant_id in expected.items():
        variant=actual.get(numeric_id)
        if not variant:
            issues.append(f"{variant_id} 未出现在区域商品 JSON")
        elif variant.get("available") is not True:
            issues.append(f"{variant_id} 区域前台 available=false")
    if expected and payload.get("available") is not True:
        issues.append("区域商品整体 available=false")
    return issues


def delivery_profile_variant_ids_to_associate(profile, product):
    """返回尚未关联到目标配送方案的变体 ID。"""
    product=product or {}; profile=profile or {}; product_id=product.get("id")
    expected=[
        variant.get("id") for variant in _connection_nodes(product.get("variants"))
        if variant.get("id")
    ]
    item=next(
        (candidate for candidate in _connection_nodes(profile.get("profileItems"))
         if (candidate.get("product") or {}).get("id")==product_id),
        None,
    )
    attached={
        node.get("id") for node in _connection_nodes((item or {}).get("variants"))
        if node.get("id")
    }
    return [variant_id for variant_id in expected if variant_id not in attached]


def storefront_product_json_url(primary_domain, path_prefix, handle):
    domain=str(primary_domain or "").strip().strip("/")
    prefix=str(path_prefix or "").strip().strip("/")
    encoded_handle=urllib.parse.quote(str(handle or "").strip(), safe="-")
    path=(f"/{prefix}" if prefix else "")+f"/products/{encoded_handle}.js"
    return f"https://{domain}{path}"


def fetch_storefront_product_json(url, runner=subprocess.run):
    """用系统 CA 链读取公开商品 JSON，避免 Python 本地证书链假失败。"""
    result=runner(
        ["curl","-fsSL","--max-time","20","-A","Funcinating-Shopify-Skill/1.0",url],
        capture_output=True,text=True,
    )
    if result.returncode:
        detail=(result.stderr or result.stdout or "curl failed").strip()[:500]
        raise RuntimeError(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"区域商品 JSON 无法解析: {exc}") from exc

IMAGE_TAG_RE = re.compile(r"<img\b", re.IGNORECASE)
MARKDOWN_IMAGE_SOURCE_RE = re.compile(
    r"\b(?:src|srcset)\s*=\s*([\"'])\s*\[https?://",
    re.IGNORECASE,
)


def description_html_issues(desired_html, current_html):
    """阻止坏图片地址或详情图数量倒退的 descriptionHtml 写回。"""
    desired=desired_html or ""; current=current_html or ""; issues=[]
    if MARKDOWN_IMAGE_SOURCE_RE.search(desired):
        issues.append("商品描述包含 Markdown 包裹的图片 src/srcset")
    desired_count=len(IMAGE_TAG_RE.findall(desired))
    current_count=len(IMAGE_TAG_RE.findall(current))
    if desired_count < current_count:
        issues.append(f"商品描述图片数量将从 {current_count} 降为 {desired_count}")
    return issues


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


def stable_unique(values):
    """按首次出现顺序去重，避免同一集合由多个业务维度重复写入。"""
    return list(dict.fromkeys(values))


def normalize_collection_handles(values):
    """Shopify handle 不区分展示大小写，写回与回读统一按小写比较。"""
    return stable_unique(str(value).strip().lower() for value in values if str(value).strip())


def shopify_html_equivalent(desired, returned):
    """忽略 Shopify 在相邻标签之间自动加入的格式化空白。"""
    normalize=lambda value: re.sub(r">\s+<", "><", value or "").strip()
    return normalize(desired)==normalize(returned)


def mutation_user_errors(payload):
    errors=[]
    for error in (payload or {}).get("userErrors") or []:
        field=error.get("field") or []
        if isinstance(field,list): field=".".join(str(part) for part in field)
        prefix=f"{field}: " if field else ""
        errors.append(prefix+(error.get("message") or "unknown Shopify user error"))
    return errors


def online_store_publication_id(publications):
    for publication in publications or []:
        app=publication.get("app") or {}
        if app.get("id")==ONLINE_STORE_APP_ID:
            return publication.get("id")
    for publication in publications or []:
        app=publication.get("app") or {}
        if (publication.get("name") or "").strip().lower() in {"online store","在线商店"}:
            return publication.get("id")
        if (app.get("title") or "").strip().lower() in {"online store","在线商店"}:
            return publication.get("id")
    return None


def publish_product_to_online_store(store, product_id):
    data=_lib.shopify(
        "{ publications(first:50){ nodes{ id name app{ id title } } } }",
        store,
    )
    publication_id=online_store_publication_id((data.get("publications") or {}).get("nodes"))
    if not publication_id:
        return ["无法唯一识别 Online Store publication"]
    result=_lib.shopify(
        "mutation($id:ID!,$input:[PublicationInput!]!){ publishablePublish(id:$id,input:$input){ userErrors{field message} } }",
        store,
        {"id":product_id,"input":[{"publicationId":publication_id}]},
        allow_mutations=True,
    )
    return mutation_user_errors(result.get("publishablePublish"))


def _variant_nodes(product):
    variants=(product or {}).get("variants") or {}
    if "edges" in variants: return [edge["node"] for edge in variants.get("edges") or []]
    return variants.get("nodes") or []


def product_readback_issues(
    product, confirmed_policy, product_input=None, metafields=None,
    wanted_collections=None, expected_status="ACTIVE", require_online_url=True,
):
    issues=[]; product=product or {}
    if product.get("status")!=expected_status: issues.append(f"状态不是 {expected_status}: {product.get('status')}")
    if require_online_url and not product.get("onlineStoreUrl"): issues.append("商品URL为空")
    for variant in _variant_nodes(product):
        if variant.get("inventoryPolicy")!=confirmed_policy:
            issues.append(f"{variant.get('id')} inventoryPolicy={variant.get('inventoryPolicy')} != {confirmed_policy}")
    expected=product_input or {}
    if "title" in expected and product.get("title")!=expected["title"]:
        issues.append("title 回读不一致")
    if "descriptionHtml" in expected and not shopify_html_equivalent(
        expected["descriptionHtml"], product.get("descriptionHtml")
    ):
        issues.append("descriptionHtml 回读不一致")
    if "tags" in expected and set(product.get("tags") or [])!=set(expected["tags"]): issues.append("tags 回读不一致")
    for key,value in (expected.get("seo") or {}).items():
        if (product.get("seo") or {}).get(key)!=value: issues.append(f"seo.{key} 回读不一致")
    current_mf={f"{m['namespace']}.{m['key']}":m.get("value") for m in [e["node"] for e in ((product.get("metafields") or {}).get("edges") or [])]}
    for item in metafields or []:
        if current_mf.get(f"{item['namespace']}.{item['key']}")!=item["value"]: issues.append(f"metafield {item['key']} 回读不一致")
    current_cols={e["node"]["handle"] for e in ((product.get("collections") or {}).get("edges") or [])}
    missing=sorted(set(wanted_collections or [])-current_cols)
    if missing: issues.append("集合缺失: "+", ".join(missing))
    return issues


def writeback_result_fields(success, error, now_ms, prepared_draft=False):
    if success:
        if prepared_draft:
            return {"Shopify写回状态":"已写回","Shopify写回时间":now_ms,"写回错误信息":""}
        return {"内容审核状态":"已上线","Shopify写回状态":"成功","Shopify写回时间":now_ms,"写回错误信息":""}
    return {"Shopify写回状态":"失败","写回错误信息":error}


def product_prewrite_issues(fields):
    """商品写回的最后硬闸；直接执行 sync_writeback 也不能绕过 QA。"""
    issues=list(product_priority_issues(fields))
    if not _lib.cell_text(fields.get("资料来源|官方依据")).strip():
        issues.append("资料来源|官方依据")
    issues.extend(f"FAQ: {issue}" for issue in faq_json_issues(fields.get("custom.faq 常见问题")))
    return issues


def read_product_node(store, product_id):
    term=product_query_term("product",product_id,False,"draft")
    data=_lib.shopify(PRODUCT_QUERY % {"q":term},store,{"cursor":None})
    edges=(data.get("products") or {}).get("edges") or []
    matches=[edge["node"] for edge in edges if edge["node"].get("id")==product_id]
    if len(matches)!=1: raise RuntimeError(f"写后无法唯一回读 {product_id}")
    return matches[0]


def product_mirror_patch(product, cfg, current_fields, field_types, sync_date_field, now_ms):
    mirror,_=build_product(product,cfg)
    patch=record_patch(mirror,{},current_fields,field_types,sync_date_field,now_ms,True)
    patch[sync_date_field]=now_ms
    return patch


def update_lark_row(app, table_id, record_id, fields, profile):
    result=_lib.lark_post(
      f"/bitable/v1/apps/{app}/tables/{table_id}/records/batch_update",
      {"records":[{"record_id":record_id,"fields":fields}]},profile)
    if result.get("code")!=0 and result.get("ok") is not True:
        raise RuntimeError(f"飞书回填失败: {result.get('msg') or result.get('error') or result}")
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--entity",default="product",choices=list(ENTITIES.keys()))
    ap.add_argument("--status",default="待确认上线"); ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--prepare-draft",action="store_true",help="写入内容但保持商品 DRAFT，不回填已上线")
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
    sellability_cfg=cfg.get("sellability") or {}
    if a.entity=="product" and rows:
        missing_sellability_config=[]
        if not sellability_cfg.get("delivery_profile_id"):
            missing_sellability_config.append("sellability.delivery_profile_id")
        if not sellability_cfg.get("required_country_codes"):
            missing_sellability_config.append("sellability.required_country_codes")
        if not sellability_cfg.get("storefront_checks"):
            missing_sellability_config.append("sellability.storefront_checks")
        if missing_sellability_config:
            print("⛔ 上架已停止：缺少区域可售门禁配置 · "+", ".join(missing_sellability_config))
            return 2
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
    fd=_lib._lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tid}/fields","--params",'{"page_size":200}'],prof)
    field_types={f["field_name"]:f["type"] for f in (fd.get("data") or {}).get("items",[])}
    for r in rows:
        F=r["fields"]; oid=_lib.cell_text(F.get(keyf)).strip()
        cur=_lib.shopify(wb["cur_query"], store, {"id":oid})[wb["cur_key"]]
        if a.entity=="product" and a.prepare_draft and cur.get("status")!="DRAFT":
            print(f"  ⛔ {oid}: --prepare-draft 只允许当前状态为 DRAFT，实际为 {cur.get('status')}")
            continue
        policy_updates=[]
        confirmed_policy=None
        if a.entity=="product":
            variants=cur["variants"]["nodes"]
            if cur["variants"]["pageInfo"]["hasNextPage"]:
                print(f"  ⚠️ {oid}: 变体超过 250 个，无法安全一次性确认库存策略，已跳过")
                continue
            confirmed_policy=inventory_policy_choices[oid]
            policy_updates=variant_policy_updates(variants,confirmed_policy)
            target_profile_id=sellability_cfg["delivery_profile_id"]
            target_profile=(_lib.shopify(
                SELLABILITY_PROFILE_QUERY,store,{"id":target_profile_id}
            ).get("deliveryProfile"))
            if not target_profile:
                print(f"  ⛔ {oid}: 目标配送方案不存在 · {target_profile_id}")
                continue
            delivery_variant_ids=delivery_profile_variant_ids_to_associate(
                target_profile,{"id":oid,"variants":{"nodes":variants}}
            )
        curmf={f"{m['namespace']}.{m['key']}":m["value"] for m in [e["node"] for e in cur["metafields"]["edges"]]}
        pin={"id":oid}; seo={}; changed=[]
        for col,fld in wb["pu_map"].items():
            v=_lib.cell_text(F.get(col)).strip()
            same=(shopify_html_equivalent(v,cur.get(fld)) if fld=="descriptionHtml"
                  else v==(cur.get(fld) or "").strip())
            if v and not same: pin[fld]=v; changed.append(fld)
        for col,sk in wb["seo_map"].items():
            v=_lib.cell_text(F.get(col)).strip()
            if v and v!=((cur.get("seo") or {}).get(sk) or "").strip(): seo[sk]=v; changed.append("seo."+sk)
        if seo: pin["seo"]=seo
        if wb["tags_field"]:
            tags=_lib.cell_text(F.get(wb["tags_field"])).strip()
            if tags:
                tl=[t.strip() for t in tags.replace("|",",").split(",") if t.strip()]
                if set(tl)!=set(cur.get("tags") or []): pin["tags"]=tl; changed.append("tags")
        if wb["activate"] and not a.prepare_draft and cur.get("status")!="ACTIVE": pin["status"]="ACTIVE"; changed.append("status:ACTIVE")
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
        want_cols=normalize_collection_handles(want_cols)
        current_cols={e["node"]["handle"] for e in ((cur.get("collections") or {}).get("edges") or [])}
        add_cols=[handle for handle in want_cols if handle not in current_cols]
        title=_lib.cell_text(F.get(wb["title_field"]))[:36]
        description_errors=[]
        if a.entity=="product":
            desired_description=_lib.cell_text(F.get("商品描述EN")).strip()
            if desired_description:
                description_errors=description_html_issues(
                    desired_description,
                    cur.get("descriptionHtml") or "",
                )
        if description_errors:
            message="; ".join(description_errors)
            print(f"  ⛔ {title}: 写回前描述安全检查失败 · {message}")
            if not a.dry_run:
                failure_patch=writeback_result_fields(False,message,int(time.time()*1000))
                if a.entity=="product": failure_patch.update(faq_status_patch(F))
                update_lark_row(
                    app,tid,r["record_id"],
                    failure_patch,prof,
                )
            continue
        prewrite_errors=product_prewrite_issues(F) if a.entity=="product" else []
        if prewrite_errors:
            message="上线前硬检查失败: "+"; ".join(prewrite_errors)
            print(f"  ⛔ {title}: {message}")
            if not a.dry_run:
                failure_patch=writeback_result_fields(False,message,int(time.time()*1000))
                failure_patch.update(faq_status_patch(F))
                update_lark_row(app,tid,r["record_id"],failure_patch,prof)
            continue
        policy_note=(f" · 库存策略={confirmed_policy}"
                     + (f"(更新{len(policy_updates)}个变体)" if policy_updates else "(已一致)")) if confirmed_policy else ""
        shipping_note=(f" · 配送方案+{len(delivery_variant_ids)}个变体"
                       if a.entity=="product" and delivery_variant_ids
                       else (" · 配送方案已一致" if a.entity=="product" else ""))
        print(f"  ✎ {title}: update={changed} · metafields={[m['key'] for m in mfs]}" + (f" · 集合+{add_cols}" if add_cols else "") + policy_note + shipping_note + " · 写后回读")
        if a.dry_run: continue
        errors=[]
        try:
            if a.entity=="product" and delivery_variant_ids:
                rd=_lib.shopify(
                    DELIVERY_PROFILE_ASSOCIATE_MUTATION,store,
                    {"id":target_profile_id,"variantIds":delivery_variant_ids},
                    allow_mutations=True,
                )
                errors+=mutation_user_errors(rd.get("deliveryProfileUpdate"))
            if not errors and policy_updates:
                rp=_lib.shopify(INVENTORY_POLICY_MUTATION,store,{"productId":oid,"variants":policy_updates},allow_mutations=True)
                payload=rp["productVariantsBulkUpdate"]; errors+=mutation_user_errors(payload)
                returned=payload.get("productVariants") or []
                if len(returned)!=len(policy_updates) or any(v.get("inventoryPolicy")!=confirmed_policy for v in returned):
                    errors.append("库存策略写入结果不完整")
            if not errors and len([k for k in pin if k!="id"])>0:
                if wb.get("id_in_input", True): vv={wb.get("var","p"):pin}
                else: vv={"id":pin["id"], wb.get("var","a"):{k:v for k,v in pin.items() if k!="id"}}
                r1=_lib.shopify(wb["update_mutation"], store, vv, allow_mutations=True)
                errors+=mutation_user_errors(list(r1.values())[0])
            if not errors and mfs:
                r2=_lib.shopify("mutation($m:[MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ userErrors{field message} } }", store, {"m":mfs}, allow_mutations=True)
                errors+=mutation_user_errors(r2["metafieldsSet"])
            if not errors:
                for h in add_cols:
                    cd=_lib.shopify("query($h:String!){ collectionByHandle(handle:$h){ id } }", store, {"h":h})
                    cid=(cd.get("collectionByHandle") or {}).get("id")
                    if not cid:
                        errors.append(f"集合不存在: {h}"); break
                    rc=_lib.shopify("mutation($id:ID!,$p:[ID!]!){ collectionAddProducts(id:$id, productIds:$p){ userErrors{field message} } }", store, {"id":cid,"p":[oid]}, allow_mutations=True)
                    collection_errors=mutation_user_errors(rc["collectionAddProducts"])
                    if collection_errors and "automated" not in " ".join(collection_errors).lower():
                        errors+=collection_errors; break
            if not errors and a.entity=="product" and not a.prepare_draft and not cur.get("onlineStoreUrl"):
                errors+=publish_product_to_online_store(store,oid)
            now_ms=int(time.time()*1000)
            patch={}
            if not errors and a.entity=="product":
                live=read_product_node(store,oid)
                errors+=product_readback_issues(
                    live, confirmed_policy, pin, mfs, want_cols,
                    expected_status="DRAFT" if a.prepare_draft else "ACTIVE",
                    require_online_url=not a.prepare_draft,
                )
                if not errors:
                    sellability_product=(_lib.shopify(
                        SELLABILITY_PRODUCT_QUERY,store,{"id":oid}
                    ).get("product"))
                    sellability_profile=(_lib.shopify(
                        SELLABILITY_PROFILE_QUERY,store,{"id":target_profile_id}
                    ).get("deliveryProfile"))
                    if not sellability_product:
                        errors.append("可售性回读找不到商品")
                    if not sellability_profile:
                        errors.append("可售性回读找不到目标配送方案")
                    if not errors:
                        backend_issues=shipping_profile_issues(
                            sellability_profile,
                            sellability_product,
                            sellability_cfg["required_country_codes"],
                        )
                        errors += ["区域履约门禁: "+issue for issue in backend_issues]
                if not errors and not a.prepare_draft:
                    variant_ids=[
                        variant.get("id")
                        for variant in _connection_nodes(sellability_product.get("variants"))
                        if variant.get("id")
                    ]
                    attempts=max(1,int(sellability_cfg.get("retry_attempts",3)))
                    delay=max(0,float(sellability_cfg.get("retry_delay_seconds",3)))
                    for check in sellability_cfg["storefront_checks"]:
                        country_code=str(check.get("country_code") or "").upper() or "UNKNOWN"
                        base_url=storefront_product_json_url(
                            cfg.get("primary_domain"),check.get("path_prefix"),
                            sellability_product.get("handle"),
                        )
                        last_frontend_issues=[]
                        for attempt in range(attempts):
                            try:
                                separator="&" if "?" in base_url else "?"
                                payload=fetch_storefront_product_json(
                                    base_url+separator+"verify="+str(int(time.time()*1000))
                                )
                                last_frontend_issues=storefront_sellability_issues(
                                    payload,variant_ids,
                                )
                            except Exception as exc:
                                last_frontend_issues=[f"读取区域商品 JSON 失败: {exc}"]
                            if not last_frontend_issues:
                                break
                            if attempt+1<attempts and delay:
                                time.sleep(delay)
                        errors += [
                            f"{country_code} 前台可售门禁: {issue}"
                            for issue in last_frontend_issues
                        ]
                    if errors:
                        errors.append(
                            "禁止自动切换 CONTINUE 或改库存；若后台履约全绿但前台仍 false，"
                            "需用户确认后再用 CAS 库存事件触发重算"
                        )
                if not errors: patch.update(product_mirror_patch(live,cfg,F,field_types,ent["date"],now_ms))
            if errors:
                message="; ".join(errors)
                failure_patch=writeback_result_fields(False,message,now_ms)
                if a.entity=="product": failure_patch.update(faq_status_patch(F))
                update_lark_row(app,tid,r["record_id"],failure_patch,prof)
                print("    ⚠️写回失败:",message)
                continue
            patch.update(writeback_result_fields(True,"",now_ms,a.prepare_draft))
            if a.entity=="product": patch.update(faq_status_patch(F))
            update_lark_row(app,tid,r["record_id"],patch,prof)
            done+=1
        except Exception as exc:
            message=str(exc)
            failure_patch=writeback_result_fields(False,message,int(time.time()*1000))
            if a.entity=="product": failure_patch.update(faq_status_patch(F))
            try: update_lark_row(app,tid,r["record_id"],failure_patch,prof)
            except Exception as lark_exc: message+=f"; 飞书失败状态回填也失败: {lark_exc}"
            print("    ⚠️写回异常:",message)
    if not a.dry_run:
        suffix="已保持 DRAFT" if a.prepare_draft else "已回填状态=已上线"
        print(f"写回完成 {done} 行({suffix})")
    return 0

if __name__=="__main__": raise SystemExit(main())
