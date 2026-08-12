---
name: oss-upload
description: 把本地的图片、视频或其他文件传进公司的阿里云 OSS,拿到可直接引用的公开链接。自动取 STS 临时凭证、按「类型/年月/内容哈希」命名、同内容不重传。触发场景:上传到 OSS、传图拿链接、把这个视频存到对象存储、抓下来的素材要个外链、图片托管、要个能公开访问的 URL。
---

# OSS 上传

一个动作:**本地文件 → OSS → 返回链接**。

```bash
python3 scripts/upload.py 图.jpg 片子.mp4
# https://vd.moimg.net/images/2026/08/3f9a1c2e8b74.jpg
# https://vd.moimg.net/videos/2026/08/7d8e9f0a1b2c.mp4
```

每行一个 URL,顺序与传入文件一致。要给程序读加 `--json`:

```json
{"ok": true, "files": [
  {"path": "图.jpg", "key": "images/2026/08/3f9a1c2e8b74.jpg",
   "url": "https://vd.moimg.net/images/2026/08/3f9a1c2e8b74.jpg",
   "bytes": 394088, "existed": false}], "failed": []}
```

退出码 `0` 全成功 / `1` 有失败。**换机器、换人第一件事跑 `python3 scripts/upload.py --check`**(真跑一遍上传+回读)。

## 命名规则(代码定,调用方无从干预)

```
{images|videos|files}/{年}/{月}/{内容sha256前12位}{后缀}
```

- **对象名由文件内容决定** → 同一个文件传多少次都落到同一个 key,天然幂等、自动去重、**永不误覆盖**(两个都叫 `cover.jpg` 的不同文件互不影响)
- 传之前先探一遍,已存在就直接返回链接不重传(`existed: true`),上行慢的机器上省的是几十分钟;真要重传加 `--force`
- 类型只分三个桶:图 → `images/`,视频 → `videos/`,**其他一律 `files/`**(文案、字幕、JSON、PDF 都行)
- 后缀统一小写,`.jpeg` 归到 `.jpg`,免得同一张图存两份
- 跨月的同一个文件会各存一份(key 含年月),这是有意的:按月归档好清理

## 不做什么

这个 skill **只上传**。被问到下面这些,直接说不支持,别自己想办法绕:

| 想干的事 | 结论 |
|---|---|
| 列目录 / 搜索已有文件 | **不支持**。STS 凭证没有 ListObjects 权限(403),查文件请查你自己的业务记录 |
| 删除 / 覆盖 / 改名已有对象 | **不支持**,也不打算支持。命名是内容哈希,改内容自然是新对象 |
| 下载 / 取回 OSS 上的文件 | **不支持**。公开读,直接 `curl -O <URL>` 就行 |
| 设权限 / 私有链接 / 签名 URL | **不支持**。桶是公共读,传上去就是公开的 |
| 传到别的桶或别的前缀 | **不支持**。改 `OSS_BUCKET` 等环境变量是部署配置,不是调用参数 |
| 记录到飞书 / 数据库 / 业务表 | **不是这个 skill 的事**,调用方自己拿着 URL 去写 |

## 红线

- **桶是公共读,STS 网关无鉴权** —— 传上去的东西等于公开发布。**绝不要传合同、凭证、身份信息、内部资料、未公开的商业数据**。
- **传别人的内容前先确认能不能用**。从社交平台抓下来的图片视频通常带水印和版权,能存进 OSS 不等于能对外发布 —— 授权与使用范围由调用方自己负责。
- **只在公司内网跑**。STS 网关是内网服务,外网连不上会直接报错;**不要试图绕过它去找长期密钥**。

## 排错

| 症状 | 原因 |
|---|---|
| `取不到 STS 凭证` | 不在公司内网。这个网关外网打不通,没有别的办法 |
| 链接点开是下载不是预览 | 用成默认 endpoint `mdfile.oss-cn-beijing.aliyuncs.com` 了。阿里云对默认域名强加 `Content-Disposition: attachment` + `x-oss-force-download`,**上传时设 header 也压不掉,只能用 `vd.moimg.net`** |
| HTTPS 证书告警 | `vd.moimg.net` 目前挂的是阿里云默认证书,SAN 里没有这个域名,运维在处理。临时可用 `http://` 验证内容 |
| 大文件传很久 | 上行带宽的事。境外机器传阿里云北京只有 ~18KB/s,4MB 就要几分钟;超时上限 `OSS_UPLOAD_TIMEOUT`(默认 1800 秒)|

## 部署坐标

bucket `mdfile` / region `cn-beijing` / STS 网关 `http://api-ai.modianinc.com:8080/oss/get_sts` / 读取域名 `https://vd.moimg.net`。
全部可用 `OSS_BUCKET`、`OSS_REGION`、`OSS_STS_URL`、`OSS_PUBLIC_BASE` 覆盖。

**零依赖**:只用 Python 标准库,OSS V4 签名是手写的,不需要 `pip install` 任何东西。
