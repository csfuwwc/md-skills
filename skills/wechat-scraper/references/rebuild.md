# 微信公众号网关重建参考

当需要理解、重建或恢复单篇文章兜底接口与公众号历史接口时读取本文。本文是运维参考，不代表已获得访问 VPS、部署服务、续期登录态或修改生产环境的授权。

## 目录

- [能力边界](#能力边界)
- [可复现源码基线](#可复现源码基线)
- [架构与数据流](#架构与数据流)
- [重建顺序](#重建顺序)
- [验收闸](#验收闸)
- [故障恢复](#故障恢复)

## 能力边界

| 能力 | 独立路径 | 网关依赖 |
| --- | --- | --- |
| 单篇公开文章 | `scripts/fetch_article.py`，再用 Playwright 兜底 | 仅作为第二级兜底，可选 |
| 最近/历史文章 | 无独立路径 | 必需，因为需要服务端持有的公众号后台会话 |

网关消失时，单篇抓取仍应通过独立路径工作。在网关恢复并通过验收前，不得声称历史文章能力可用。

## 可复现源码基线

重建前重新检查仓库权限、固定提交的文件树及各仓库 License。

| 项目 | 用途 | 固定基线 |
| --- | --- | --- |
| [wechat-article/wechat-article-exporter](https://github.com/wechat-article/wechat-article-exporter) | 登录、文章导出、公众号搜索和历史文章的上游参考 | [`55217d4`](https://github.com/wechat-article/wechat-article-exporter/commit/55217d4fdcefd004d42650ebf15116e7b820967a) |
| [csfuwwc/wechat-article-exporter](https://github.com/csfuwwc/wechat-article-exporter) | 部署 fork 与私有镜像构建 | [`069b794`](https://github.com/csfuwwc/wechat-article-exporter/commit/069b7940a4d0eca3d30aa6113fde781c13119678) |
| [Modian-com/Video-Picture-OSS-Auth](https://github.com/Modian-com/Video-Picture-OSS-Auth) | 对外网关、共享登录态注入和历史接口归一化 | [`0074a5e`](https://github.com/Modian-com/Video-Picture-OSS-Auth/commit/0074a5e61d948abd574a495096be2c9786a1beaa) |

固定版本中的关键位置：

- Exporter 登录：`server/api/web/login/`
- 会话持久化：`server/kv/cookie.ts`、`server/utils/CookieStore.ts`
- 公众号搜索与历史文章：`server/api/web/appmsg/`
- 单篇文章导出：`server/api/public/v1/download.get.ts`、`shared/utils/html.ts`
- 网关历史文章归一化：`internal/wechat/history.go`
- 部署镜像 Workflow：部署 fork 的 `.github/workflows/private-vps-image.yml`

上游文件名可能变化。重建时以固定提交的文件树为准，不要根据新分支猜路径。

## 架构与数据流

```text
Skill 或同事
  -> HTTPS 鉴权网关
     -> 仅内部可访问的 wechat-article-exporter
        -> 微信公开文章或公众号后台
        -> 持久化 /app/.data 卷
```

历史文章链路：Exporter 登录操作者自己的公众号后台，通过 `searchbiz` 搜索目标公众号，按昵称精确匹配得到 `fakeid`，调用 `appmsgpublish`，解析嵌套发布数据，过滤已删除文章，按时间倒序输出。此过程不会获得目标公众号的管理权限。

真实微信 token 与 Cookie 只保存在 Exporter 的 Nitro 持久化存储中。网关只保存随机 `auth-key` 引用并在服务端注入，调用方不得提供或获得真实会话。

## 重建顺序

1. 读取固定版本的 Exporter fork 与网关代码，确认是否需要适配微信最新响应。
2. 用 GitHub Actions 或受控构建器构建 `linux/amd64` 镜像，发布不可变 commit tag 并记录 digest。
3. Exporter 不映射公网端口，仅与网关加入同一个私有容器网络。
4. 配置文件型 Nitro Storage，并挂载持久化卷：

```yaml
services:
  wechat-exporter:
    image: ghcr.io/<owner>/wechat-article-exporter:<immutable-tag>
    restart: unless-stopped
    init: true
    environment:
      NODE_ENV: production
      NITRO_KV_DRIVER: fs
      NITRO_KV_BASE: .data/kv
    volumes:
      - wechat-data:/app/.data
    security_opt:
      - no-new-privileges:true

volumes:
  wechat-data:
```

5. 在网关前配置 HTTPS，并使用身份认证、IP 白名单或 VPN；不得直接暴露 Exporter。
6. 通过 Exporter 完成一次新的管理员扫码。二维码数据、`uuid`、token、Cookie、`auth-key` 和会话文件不得进入日志、Git、Skill 或笔记。
7. 网关状态目录权限设为 `0700`，其中的 `auth-key` 引用文件设为 `0600`；忽略调用方传入的会话键。
8. 全部验收通过后，才把 `references/api.md` 的 Base URL 指向恢复后的网关。

## 验收闸

- Exporter 与网关健康检查成功。
- Exporter 没有公网端口，只有网关能访问。
- 登录后 `.data/kv` 出现会话记录；重启后有效会话仍存在。
- 已知公众号按昵称精确匹配，不直接选择搜索第一项。
- `appmsgpublish` 能处理一次群发中的多篇文章、过滤删除项并按时间倒序。
- `GET /api/v1/account/recent` 限制 `limit` 为 1–20，并归一化标题、URL、作者、摘要和发布时间。
- `GET /api/public/v1/download` 只有通过正文语义校验才算成功。
- 登录失效返回 503；微信上游或解析失败返回 502。
- 日志中没有 Cookie、token、二维码内容、`uuid`、`auth-key` 或完整授权头。

## 故障恢复

- 503 通常表示共享登录态过期：由管理员重新扫码，不手工修改 Cookie。
- 502 可能表示微信响应结构变化：保留脱敏后的响应结构，对比固定版本，只修受影响的解析器并重跑验收。
- 持久化卷只能作为加密、限权的运维备份，不得提交或打包进 Skill。
- 镜像升级前记录当前 digest 并备份卷；验收失败时回滚到原 digest 和兼容卷。
- `references/api.md` 中的 Base URL 只是可替换的部署实例，不是能力本身。
