#!/usr/bin/env python3
"""health:店铺健康巡检(只读,不改任何东西)。一条命令跑遍目录,聚合各项自检成一张报告。
   常态监控用——每周/每次批量改动后跑,防回退(不是补缺口,是巡检)。

   查:商品 SEO/alt/集合归属/滞留草稿/正文图是否已优化;集合 SEO/内容;
      可选 --i18n:各语言 locale 完整性(--pull 实拉 live)+ market 启用。

   用法:
     python3 health.py                 # 内容健康
     python3 health.py --i18n --pull    # 加多语言巡检(实拉 live locale)
   退出码:有待办项=1,全绿=0(可接 CI/定时)。"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
import image_optimize as imgopt

def line(ok, label, detail=""):
    print(f"  {'✅' if ok else '⚠️ '} {label}{('  '+detail) if detail else ''}")
    return 0 if ok else 1


def workflow_field_issues(fields):
    """检查飞书流程字段自洽性；不把 Shopify ACTIVE 误当成历史写回成功证据。"""
    issues=[]
    shopify_status=_lib.cell_text(fields.get("状态")).strip().upper()
    workflow_status=_lib.cell_text(fields.get("内容审核状态")).strip()
    writeback_status=_lib.cell_text(fields.get("Shopify写回状态")).strip()
    writeback_time=fields.get("Shopify写回时间")
    error=_lib.cell_text(fields.get("写回错误信息")).strip()
    source=_lib.cell_text(fields.get("资料来源|官方依据")).strip()
    faq=_lib.cell_text(fields.get("custom.faq 常见问题")).strip()
    faq_status=_lib.cell_text(fields.get("FAQ JSON校验状态")).strip()
    success=writeback_status in {"成功","已写回"}
    published=shopify_status=="ACTIVE" or workflow_status=="已上线"

    product_url=fields.get("商品URL")
    if isinstance(product_url,dict): product_url=product_url.get("link") or product_url.get("text") or ""
    if shopify_status=="ACTIVE" and not str(product_url or "").strip():
        issues.append("ACTIVE 但商品URL为空")
    if not source: issues.append("资料来源|官方依据为空")
    if published and not faq: issues.append("已上线但 FAQ 为空")
    if faq and faq_status!="通过": issues.append("FAQ 有内容但校验状态不是通过")
    if published and not success: issues.append("已上线但没有经回读验证的写回成功状态")
    if success and not writeback_time: issues.append("写回成功但写回时间为空")
    if success and error: issues.append("写回成功但仍有错误信息")
    if writeback_status=="失败" and not error: issues.append("写回失败但错误信息为空")
    if not success and writeback_time: issues.append("非成功状态却有写回时间")
    if writeback_status!="失败" and error: issues.append("非失败状态却有错误信息")
    return issues


def check_product_workflow(cfg):
    """只读巡检商品表的来源、FAQ、URL与写回状态债务。"""
    table_id=((cfg.get("entities") or {}).get("product") or {}).get("table_id","")
    if not table_id:
        print("\n[流程] 商品飞书表")
        return line(False,"流程字段完整性","config.entities.product.table_id 未配置")
    flow_cfg=dict(cfg); flow_cfg["feishu"]=dict(cfg.get("feishu") or {})
    flow_cfg["feishu"]["table_id"]=table_id
    rows=_lib.bitable_list(flow_cfg); bad=[]
    for row in rows:
        issues=workflow_field_issues(row.get("fields") or {})
        if issues:
            title=_lib.cell_text((row.get("fields") or {}).get("商品名称")) or row.get("record_id","(无名)")
            bad.append((title,issues))
    print(f"\n[流程] 商品飞书表 × {len(rows)}")
    detail="" if not bad else f"异常 {len(bad)} 行，如 {bad[0][0][:24]}: {'; '.join(bad[0][1][:2])}"
    return line(not bad,f"流程字段完整性 {len(rows)-len(bad)}/{len(rows)}",detail)

def check_products(store):
    q='''{ products(first:100){ edges{ node{
      title status descriptionHtml seo{title description}
      media(first:40){ edges{ node{ ... on MediaImage{ image{altText} } } } }
      collections(first:5){ edges{ node{ handle } } } } } } }'''
    P=[e["node"] for e in _lib.shopify(q, store)["products"]["edges"]]
    n=len(P); issues=0
    seo_t=sum(1 for p in P if (p.get("seo") or {}).get("title"))
    seo_d=sum(1 for p in P if (p.get("seo") or {}).get("description"))
    orphan=[p["title"][:24] for p in P if not p["collections"]["edges"]]
    imgs=alt_miss=0
    unopt=[]
    for p in P:
        for m in p["media"]["edges"]:
            im=m["node"].get("image")
            if im: imgs+=1; alt_miss+= 0 if (im.get("altText") or "").strip() else 1
        _,k=imgopt.rewrite_html(p.get("descriptionHtml"),1600,True,True)
        if k>0: unopt.append(f"{p['title'][:20]}({k})")
    print(f"\n[内容] 商品 × {n}(主图廊 {imgs} 图)")
    issues+=line(seo_t==n, f"SEO 标题 {seo_t}/{n}", "" if seo_t==n else f"缺 {n-seo_t}")
    issues+=line(seo_d==n, f"SEO 描述 {seo_d}/{n}", "" if seo_d==n else f"缺 {n-seo_d}")
    issues+=line(alt_miss==0, f"图片 alt {imgs-alt_miss}/{imgs}", "" if alt_miss==0 else f"缺 {alt_miss} 张")
    issues+=line(not orphan, f"集合归属 {n-len(orphan)}/{n}", "" if not orphan else "孤儿:"+"、".join(orphan[:3]))
    issues+=line(not unopt, f"正文图已优化 {n-len(unopt)}/{n}", "" if not unopt else "待优化:"+"、".join(unopt[:3])+" → image_optimize.py")
    return issues

def check_collections(store):
    q='{ collections(first:60){ edges{ node{ title handle seo{title description} descriptionHtml } } } }'
    C=[e["node"] for e in _lib.shopify(q, store)["collections"]["edges"]]
    n=len(C); issues=0
    seo_t=sum(1 for c in C if (c.get("seo") or {}).get("title"))
    seo_d=sum(1 for c in C if (c.get("seo") or {}).get("description"))
    body=sum(1 for c in C if (c.get("descriptionHtml") or "").strip())
    print(f"\n[内容] 集合 × {n}")
    issues+=line(seo_t==n, f"SEO 标题 {seo_t}/{n}", "" if seo_t==n else f"缺 {n-seo_t}")
    issues+=line(seo_d==n, f"SEO 描述 {seo_d}/{n}", "" if seo_d==n else f"缺 {n-seo_d}")
    issues+=line(body==n, f"导购正文 {body}/{n}", "" if body==n else f"缺 {n-body}")
    return issues

def check_redirects(store):
    r=_lib.shopify('{ urlRedirects(first:1){ edges{ node{ id } } } }', store)
    print("\n[治理]")
    return line(True, "301 重定向", "已有" if r["urlRedirects"]["edges"] else "0 条(handle 变更须补 301)")

def check_i18n(cfg, pull):
    store=cfg["shopify_store"]
    langs=(cfg.get("languages") or {}).get("alternates", [])
    print(f"\n[多语言] {', '.join(langs)}")
    issues=0
    # market 启用
    import translate
    q='{ markets(first:50){ edges{ node{ name enabled webPresence{ defaultLocale{locale} alternateLocales{locale} } } } } }'
    d=_lib.shopify(q, store); en_langs=set()
    for e in d["markets"]["edges"]:
        n=e["node"]; wp=n.get("webPresence") or {}
        if n["enabled"]:
            en_langs.add((wp.get("defaultLocale") or {}).get("locale"))
            en_langs|={a["locale"] for a in (wp.get("alternateLocales") or [])}
    miss_mkt=[l for l in langs if l not in en_langs]
    issues+=line(not miss_mkt, "market 启用", "全部已启用" if not miss_mkt else "未启用:"+"、".join(miss_mkt))
    # locale 完整性(需 --pull 实拉真值)
    if pull:
        import locale_check as lc
        ldir=lc.pull_live_locales(cfg, langs)
        EN=dict(lc.flat(lc.load_locale(os.path.join(ldir,"en.default.json"))))
        dnt=cfg.get("dnt_names") or []
        for l in langs:
            fp=os.path.join(ldir, lc.lang_file(l))
            if not os.path.exists(fp): issues+=line(False, f"locale {l}", "整门缺文件"); continue
            T=dict(lc.flat(lc.load_locale(fp)))
            miss=[k for k in EN if k not in T]
            untl=[k for k in EN if k in T and str(EN[k])==str(T[k]) and lc.translatable(EN[k],dnt)]
            issues+=line(not miss and len(untl)<=3, f"locale {l}",
                         "全翻" if not miss and not untl else f"缺{len(miss)}/疑未翻{len(untl)}(locale_check 细看)")
    else:
        print("  · locale 完整性:加 --pull 从 live 实拉比对(本地会过期误报)")
    return issues

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--i18n", action="store_true", help="加多语言巡检")
    ap.add_argument("--pull", action="store_true", help="i18n 时从 live 实拉 locale(真值)")
    a=ap.parse_args()
    cfg=_lib.load_config(); store=cfg["shopify_store"]
    print("═══ Funcinating 店铺健康巡检(只读)═══")
    total=0
    total+=check_products(store)
    total+=check_collections(store)
    total+=check_redirects(store)
    total+=check_product_workflow(cfg)
    if a.i18n: total+=check_i18n(cfg, a.pull)
    print("\n"+"─"*40)
    print(f"结论:{'✅ 全绿,无待办' if total==0 else f'⚠️  {total} 项待办,见上 ⚠️ 处'}")
    sys.exit(1 if total else 0)

if __name__=="__main__":
    main()
