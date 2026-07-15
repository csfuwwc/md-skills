"""shopify skill 共享库:配置加载 + Shopify GraphQL + 飞书 bitable 封装。
   token 绝不写死:Shopify 走 `shopify store execute` 自带鉴权,飞书走 lark-cli --profile(keychain)。"""
import json, subprocess, os, re, tempfile

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
        if allow_mutations: cmd.insert(4, "--allow-mutations")
        if variables:
            vf = os.path.join(t, "v.json"); open(vf,"w").write(json.dumps(variables)); cmd += ["--variable-file", vf]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.exists(of): raise RuntimeError("shopify execute 无输出")
        raw = json.load(open(of))
        return raw.get("data", raw)

def _lark(args, profile):
    r = subprocess.run(["lark-cli"]+args+["--profile",profile,"--as","user"], capture_output=True, text=True)
    out = r.stdout + r.stderr
    i = out.find("{")
    return json.loads(out[i:]) if i>=0 else {}

def lark_post(path, data_obj, profile):
    """POST body 走 @相对路径临时文件(lark-cli 要求 @file 在当前目录内)。"""
    import uuid
    p=f"_larkpost_{uuid.uuid4().hex[:8]}.json"   # cwd 内相对路径
    with open(p,"w",encoding="utf-8") as f: json.dump(data_obj, f, ensure_ascii=False)
    try:
        r=subprocess.run(["lark-cli","api","POST",path,"--data","@"+p,"--profile",profile,"--as","user"], capture_output=True, text=True)
        out=r.stdout+r.stderr; i=out.find("{")
        return json.loads(out[i:]) if i>=0 else {}
    finally:
        if os.path.exists(p): os.unlink(p)

def bitable_list(cfg):
    """拉全部记录,返回 [{record_id, fields}]。"""
    app=cfg["feishu"]["app_token"]; tbl=cfg["feishu"]["table_id"]; prof=cfg["feishu"]["profile"]
    d=_lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tbl}/records","--params",'{"page_size":200}'], prof)
    return (d.get("data") or {}).get("items", [])

def bitable_field_names(cfg):
    app=cfg["feishu"]["app_token"]; tbl=cfg["feishu"]["table_id"]; prof=cfg["feishu"]["profile"]
    d=_lark(["api","GET",f"/bitable/v1/apps/{app}/tables/{tbl}/fields","--params",'{"page_size":200}'], prof)
    return [f["field_name"] for f in (d.get("data") or {}).get("items", [])]

def cell_text(v):
    if v is None: return ""
    if isinstance(v,str): return v
    if isinstance(v,list): return "".join((x.get("text",x.get("name","")) if isinstance(x,dict) else str(x)) for x in v)
    if isinstance(v,dict): return v.get("text") or v.get("name") or ""
    return str(v)
