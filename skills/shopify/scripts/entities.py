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


# ---------- ARTICLE ----------
ARTICLE_QUERY = """query($cursor:String){ articles(first:50, after:$cursor){
  edges{ cursor node{
    id handle title body summary tags
    author{ name } blog{ handle } image{ url }
    tt:metafield(namespace:"global",key:"title_tag"){ value }
    dt:metafield(namespace:"global",key:"description_tag"){ value }
  } } pageInfo{ hasNextPage endCursor } } }"""

def build_article(node, cfg):
    mirror={"Article ID":node["id"],"Handle":node.get("handle") or "",
            "博客":(node.get("blog") or {}).get("handle",""),"作者":(node.get("author") or {}).get("name","")}
    content={"文章标题":node.get("title") or "","文章正文EN":node.get("body") or "",
             "摘要EN":node.get("summary") or "",
             "SEO Title EN":(node.get("tt") or {}).get("value") or "",
             "SEO描述EN":(node.get("dt") or {}).get("value") or "",
             "Tags":", ".join(node.get("tags") or []),"主图URL":(node.get("image") or {}).get("url","")}
    return mirror, content


# ---------- PAGE ----------
PAGE_QUERY = """query($cursor:String){ pages(first:50, after:$cursor){
  edges{ cursor node{ id handle title body templateSuffix
    tt:metafield(namespace:"global",key:"title_tag"){ value }
    dt:metafield(namespace:"global",key:"description_tag"){ value }
  } } pageInfo{ hasNextPage endCursor } } }"""

def build_page(node, cfg):
    mirror={"Page ID":node["id"],"Handle":node.get("handle") or "","模板后缀":node.get("templateSuffix") or ""}
    content={"页面标题":node.get("title") or "","正文EN":node.get("body") or "",
             "SEO Title EN":(node.get("tt") or {}).get("value") or "","SEO描述EN":(node.get("dt") or {}).get("value") or ""}
    return mirror, content

PAGE_WB = {
 "cur_query":"query($id:ID!){ page(id:$id){ title body metafields(first:20){ edges{ node{ namespace key value } } } } }",
 "cur_key":"page",
 "update_mutation":"mutation($id:ID!,$p:PageUpdateInput!){ pageUpdate(id:$id, page:$p){ userErrors{field message} } }",
 "id_in_input":False, "var":"p", "publish":True,
 "pu_map":{"页面标题":"title","正文EN":"body"}, "seo_map":{}, "tags_field":None,
 "mf_map":{"SEO Title EN":("global","title_tag","single_line_text_field"),
           "SEO描述EN":("global","description_tag","single_line_text_field")},
 "activate":False, "target_collections":[], "title_field":"页面标题",
}

ENTITIES = {
 "product":   {"query":PRODUCT_QUERY,   "build":build_product,   "key":"Shopify Product ID",
               "status":"内容审核状态", "date":"最近Shopify同步日期", "supports_query":True},
 "collection":{"query":COLLECTION_QUERY,"build":build_collection,"key":"Collection ID",
               "status":"内容审核状态", "date":"最近同步日期", "supports_query":False},
 "article":   {"query":ARTICLE_QUERY,   "build":build_article,   "key":"Article ID",
               "status":"内容审核状态", "date":"最近同步日期", "supports_query":False,
               "hard":["文章标题","文章正文EN"]},
 "page":      {"query":PAGE_QUERY,      "build":build_page,      "key":"Page ID",
               "status":"内容审核状态", "date":"最近同步日期", "supports_query":False,
               "hard":["页面标题"], "wb":PAGE_WB},
}

# ---------- 写回规格(sync_writeback 用)----------
PRODUCT_WB = {
 "cur_query":"""query($id:ID!){ product(id:$id){ title descriptionHtml productType tags status seo{title description}
   metafields(first:60){ edges{ node{ namespace key value } } } collections(first:30){edges{node{handle}}} } }""",
 "cur_key":"product",
 "update_mutation":"mutation($p:ProductInput!){ productUpdate(input:$p){ userErrors{field message} } }",
 "input_type":"ProductInput",
 "pu_map":{"商品名称":"title","商品描述EN":"descriptionHtml"},
 "seo_map":{"SEO Title EN":"title","SEO描述EN":"description"},
 "tags_field":"Tags|标签",
 "mf_map":{"custom.material 材质":("custom","material","single_line_text_field"),
   "custom.height_cm 高度":("custom","height_cm","single_line_text_field"),
   "custom.box_size_cm 单盒尺寸：长|宽|高":("custom","box_size","single_line_text_field"),
   "custom.hidden_odds 隐藏款概率":("custom","hidden_odds","single_line_text_field"),
   "custom.series 系列":("custom","series","single_line_text_field"),
   "custom.scenario_copy 场景文案":("custom","scenario_copy","multi_line_text_field"),
   "custom.faq 常见问题":("custom","faq","json")},
 "activate":True,
 "target_collections":["目标IP集合","目标品类集合","目标场景集合"],
 "title_field":"商品名称",
}
COLLECTION_WB = {
 "cur_query":"""query($id:ID!){ collection(id:$id){ title descriptionHtml seo{title description}
   metafields(first:30){ edges{ node{ namespace key value } } } } }""",
 "cur_key":"collection",
 "update_mutation":"mutation($p:CollectionInput!){ collectionUpdate(input:$p){ userErrors{field message} } }",
 "input_type":"CollectionInput",
 "pu_map":{"集合名称":"title","集合描述EN":"descriptionHtml"},
 "seo_map":{"SEO Title EN":"title","SEO描述EN":"description"},
 "tags_field":None,
 "mf_map":{"editorial_body EN":("custom","editorial_body","rich_text_field"),
   "FAQ EN":("custom","faq","json"),
   "IP卡_badge EN":("funcinating","homepage_badge","single_line_text_field"),
   "IP卡_tagline EN":("funcinating","homepage_tagline","single_line_text_field"),
   "IP卡_summary EN":("funcinating","homepage_summary","multi_line_text_field"),
   "IP卡_chips EN":("funcinating","homepage_chips","list.single_line_text_field")},
 "activate":False,
 "target_collections":[],
 "title_field":"集合名称",
}
ARTICLE_WB = {
 "cur_query":"query($id:ID!){ article(id:$id){ title body summary tags metafields(first:20){ edges{ node{ namespace key value } } } } }",
 "cur_key":"article",
 "update_mutation":"mutation($id:ID!,$a:ArticleUpdateInput!){ articleUpdate(id:$id, article:$a){ userErrors{field message} } }",
 "id_in_input":False, "var":"a", "publish":True,
 "pu_map":{"文章标题":"title","文章正文EN":"body","摘要EN":"summary"},
 "seo_map":{}, "tags_field":"Tags",
 "mf_map":{"SEO Title EN":("global","title_tag","single_line_text_field"),
           "SEO描述EN":("global","description_tag","single_line_text_field")},
 "activate":False, "target_collections":[], "title_field":"文章标题",
}
ENTITIES["article"]["wb"]=ARTICLE_WB
ENTITIES["product"]["hard"]=["商品名称","商品描述EN","主图URL","IP|角色","custom.material 材质","custom.series 系列","custom.box_size_cm 单盒尺寸：长|宽|高","custom.height_cm 高度","资料来源|官方依据"]
ENTITIES["collection"]["hard"]=["集合名称","集合描述EN","editorial_body EN","FAQ EN"]
ENTITIES["product"]["wb"]=PRODUCT_WB
ENTITIES["collection"]["wb"]=COLLECTION_WB


# ---------- 需按语言建 _<lang> 变体的 metafield(json/rich_text 不走标准翻译)----------
ML_METAFIELDS = {
 "product":   [("custom","scenario_copy","multi_line_text_field"),("custom","faq","json")],
 "collection":[("custom","editorial_body","rich_text_field"),("custom","faq","json"),
               ("funcinating","homepage_badge","single_line_text_field"),
               ("funcinating","homepage_tagline","single_line_text_field"),
               ("funcinating","homepage_summary","multi_line_text_field"),
               ("funcinating","homepage_chips","list.single_line_text_field")],
 "article":[], "page":[],
}
# lang -> metafield key 后缀(承接现有:_th/_es/_zh)
LANG_SUFFIX = {"es":"es","th":"th","zh-CN":"zh","zh-TW":"zh_tw"}
RES_LIST = {"product":"products","collection":"collections"}
