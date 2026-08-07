---
name: oss-upload
description: 达人/社媒素材库的入库与取用 —— 把小红书等平台的合作素材(图/视频/文案)归档进阿里 OSS 并登记到飞书「达人·素材」表,以及按 IP/表现/授权条件检索素材,供独立站 blog、news、站外引流帖复用。触发场景:素材入库、素材归档、找素材、达人素材、素材库、把这条笔记存下来、写文章要配图找现成素材。
---

# 达人素材库

素材库 = **OSS 存文件 + 飞书表做索引**。文件放阿里 OSS(bucket `mdfile`,前缀 `assets/`),检索靠飞书「达人·素材」表——**任何时候找素材都查表,不要去扫 OSS**(STS 凭证只能写不能列目录)。

## 系统坐标

| 组件 | 位置 |
|---|---|
| 飞书「达人·素材」表 | app `BkRCb9uKjaN8VzsgGDZciqRxnDc` / table `tblxpajEH9CoNcQa`(Stagehand 统一数据骨干 base) |
| 血缘下游「发布·内容资产」 | 同 base / table `tbl6oVFshNxbwOxp`,来源类型「达人二创」+ 字段「关联达人素材」 |
| 入库脚本 | `/home/ubuntu/creator-assets/ingest.py`(VPS) |
| 裸上传脚本 | `/home/ubuntu/creator-assets/oss_up.py`(不写表,一般不用) |
| lark 身份 | **必须 `--profile personal-li-shoushou --as user`**;`concerto-system` 读不了记录 |

## 入库

三种来历,脚本自动发素材ID、拼路径、改文件名、回写表:

```bash
# ① 有笔记链接(素材ID 从链接提取;若表里已有种子行则合并更新,不新建)
/home/ubuntu/creator-assets/ingest.py --url "http://xhslink.com/o/xxx" 图1.jpg 图2.jpg video.mp4 \
    --cover 图1.jpg --note "达人原文案..."

# ② 达人直接交付的原片(无链接)→ 发 c_ 号
/home/ubuntu/creator-assets/ingest.py --delivery --creator "达人昵称" video.mp4 --note note.md

# ③ 我们自己生成/加工的成品 → 发 g_ 号
/home/ubuntu/creator-assets/ingest.py --generated --title "labubu 头图" cover.jpg

# 先看路径不上传
/home/ubuntu/creator-assets/ingest.py --url "..." *.jpg --dry-run
```

`--note` 可以给文本,也可以给 `.md`/`.txt` 路径;文案会同时存成 OSS 里的 `note.md` 和表里的「文案快照」。

入库后人工补三件脚本不知道的事(飞书表里直接改):**授权状态**、内容标签、关联达人/合作。

## 存储规则(脚本已实现,勿手工拼路径)

```
mdfile/
  uploads/                      ← Stagehand 既有上传区,不碰
  assets/{YYYY}/{MM}/{素材ID}/   ← 入库年月;一个素材一个文件夹
      img_01.jpg img_02.jpg video.mp4 cover.jpg note.md
```

- 素材ID:`xhs_<noteid>` / `xhslink_<码>`(从链接)、`c_<日期>_<随机>`(达人交付)、`g_<日期>_<随机>`(自产)
- 文件名脚本统一发号,原始文件名记进表「备注」
- **只增不改**:加工产出永远开新 `g_` 文件夹,不覆盖旧文件
- 读取 URL 用 `https://mdfile.oss-cn-beijing.aliyuncs.com/<key>`;**`vd.moimg.net` 的 HTTPS 证书不匹配,别用**
- 分类维度(IP/标签/用途)一律留在表字段,不进路径——目录只保证唯一和可读

## 取用素材

查表,不扫 OSS。典型:给一篇 blog 找配图 → 筛「表现分层 S/A + 状态=已归档 + 授权状态≠未授权」:

```bash
lark-cli api POST /open-apis/bitable/v1/apps/BkRCb9uKjaN8VzsgGDZciqRxnDc/tables/tblxpajEH9CoNcQa/records/search \
  --data '{"filter":{"conjunction":"and","conditions":[
      {"field_name":"表现分层","operator":"is","value":["S"]},
      {"field_name":"状态","operator":"is","value":["已归档"]}]},"page_size":50}' \
  --profile personal-li-shoushou --as user
```

拿到「素材URL」(一行一个)直接 `curl -O` 下载,或把 URL 交给下游(Shopify 文章、剪辑)。

用了之后**回写血缘**:在「发布·内容资产」建记录时,来源类型选「达人二创」、「关联达人素材」指向该素材行。

## 红线

- **未授权素材禁止用于投流和商品页**;站内 blog/news 使用前确认「授权状态」不是「未授权」。表里没写授权的,默认当未授权处理,先找运营补确认。
- **跨平台不原样搬运**:小红书爆款视频直接搬去 TikTok 会被判非原创限流,复用必须二次剪辑(产出存新 `g_` 素材)。
- bucket 是公共读、STS 网关无鉴权,**不要往 `assets/` 传任何敏感文件**(合同、凭证、内部资料)。
- 小红书反爬严格,**优先让达人直接交付原片**(顺带解决无水印和授权),不做批量抓取。
- xhslink 短链和带 `xsec_token` 的链接会过期——**合作发布后尽快归档**,别等要用时再找。

## 常见问题

- **`lark-cli` 报 99991679**:用错身份了,换 `personal-li-shoushou`。
- **上传成功但 URL 打不开**:检查是不是写成了 `vd.moimg.net`,换 `mdfile.oss-cn-beijing.aliyuncs.com`。
- **想确认某素材是否已归档**:查表「状态」字段,别去 OSS 找(列目录会 403)。
- **SDK 缺失**:入库脚本用自带 venv `/home/ubuntu/creator-assets/.venv`(装了 `alibabacloud-oss-v2`),直接执行脚本即可,别用系统 python。
