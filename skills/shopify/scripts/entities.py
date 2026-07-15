"""实体定义:每个 Shopify 资源(product/collection/…)的 GraphQL 查询 + 字段映射。
   sync_pull/writeback 据此做实体感知处理。新增实体只在这里加一段。"""

# ---------- PRODUCT ----------
PRODUCT_QUERY = """query($cursor:String){ products(first:50, query:"%(q)s", after:$cursor){
  edges{ cursor node{
    id handle onlineStoreUrl status vendor
    title descriptionHtml seo{ title description }
    featuredImage{ url }
    variants(first:100){ edges{ node{ sku price inventoryQuantity } } }
    collections(first:30){ edges{ node{ handle } } }
    metafields(first:60){ edges{ node{ namespace key value } } }
  } } pageInfo{ hasNextPage endCursor } } }"""

def build_product(node, cfg):
    v=[e["node"] for e in node["variants"]["edges"]]
    prices=[float(x["price"]) for x in v if x.get("price")]
    cols=[e["node"]["handle"] for e in node["collections"]["edges"]]
    cc=cfg.get("collections",{})
    mfv={f"{m['namespace']}.{m['key']}":m["value"] for m in [e["node"] for e in node["metafields"]["edges"]]}
    mirror={"Shopify Product ID":node["id"],"Handle短名URL":node["handle"],"商品URL":node.get("onlineStoreUrl") or "",
      "状态":node["status"],"Vendor":node.get("vendor") or "","变体数":len(v),
      "SKU汇总":", ".join(x["sku"] for x in v if x.get("sku")),
      "价格区间USD":(f"{min(prices):g}-{max(prices):g}" if prices else ""),
      "总库存":sum(int(x.get("inventoryQuantity") or 0) for x in v),
      "变体摘要":" , ".join(f"SKU:{x.get('sku','')}/${x.get('price','')}/stock{x.get('inventoryQuantity',0)}" for x in v),
      "主图URL":(node.get("featuredImage") or {}).get("url","")}
    content={"商品名称":node.get("title") or "","商品描述EN":node.get("descriptionHtml") or "",
      "SEO Title EN":(node.get("seo") or {}).get("title") or "","SEO描述EN":(node.get("seo") or {}).get("description") or "",
      "目标IP集合":[c for c in cols if c in cc.get("ip",[])],
      "目标品类集合":[c for c in cols if c in cc.get("category",[])],
      "目标场景集合":[c for c in cols if c in cc.get("scenario",[])]}
    for col,key in {"custom.material 材质":"custom.material","custom.height_cm 高度":"custom.height_cm",
      "custom.box_size_cm 单盒尺寸：长|宽|高":"custom.box_size","custom.hidden_odds 隐藏款概率":"custom.hidden_odds",
      "custom.series 系列":"custom.series","custom.scenario_copy 场景文案":"custom.scenario_copy",
      "custom.faq 常见问题":"custom.faq"}.items():
        content[col]=mfv.get(key,"")
    return mirror, content

# ---------- COLLECTION ----------
COLLECTION_QUERY = """query($cursor:String){ collections(first:50, after:$cursor){
  edges{ cursor node{
    id handle title descriptionHtml seo{ title description } productsCount{ count }
    ed:metafield(namespace:"custom",key:"editorial_body"){ value }
    fq:metafield(namespace:"custom",key:"faq"){ value }
    hb:metafield(namespace:"funcinating",key:"homepage_badge"){ value }
    ht:metafield(namespace:"funcinating",key:"homepage_tagline"){ value }
    hs:metafield(namespace:"funcinating",key:"homepage_summary"){ value }
    hc:metafield(namespace:"funcinating",key:"homepage_chips"){ value }
  } } pageInfo{ hasNextPage endCursor } } }"""

def build_collection(node, cfg):
    h=node["handle"]; cc=cfg.get("collections",{})
    ctype = "IP" if h in cc.get("ip",[]) else ("场景" if h in cc.get("scenario",[]) else "品类")
    mirror={"Collection ID":node["id"],"Handle":h,"商品数":node.get("productsCount",{}).get("count",0)}
    content={"集合名称":node.get("title") or "","集合类型":ctype,
      "集合描述EN":node.get("descriptionHtml") or "",
      "SEO Title EN":(node.get("seo") or {}).get("title") or "","SEO描述EN":(node.get("seo") or {}).get("description") or "",
      "editorial_body EN":(node.get("ed") or {}).get("value") or "","FAQ EN":(node.get("fq") or {}).get("value") or "",
      "IP卡_badge EN":(node.get("hb") or {}).get("value") or "","IP卡_tagline EN":(node.get("ht") or {}).get("value") or "",
      "IP卡_summary EN":(node.get("hs") or {}).get("value") or "","IP卡_chips EN":(node.get("hc") or {}).get("value") or ""}
    return mirror, content

ENTITIES = {
 "product":   {"query":PRODUCT_QUERY,   "build":build_product,   "key":"Shopify Product ID",
               "status":"内容审核状态", "date":"最近Shopify同步日期", "supports_query":True},
 "collection":{"query":COLLECTION_QUERY,"build":build_collection,"key":"Collection ID",
               "status":"内容审核状态", "date":"最近同步日期", "supports_query":False},
}
