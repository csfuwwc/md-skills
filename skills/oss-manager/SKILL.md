---
name: oss-manager
description: 达人/社媒素材库的入库与取用 —— 把小红书等平台的合作素材(图/视频/文案)归档进阿里 OSS 并登记到飞书「达人·素材」表,以及按 IP/表现/授权条件检索素材,供独立站 blog、news、站外引流帖复用。触发场景:素材入库、素材归档、找素材、达人素材、素材库、把这条笔记存下来、写文章要配图找现成素材。
---

# 达人素材库(OSS)

**管辖范围仅限 bucket `mdfile` 的 `assets/` 前缀**;同桶下的 `uploads/`(Stagehand 运营上传区)不归本 skill 管,不要读写。

素材库 = **OSS 存文件 + 飞书表做索引**。文件放阿里 OSS(bucket `mdfile`,前缀 `assets/`),检索靠飞书「达人·素材」表——**任何时候找素材都查表,不要去扫 OSS**(STS 凭证只能写不能列目录)。

## 系统坐标

| 组件 | 位置 |
|---|---|
| 飞书「达人·素材」表 | app `BkRCb9uKjaN8VzsgGDZciqRxnDc` / table `tblxpajEH9CoNcQa`(Stagehand 统一数据骨干 base) |
| 血缘下游「发布·内容资产」 | 同 base / table `tbl6oVFshNxbwOxp`,来源类型「达人二创」+ 字段「关联达人素材」 |
| 脚本 | 本 skill 的 `scripts/`(VPS 上 `/home/ubuntu/creator-assets/` 是软链过去的) |
| lark 身份 | **必须 `--profile personal-li-shoushou --as user`**;`concerto-system` 读不了记录 |

`scripts/`:`ingest.py` 入库、`scrape_xhs.py` 小红书存量抓取、`oss_client.py` 上传器(被前两个调用)、
`oss_up.py` 裸上传不写表(一般不用)。跑之前确认三件事:能连 STS 网关(公司内网)、`lark-cli` 已授权、
python 装了 `alibabacloud-oss-v2`。

## 两条流,别混

| | 来源 | 能用到哪 | 入口 |
|---|---|---|---|
| **A 干净素材** | 达人直接交付的原片(附授权) | 站内 blog / 商品页 / 投流 | `ingest.py --delivery` |
| **B 情报素材** | 从笔记页抓的文案+数据+图 | **只能内部参考**,不可对外发布 | `scrape_xhs.py` |

流 B 抓下来的图带**小红书水印 + 达人自己的中文大字**,原图拿不到(去掉处理参数一律 403),
所以脚本一律把「可用范围」写成「仅参考」。流 B 真正的价值是**文案和互动数据**——达人怎么讲这个产品、
什么角度数据好,是写 blog 和选题的依据,不是配图来源。

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

## 存量抓取(流 B)

```bash
scripts/scrape_xhs.py --dry-run --limit 5   # 先看抓到什么,不下载不写表
scripts/scrape_xhs.py --limit 5             # 真跑 5 条
scripts/scrape_xhs.py                       # 跑完所有「待归档」的
scripts/scrape_xhs.py --asset-id xhslink_xxx --with-video   # 指定几条,连视频文件一起归档
```

- 默认只处理**状态=待归档**的行,跑成功改「已归档」;重复跑不会重复干活,断了直接再跑一遍就是续跑。
- 抓失败(笔记删了/不可见)的行标「源已失效」并把原因写进备注,不会重试,也不会清掉已有数据。
- 写回:标题、文案快照、点赞/收藏/评论、快照时间、发布时间、素材类型、素材URL、封面URL、可用范围=仅参考。
  表里原有的建联期互动数据如果和抓到的不一致,**旧值会记进备注**再更新,不会凭空消失。
- **视频文件默认不归档**。VPS 在东京,上行到阿里云北京只有 ~18KB/s,一个 18MB 的视频要传十几分钟;
  在国内的机器上跑就没这问题,可以放心加 `--with-video`。视频下载走 `video-download` skill,不自己写下载器。
- 节流:默认每条间隔 6 秒(`--delay`)。小红书反爬严格,别并发、别调快。

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

查表,不扫 OSS。**先看「可用范围」再看好不好看**——「仅参考」的东西无论多好都不能对外发。

要配图(必须能对外):筛「可用范围≠仅参考 + 状态=已归档」,再按表现分层排。
要写作参考(什么都能看):直接按表现分层 S/A 筛,读「文案快照」。

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

- **「可用范围=仅参考」的素材一律不对外**:不上 blog、不上商品页、不投流、不发社媒。它只用来给人看、给写作当参考。空白按仅参考处理。
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
