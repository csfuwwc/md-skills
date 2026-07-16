"""shopify skill 共享库:配置加载 + Shopify GraphQL + 飞书 bitable 封装。
   token 绝不写死:Shopify 走 `shopify store execute` 自带鉴权,飞书走 lark-cli --profile(keychain)。"""
import json, subprocess, os, re, tempfile, time

def load_config(skill_dir=None):
    d = skill_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 的父 = skill 根(config 在此)
    cfg = {}
    for fn in ("config.example.json", "config.local.json"):
        p = os.path.join(d, fn)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                _deep_merge(cfg, json.load(f))
    return cfg

def _deep_merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict): _deep_merge(a[k], v)
        else: a[k] = v

def shopify(query, store, variables=None, allow_mutations=False):
    """跑一条 Admin GraphQL,返回 data(已去 ANSI/无 data 包裹兼容)。"""
    with tempfile.TemporaryDirectory() as t:
        qf = os.path.join(t, "q.graphql"); of = os.path.join(t, "o.json")
        open(qf, "w").write(query)
        cmd = ["shopify","store","execute","-s",store,"-j","--query-file",qf,"--output-file",of]
        if allow_mutations: cmd.append("--allow-mutations")
        if variables:
            vf = os.path.join(t, "v.json"); open(vf,"w").write(json.dumps(variables)); cmd += ["--variable-file", vf]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.exists(of): raise RuntimeError("shopify execute 无输出")
        raw = json.load(open(of))
        return raw.get("data", raw)

def feishu_profile(cfg):
    """profile 可留空:空=用 lark-cli 当前活动 profile(同事自己已登录的飞书),不必写进 config。"""
    return (cfg.get("feishu") or {}).get("profile") or None

def _lark(args, profile=None):
    cmd = ["lark-cli"]+args+["--as","user"]
    if profile: cmd += ["--profile", profile]   # 留空=用活动 profile
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = r.stdout + r.stderr
    i = out.find("{")
    return json.loads(out[i:]) if i>=0 else {}

def lark_post(path, data_obj, profile=None):
    """POST body 走 @相对路径临时文件(lark-cli 要求 @file 在当前目录内)。"""
    import uuid
    p=f"_larkpost_{uuid.uuid4().hex[:8]}.json"   # cwd 内相对路径
    with open(p,"w",encoding="utf-8") as f: json.dump(data_obj, f, ensure_ascii=False)
    try:
        for attempt in range(2):
            cmd=["lark-cli","api","POST",path,"--data","@"+p,"--as","user"]
            if profile: cmd += ["--profile", profile]
            r=subprocess.run(cmd, capture_output=True, text=True)
            out=r.stdout+r.stderr; i=out.find("{")
            d=json.loads(out[i:]) if i>=0 else {}
            if d.get("code")==0 or d.get("ok") is True: return d   # 成功
            if attempt==0: time.sleep(1); continue                 # 偶发失败重试一次
            return d
    finally:
        if os.path.exists(p): os.unlink(p)

def bitable_list(cfg):
    """拉全部记录,返回 [{record_id, fields}]。"""
    app=cfg["feishu"]["app_token"]; tbl=cfg["feishu"]["table_id"]; prof=feishu_profile(cfg)
    d=_lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tbl}/records","--params",'{"page_size":200}'], prof)
    return (d.get("data") or {}).get("items") or []

def bitable_field_names(cfg):
    app=cfg["feishu"]["app_token"]; tbl=cfg["feishu"]["table_id"]; prof=feishu_profile(cfg)
    d=_lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tbl}/fields","--params",'{"page_size":200}'], prof)
    return [f["field_name"] for f in (d.get("data") or {}).get("items", [])]

def ensure_ready(cfg):
    """轻量前置守卫:config 没建好就友好报错退出,指向 preflight。任何脚本开头调用。"""
    import sys
    f=cfg.get("feishu") or {}
    at, tid = f.get("app_token",""), f.get("table_id","")
    if not at or "SET_IN" in at or not tid or "SET_IN" in tid or not cfg.get("shopify_store"):
        print("❌ 初始化未完成:config.local.json 未建好(feishu.app_token/table_id 未填)。")
        print("   → 1) cp config.example.json config.local.json 并填入你的飞书表标识")
        print("      2) 先跑 `python3 preflight.py` 做完整自检(config/授权/依赖应用),全绿再跑本脚本。")
        sys.exit(1)

def cell_text(v):
    if v is None: return ""
    if isinstance(v,str): return v
    if isinstance(v,list): return "".join((x.get("text",x.get("name","")) if isinstance(x,dict) else str(x)) for x in v)
    if isinstance(v,dict): return v.get("text") or v.get("name") or ""
    return str(v)
