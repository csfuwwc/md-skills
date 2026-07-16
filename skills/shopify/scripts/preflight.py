#!/usr/bin/env python3
"""preflight:跑流水线前的初始化自检。自动查 config/授权/依赖;
   Shopify 应用无法通过 API 查(缺 read_apps),列清单让用户确认已装。
   用法: python3 preflight.py"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--skill-dir",default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--modules", default="core",
                    help="要用的能力模块:core(Shopify后台内容,默认) · theme(主题UI多语言/代码侧,需前端仓) · 逗号分隔,如 core,theme")
    a=ap.parse_args()
    modules = {m.strip() for m in a.modules.split(",") if m.strip()} | {"core"}
    print("═══ Shopify 流水线 · 初始化自检 ═══")
    print(f"选定模块:{'、'.join(sorted(modules))}"
          + ("" if "theme" in modules else "  (纯 Shopify 后台;要做主题UI多语言加 --modules core,theme)") + "\n")
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
    # 2 飞书授权(读表)——profile 留空则用 lark-cli 活动 profile(同事自己已登录的飞书)
    prof=_lib.feishu_profile(cfg)
    if at and "SET_IN" not in at:
        try:
            names=_lib.bitable_field_names(cfg); assert names
            print(f"✅ 飞书授权:表可读({len(names)} 字段)· profile={prof or 'lark-cli 活动身份'}")
        except Exception:
            ok=False
            print(f"❌ 飞书读表失败(profile={prof or '活动身份'})→ 确认 ①lark-cli 已登录你的飞书 ②你账号有该多维表格读写权限(base:record/field)")
    # 3 Shopify 授权
    try:
        d=_lib.shopify("{ productsCount{ count } }", cfg["shopify_store"])
        print(f"✅ Shopify 授权:可连({d['productsCount']['count']} 商品)")
    except Exception:
        ok=False; print("❌ Shopify 未连 → 装 shopify CLI 并 `shopify auth`/配置 store execute 凭证")
    # 4 主题/前端模块(代码侧)——仅当选了 theme 模块才作硬性要求;否则纯后台不检查
    if "theme" in modules:
        th=cfg.get("theme") or {}
        envp=os.path.expanduser(th.get("env_local_path",""))
        ldir=os.path.expanduser(th.get("locales_dir",""))
        env_ok=bool(envp) and os.path.exists(envp) and any("THEME_TOKEN" in l for l in open(envp))
        ld_ok=bool(ldir) and os.path.isdir(ldir)
        if env_ok and ld_ok:
            print("✅ 主题模块:.env.local 含 THEME_TOKEN · locales_dir 就绪")
        else:
            ok=False
            if not env_ok: print("❌ 主题模块:theme.env_local_path 缺失/无 THEME_TOKEN → 指向你本机 fe-www 前端仓的 .env.local")
            if not ld_ok:  print("❌ 主题模块:theme.locales_dir 不存在 → 指向前端仓主题 locales 目录(locale_check 用)")
    else:
        print("· 主题/前端模块:未选(纯 Shopify 后台无需 fe-www;做主题UI多语言时加 --modules core,theme)")
    # 4b 依赖 skill(去AI味,optimize/翻译步骤用)——装在 shopify 同级目录
    skills_root = os.path.dirname(a.skill_dir)
    for dep in ["humanizer", "humanizer-zh"]:
        present = os.path.isdir(os.path.join(skills_root, dep))
        if present:
            print(f"✅ 依赖 skill {dep}:已装")
        else:
            print(f"⚠️ 依赖 skill {dep}:未装 → install.sh {dep}(optimize 去AI味用;install.sh 装 shopify 时本应自动带上)")
    # 5 Shopify 应用(用户确认——API 查不到)
    print("\n─── 请确认以下 Shopify 应用已安装(后台 API 查不到,需你确认)───")
    for app in cfg.get("required_apps",[]):
        flag="必需" if app.get("required") else "可选"
        print(f"   ☐ [{flag}] {app['name']} —— {app['purpose']}")
    print("\n" + ("═══ ✅ 环境就绪,可以开始 sync_pull ═══" if ok else "═══ ❌ 上面有 ❌ 项,先补齐再跑 ═══"))
    sys.exit(0 if ok else 1)

if __name__=="__main__": main()
