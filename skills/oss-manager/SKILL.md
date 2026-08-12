---
name: oss-manager
description: 达人/社媒素材库的入库与取用 —— 把小红书等平台的合作素材(图/视频/文案)归档进阿里 OSS 并登记到飞书「达人·素材」表,以及按 IP/表现/授权条件检索素材,供独立站 blog、news、站外引流帖复用。触发场景:素材入库、素材归档、找素材、达人素材、素材库、把这条笔记存下来、写文章要配图找现成素材。
---

# 达人素材库

素材库 = **OSS 存文件 + 飞书表做索引**。**任何时候找素材都查表,不要去扫 OSS**(STS 凭证只能写不能列目录)。

**代码在 Stagehand 仓库,不在本 skill 里** —— 表和血缘都是 Stagehand 的数据骨干(ADR-023),
业务逻辑就该待在那儿。本 skill 只管:去哪儿找、怎么用、什么不能干。

| 组件 | 位置 |
|---|---|
| 代码 | Stagehand 仓 `python/stagehand/creator_assets/`(入库 + 存量回灌)、`scraping/xhs.py`(笔记页解析);本机默认 `~/Stagehand`,可用 `STAGEHAND` 环境变量指定 |
| 依赖的 skill | `video-download`(唯一下载入口,`--with-video` 时子进程调用)、`lark-cli`(飞书读写) |
| 「达人·素材」表 | app `BkRCb9uKjaN8VzsgGDZciqRxnDc` / table `tblxpajEH9CoNcQa` |
| 血缘下游「发布·内容资产」 | 同 base / table `tbl6oVFshNxbwOxp`,来源类型「达人二创」+ 字段「关联达人素材」 |
| OSS | bucket `mdfile`,前缀 `assets/`(同桶的 `uploads/` 是 Stagehand 运营上传区,**不碰**) |
| lark 身份 | **`personal-li-shoushou`**;`concerto-system` 读不了记录(99991679) |

## 两条流,别混

| | 来源 | 能用到哪 | 入口 |
|---|---|---|---|
| **A 干净素材** | 达人直接交付的原片(附授权) | 站内 blog / 商品页 / 投流 | `cli.py ingest` |
| **B 情报素材** | 从笔记页抓的文案 + 数据 + 图 | **只能内部参考**,不可对外发布 | `cli.py scrape` |

流 B 抓下来的图带**小红书水印 + 达人自己压的中文字幕**,原图拿不到(去掉处理参数一律 403),
所以代码一律把「可用范围」写成「仅参考」。流 B 真正的价值是**文案和互动数据**——达人怎么讲这个
产品、什么角度数据好,是写 blog 和选题的依据,不是配图来源。

## 跑

**先确认三件事,缺一条就别往下跑**:

```bash
# ① 仓在不在(默认 ~/Stagehand;没有就 git clone git@github.com:Modian-com/Stagehand.git)
STAGEHAND=${STAGEHAND:-~/Stagehand} && cd $STAGEHAND/python && export PYTHONPATH=.
# ② OSS SDK 在不在(它在 pyproject 里但历史上没装过;该 venv 没 pip,只能 uv)
.venv/bin/python -c "import alibabacloud_oss_v2" || uv pip install --python .venv/bin/python alibabacloud-oss-v2
# ③ STS 网关通不通(内网无鉴权,期望 "code":0;不通说明不在公司网络,整条流跑不了)
curl -s -m 10 http://api-ai.modianinc.com:8080/oss/get_sts | head -c 60
```

`--with-video` 还需要 playwright + chromium(`python3 -m playwright install chromium`),不用视频就不管。

```bash
# ① 达人交付的原片 → 发 c_ 号
.venv/bin/python -m stagehand.creator_assets.cli ingest --delivery --creator "达人昵称" video.mp4 --note note.md
# ② 我们自己生成/加工的成品 → 发 g_ 号
.venv/bin/python -m stagehand.creator_assets.cli ingest --generated --title "labubu 头图" cover.jpg
# ③ 有笔记链接(表里已有种子行则合并更新,不新建)
.venv/bin/python -m stagehand.creator_assets.cli ingest --url "http://xhslink.com/o/xxx" 图1.jpg --cover 图1.jpg

# ④ 存量回灌(产出仅参考)
.venv/bin/python -m stagehand.creator_assets.cli scrape --dry-run --limit 5   # 先看抓到什么
.venv/bin/python -m stagehand.creator_assets.cli scrape --limit 5             # 真跑
.venv/bin/python -m stagehand.creator_assets.cli scrape                       # 跑完所有「待归档」
```

- 入库后人工补三件代码不知道的事(飞书表里直接改):**授权状态**、内容标签、关联达人/合作。
- `scrape` 默认只碰「待归档」的行,**断了直接重跑就是续跑**;抓不到的标「源已失效」+ 原因写备注,不重试。
- 表里原有的建联期互动数据若与抓到的不一致,**旧值先写进备注**再更新,不会凭空消失。
- 视频文件默认不归档(上行慢的机器上一个 18MB 视频要传十几分钟);要留存加 `--with-video`,
  下载走 `video-download` skill。
- 节流:默认每条 6 秒,串行。小红书反爬严格,**别并发、别调快**。

## 存储规则(代码已实现,勿手工拼路径)

```
mdfile/
  uploads/                      ← Stagehand 既有上传区,不碰
  assets/{YYYY}/{MM}/{素材ID}/   ← 入库年月;一个素材一个文件夹
      img_01.jpg img_02.jpg video.mp4 cover.jpg note.md
```

- 素材ID:`xhs_<noteid>` / `xhslink_<码>`(从链接)、`c_<日期>_<随机>`(达人交付)、`g_<日期>_<随机>`(自产)
- 文件名代码统一发号,原始文件名记进表「备注」
- **只增不改**:加工产出永远开新 `g_` 文件夹,不覆盖旧文件
- 读取 URL 用 `https://vd.moimg.net/<key>`(bucket 绑的自定义域名,与「内容资产」表口径一致)。
  **别用默认 endpoint `mdfile.oss-cn-beijing.aliyuncs.com`** —— 阿里云对默认域名强加
  `Content-Disposition: attachment` + `x-oss-force-download`,浏览器只能下载不能预览,
  上传时设 header 也压不掉,只能换域名
- 分类维度(IP / 标签 / 用途)一律留在表字段,不进路径——分类会变,OSS 没有移动

## 取用素材

查表,不扫 OSS。**先看「可用范围」再看好不好看**——「仅参考」的东西无论多好都不能对外发。

要配图(必须能对外):筛「可用范围≠仅参考 + 状态=已归档」,再按表现分层排。
要写作参考(什么都能看):按表现分层 S/A 筛,读「文案快照」。

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

- **「可用范围=仅参考」的素材一律不对外**:不上 blog、不上商品页、不投流、不发社媒。空白按仅参考处理。
- **未授权素材禁止用于投流和商品页**;表里没写授权的默认当未授权,先找运营补确认。
- **跨平台不原样搬运**:小红书爆款直接搬去 TikTok 会被判非原创限流,复用必须二次剪辑(产出存新 `g_` 素材)。
- bucket 是公共读、STS 网关无鉴权,**不要往 `assets/` 传任何敏感文件**(合同、凭证、内部资料)。
- 出现验证码 / 登录墙 / 平台警告 → **立刻停**,不换 IP、不挂代理、不做反检测对抗。
- xhslink 短链和带 `xsec_token` 的链接会过期——**合作发布后尽快归档**,别等要用时再找。

## 常见问题

- **`lark-cli` 报 99991679**:身份错了,换 `personal-li-shoushou`。
- **链接点开是下载不是预览**:用成默认 endpoint 了,换 `vd.moimg.net`。
- **想确认某素材是否已归档**:查表「状态」,别去 OSS 找(列目录会 403)。
- **`ModuleNotFoundError: alibabacloud_oss_v2`**:Stagehand 的 venv 里装一下(`uv pip install --python .venv/bin/python alibabacloud-oss-v2`),它在 pyproject 里但历史上没装过。
