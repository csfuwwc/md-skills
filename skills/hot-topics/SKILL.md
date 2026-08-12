---
name: hot-topics
description: 拉各平台的实时热榜(微博热搜、B站热门视频),用于选题、蹭热点、看今天大家在聊什么。走公开接口,不需要登录、不碰账号。触发场景:今天有什么热点、微博热搜、B站热门、热榜、蹭热点选题、最近流行什么、有什么可以蹭的话题。
---

# 平台热榜

```bash
python3 scripts/hot.py                    # 全部源
python3 scripts/hot.py weibo --limit 30   # 单个源
python3 scripts/hot.py --json             # 给机器读
```

```
── weibo ──
  1. C罗宣布结婚  (1,158,817)
     https://s.weibo.com/weibo?q=%23C罗宣布结婚%23
── bilibili ──
  1. 《影之刃零》预购开启，11分钟实机预告公开  (2,526,863)
     https://b23.tv/BV1Hmuv68EWW
```

`--json` 每条给 `{source, title, heat, url, extra}`;`extra.rank` 是**平台原始位次**
(丢掉空条目后不重排号,否则报出来的名次跟平台对不上)。退出码 `0` 至少一个源成功 / `1` 全挂。

| 源 | 拉什么 | 接口 |
|---|---|---|
| `weibo` | 热搜榜(~50 条) | `weibo.com/ajax/side/hotSearch` |
| `bilibili` | 热门视频榜 | `api.bilibili.com/x/web-interface/popular` |

## 怎么用这些热点

热榜给的是**话题词和标题**,不是可以直接发的内容。典型接法:

1. 拉热榜 → 人或模型挑出跟自家品类沾边的
2. 拿到话题词后再去**深挖**:`xiaohongshu-scraper` / `douyin-scraper` 看这个词下面别人怎么写、
   `bilibili-keywords-scraper` 找这个方向的 UP
3. 素材要存下来复用 → `oss-upload`

**别直接把热搜词当选题**。热搜里大量是社会新闻、明星八卦,跟品牌调性硬蹭会翻车;
`heat` 高只说明流量大,不说明适合你。

## 加新平台

往 `SOURCES` 里加一个 fetcher 就行,**别在调用方分支判断**。fetcher 契约:
`fetch_xxx(limit, get_json=None) -> [{source, title, heat, url, extra}]`,拉不到抛 `HotError`。

## 坑

- **微博裸调 403**:必须先访问 `weibo.com` 拿访客 cookie,带着同一个 cookie jar 再调接口。
  代码里已经做了,别把这层"优化"掉。
- **Referer 必须按源给**:B 站接口收到微博的 Referer 会直接 403。别做一个"通用 HTTP 客户端"
  把 header 统一了 —— 这个 skill 踩过。
- **接口是公开非官方的**,平台随时可能改。挂了就是挂了,`fail-closed` 抛错,**不要退化成
  静默返回空列表** —— 空榜和抓不到是两回事。
- 只读公开数据,不登录、不带账号 cookie。**别为了多拉点数据去挂登录态**,那是另一个风险等级。

## 相关

`aihot` 是 AI 圈资讯的专用热榜(另一个数据源);本 skill 是通用社媒热榜。
