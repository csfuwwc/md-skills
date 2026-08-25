#!/usr/bin/env python3
"""qa:写回前自检(实体感知)。查 SEO 长度/FAQ 合法json/写回关键字段非空,
   有问题就列出、拦住带病上线。confirm-publish 的自检闸。
   用法: python3 qa.py [--entity product|collection|article|page] [--status 待确认上线]"""
import sys, os, json, argparse, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
from entities import ENTITIES


def product_priority_issues(fields):
    priority=_lib.cell_text(fields.get("运营优先级")).strip()
    return ["运营优先级"] if not priority or priority=="待评估" else []


def faq_json_issues(value):
    """校验 FAQ 不只是合法 JSON，还必须是非空 question/answer 对象数组。"""
    raw=_lib.cell_text(value).strip()
    if not raw: return ["FAQ为空"]
    try: items=json.loads(raw)
    except (TypeError,ValueError,json.JSONDecodeError): return ["FAQ 非法json"]
    if not isinstance(items,list) or not items: return ["FAQ 必须是非空数组"]
    issues=[]
    for index,item in enumerate(items,1):
        if not isinstance(item,dict):
            issues.append(f"FAQ[{index}] 不是对象"); continue
        if not str(item.get("question") or "").strip(): issues.append(f"FAQ[{index}] question为空")
        if not str(item.get("answer") or "").strip(): issues.append(f"FAQ[{index}] answer为空")
    return issues


def faq_validation_state(value):
    if not _lib.cell_text(value).strip(): return "待检查"
    return "格式错误" if faq_json_issues(value) else "通过"


def faq_status_patch(fields, faq_field="custom.faq 常见问题", status_field="FAQ JSON校验状态"):
    desired=faq_validation_state(fields.get(faq_field))
    current=_lib.cell_text(fields.get(status_field)).strip()
    return {} if current==desired else {status_field:desired}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--entity",default="product",choices=list(ENTITIES.keys()))
    ap.add_argument("--status",default="待确认上线")
    ap.add_argument("--write-status",action="store_true",help="把商品 FAQ 校验结果回填到飞书；不修改 Shopify")
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
    allok=True; status_updates=[]
    for r in rows:
        F=r["fields"]; title=_lib.cell_text(F.get(title_f))[:34] or "(无名)"; issues=[]
        if not _lib.cell_text(F.get(title_f)).strip(): issues.append("标题空")
        if a.entity=="product": issues.extend(product_priority_issues(F))
        for c in set(seo_t):
            v=_lib.cell_text(F.get(c)).strip()
            if v and len(v)>60: issues.append(f"{c}>60字({len(v)})")
        for c in seo_d:
            v=_lib.cell_text(F.get(c)).strip()
            if v and len(v)>160: issues.append(f"SEO描述>160字({len(v)})")
        for c in set(faq_cols):
            v=_lib.cell_text(F.get(c)).strip()
            if v or (a.entity=="product" and c=="custom.faq 常见问题"):
                issues.extend(f"{c}: {issue}" for issue in faq_json_issues(v))
        # 非美元语言不该有 $(查中文列)
        for c in ["商品描述中文","集合描述中文","文章正文中文","正文中文","SEO描述中文"]:
            if "$" in _lib.cell_text(F.get(c)): issues.append(f"{c} 含$(非美元语言应去美元)")
        if a.entity=="product":
            patch=faq_status_patch(F)
            if patch: status_updates.append((r["record_id"],patch))
        if issues: allok=False; print(f"  ❌ {title}: {'; '.join(issues)}")
        else: print(f"  ✅ {title}: 自检通过")
    if a.write_status:
        if a.entity!="product":
            print("\n· --write-status 目前仅适用于 product，未写入")
        elif "FAQ JSON校验状态" not in _lib.bitable_field_names(cfg):
            allok=False; print("\n❌ 飞书缺少 FAQ JSON校验状态 字段，无法回填")
        elif status_updates:
            app=cfg["feishu"]["app_token"]; prof=_lib.feishu_profile(cfg)
            result=_lib.lark_post(
                f"/bitable/v1/apps/{app}/tables/{tid}/records/batch_update",
                {"records":[{"record_id":rid,"fields":patch} for rid,patch in status_updates]},prof,
            )
            if result.get("code")!=0 and result.get("ok") is not True:
                raise RuntimeError(f"FAQ 校验状态回填失败: {result.get('msg') or result.get('error') or result}")
            print(f"\n· FAQ JSON校验状态已回填 {len(status_updates)} 行")
        else:
            print("\n· FAQ JSON校验状态已一致，0 写入")
    print("\n"+("✅ 全部通过,可 sync_writeback 上线" if allok and rows else "❌ 有问题,修完再上线" if rows else "无待确认上线行"))
    sys.exit(0 if allok else 1)
if __name__=="__main__": main()
