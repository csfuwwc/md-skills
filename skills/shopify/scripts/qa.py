#!/usr/bin/env python3
"""qa:写回前自检(实体感知)。查 SEO 长度/FAQ 合法json/写回关键字段非空,
   有问题就列出、拦住带病上线。confirm-publish 的自检闸。
   用法: python3 qa.py [--entity product|collection|article|page] [--status 待确认上线]"""
import sys, os, json, argparse, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
from entities import ENTITIES

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--entity",default="product",choices=list(ENTITIES.keys()))
    ap.add_argument("--status",default="待确认上线")
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg)
    ent=ENTITIES[a.entity]; wb=ent.get("wb",{})
    tid=(cfg.get("entities",{}).get(a.entity,{}) or {}).get("table_id",""); cfg["feishu"]["table_id"]=tid
    rows=[r for r in _lib.bitable_list(cfg) if _lib.cell_text(r["fields"].get(ent["status"]))==a.status]
    print(f"[{a.entity}] 上线自检(状态={a.status}) {len(rows)} 行\n")
    # 找 SEO/FAQ 相关列
    seo_t=[c for c in wb.get("mf_map",{}) if "Title" in c] + [c for c in wb.get("seo_map",{}) if "Title" in c] + ["SEO Title EN"]
    seo_d=["SEO描述EN"]
    faq_cols=[c for c in list(wb.get("mf_map",{}))+["custom.faq 常见问题","FAQ EN"] if "faq" in c.lower() or "FAQ" in c]
    title_f=wb.get("title_field", ent.get("hard",[ent["key"]])[0])
    allok=True
    for r in rows:
        F=r["fields"]; title=_lib.cell_text(F.get(title_f))[:34] or "(无名)"; issues=[]
        if not _lib.cell_text(F.get(title_f)).strip(): issues.append("标题空")
        for c in set(seo_t):
            v=_lib.cell_text(F.get(c)).strip()
            if v and len(v)>60: issues.append(f"{c}>60字({len(v)})")
        for c in seo_d:
            v=_lib.cell_text(F.get(c)).strip()
            if v and len(v)>160: issues.append(f"SEO描述>160字({len(v)})")
        for c in set(faq_cols):
            v=_lib.cell_text(F.get(c)).strip()
            if v:
                try: json.loads(v)
                except: issues.append(f"{c} 非法json")
        # 非美元语言不该有 $(查中文列)
        for c in ["商品描述中文","集合描述中文","文章正文中文","正文中文","SEO描述中文"]:
            if "$" in _lib.cell_text(F.get(c)): issues.append(f"{c} 含$(非美元语言应去美元)")
        if issues: allok=False; print(f"  ❌ {title}: {'; '.join(issues)}")
        else: print(f"  ✅ {title}: 自检通过")
    print("\n"+("✅ 全部通过,可 sync_writeback 上线" if allok and rows else "❌ 有问题,修完再上线" if rows else "无待确认上线行"))
    sys.exit(0 if allok else 1)
if __name__=="__main__": main()
