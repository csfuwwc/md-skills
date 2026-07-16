#!/usr/bin/env python3
"""preflight:跑流水线前的初始化自检。自动查 config/授权/依赖;
   Shopify 应用无法通过 API 查(缺 read_apps),列清单让用户确认已装。
   用法: python3 preflight.py"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

def main():
    print("═══ Shopify 流水线 · 初始化自检 ═══\n")
    ap=argparse.ArgumentParser(); ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a=ap.parse_args()
    ok=True
    cfg=_lib.load_config(a.skill_dir)
    # 1 config.local.json
    at=(cfg.get("feishu") or {}).get("app_token","")
    tid=(cfg.get("feishu") or {}).get("table_id","")
    if not at or "SET_IN" in at or not tid or "SET_IN" in tid:
        ok=False; print("❌ config.local.json:feishu.app_token/table_id 未填")
        print("   → cp config.example.json config.local.json,填入你的飞书表 app_token/table_id(从表 URL 取)")
    else:
        print(f"✅ config:feishu 表 {tid} · store {cfg.get('shopify_store')}")
    # 1b 各实体表 id(product/collection/article/page 都要配,漏一个该实体流程就跑不了)
    ents = cfg.get("entities") or {}
    miss_ent = [e for e, v in ents.items()
                if not (v or {}).get("table_id") or "SET_IN" in str((v or {}).get("table_id", ""))]
    if not ents or miss_ent:
        ok = False
        print(f"❌ 实体表未配全 → {'、'.join(miss_ent) or '(entities 缺失)'}(entities.<实体>.table_id,共需 product/collection/article/page 四张)")
    else:
        print(f"✅ 实体表:{len(ents)} 张全配({'、'.join(ents.keys())})")
    # 2 飞书授权(读表)
    if at and "SET_IN" not in at:
        try:
            names=_lib.bitable_field_names(cfg); assert names
            print(f"✅ 飞书授权:表可读({len(names)} 字段)· profile={cfg['feishu']['profile']}")
        except Exception:
            ok=False; print(f"❌ 飞书授权失败 → lark-cli auth login --profile {cfg.get('feishu',{}).get('profile','?')}(需 base 读写权限)")
    # 3 Shopify 授权
    try:
        d=_lib.shopify("{ productsCount{ count } }", cfg["shopify_store"])
        print(f"✅ Shopify 授权:可连({d['productsCount']['count']} 商品)")
    except Exception:
        ok=False; print("❌ Shopify 未连 → 装 shopify CLI 并 `shopify auth`/配置 store execute 凭证")
    # 4 主题访问(可选,步骤4)
    envp=os.path.expanduser((cfg.get("theme") or {}).get("env_local_path",""))
    if envp and os.path.exists(envp):
        has=any("THEME_TOKEN" in l for l in open(envp))
        print(f"{'✅' if has else '⚠️'} 主题访问:.env.local {'含 THEME_TOKEN' if has else '缺 THEME_TOKEN'}(仅步骤4多语言/改主题需要)")
    else:
        print("⚠️ 主题访问:.env.local 未找到(仅步骤4多语言/改主题需要;纯商品上架不需要)")
    # 5 Shopify 应用(用户确认——API 查不到)
    print("\n─── 请确认以下 Shopify 应用已安装(后台 API 查不到,需你确认)───")
    for app in cfg.get("required_apps",[]):
        flag="必需" if app.get("required") else "可选"
        print(f"   ☐ [{flag}] {app['name']} —— {app['purpose']}")
    print("\n" + ("═══ ✅ 环境就绪,可以开始 sync_pull ═══" if ok else "═══ ❌ 上面有 ❌ 项,先补齐再跑 ═══"))
    sys.exit(0 if ok else 1)

if __name__=="__main__": main()
