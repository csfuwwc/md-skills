#!/usr/bin/env python3
"""audit:对「待补素材」行核查硬缺(只有同事能提供的字段),输出补充清单。
   软缺(SEO/关键词/FAQ/scenario/集合 skill 能生成)不算缺、不烦同事。
   用法: python3 audit.py [--status 待补素材]"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

# 硬缺:只有人能给。(隐藏款概率仅盲盒必填)
HARD = ["商品名称","商品描述EN","主图URL","IP|角色","custom.material 材质",
        "custom.series 系列","custom.box_size_cm 单盒尺寸：长|宽|高","custom.height_cm 高度","资料来源|官方依据"]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--status",default="待补素材")
    ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    cfg=_lib.load_config(a.skill_dir); _lib.ensure_ready(cfg)
    rows=[r for r in _lib.bitable_list(cfg) if _lib.cell_text(r["fields"].get("内容审核状态"))==a.status]
    print(f"核查(状态={a.status}) {len(rows)} 行\n")
    allok=True
    for r in rows:
        F=r["fields"]; title=_lib.cell_text(F.get("商品名称")) or "(无名)"
        miss=[c for c in HARD if not _lib.cell_text(F.get(c)).strip()]
        # 盲盒才要隐藏款概率
        typ=_lib.cell_text(F.get("商品类型|毛绒/盲盒/手办-便于做集合分类"))+_lib.cell_text(F.get("商品名称"))
        if ("盲盒" in typ or "blind" in typ.lower()) and not _lib.cell_text(F.get("custom.hidden_odds 隐藏款概率")).strip():
            miss.append("custom.hidden_odds 隐藏款概率(盲盒必填)")
        if miss:
            allok=False; print(f"  ⚠️ {title[:40]}  缺:{ '、'.join(m.split(' ')[0] for m in miss) }")
        else:
            print(f"  ✅ {title[:40]}  硬缺已齐,可进 optimize")
    print("\n"+("全部硬缺已齐" if allok and rows else "有待补,提醒同事补上表中缺项" if rows else "无待补素材行"))
if __name__=="__main__": main()
