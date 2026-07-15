#!/usr/bin/env python3
"""audit:对「待补素材」行核查硬缺(实体感知),输出补充清单。软缺 skill 能生成的不烦人。
   用法: python3 audit.py [--entity product|collection] [--status 待补素材]"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
from entities import ENTITIES

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--entity",default="product",choices=list(ENTITIES.keys()))
    ap.add_argument("--status",default="待补素材")
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg)
    ent=ENTITIES[a.entity]; hard=ent.get("hard",[])
    tid=(cfg.get("entities",{}).get(a.entity,{}) or {}).get("table_id",""); cfg["feishu"]["table_id"]=tid
    name_f = hard[0] if hard else ent["key"]
    rows=[r for r in _lib.bitable_list(cfg) if _lib.cell_text(r["fields"].get(ent["status"]))==a.status]
    print(f"[{a.entity}] 核查(状态={a.status}) {len(rows)} 行\n")
    allok=True
    for r in rows:
        F=r["fields"]; title=_lib.cell_text(F.get(name_f)) or "(无名)"
        miss=[c for c in hard if not _lib.cell_text(F.get(c)).strip()]
        if a.entity=="product":
            typ=_lib.cell_text(F.get("商品类型|毛绒/盲盒/手办-便于做集合分类"))+title
            if ("盲盒" in typ or "blind" in typ.lower()) and not _lib.cell_text(F.get("custom.hidden_odds 隐藏款概率")).strip():
                miss.append("隐藏款概率(盲盒必填)")
        if miss: allok=False; print(f"  ⚠️ {title[:36]}  缺:{'、'.join(m.split(' ')[0] for m in miss)}")
        else: print(f"  ✅ {title[:36]}  硬缺已齐")
    print("\n"+("全部硬缺已齐" if allok and rows else "有待补,提醒同事补上缺项" if rows else "无待补行"))
if __name__=="__main__": main()
