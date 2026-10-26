---
name: slider-captcha
category: 内容抓取
short-description: 自己账号登录遇到滑块拼图时，算出拖动距离并自动拖过去
description: 给浏览器自动化流程用的滑块拼图验证码求解器。截验证码背景 → OpenCV 算出拼图块到缺口的距离 → 拟人轨迹拖动 → 失败刷新重试；cv 没把握时按顺序调用外部求解器(视觉模型、人工回复都行,不绑定任何 AI 厂商)。内置腾讯天御/防水墙预设。触发场景:登录卡在「拖动下方滑块完成拼图」、Playwright 流程需要过滑块、会话过期要重新登录、给抓取脚本接验证码。
---

# 滑块验证码

一件事:**拼图滑块 → 算距离 → 拖过去**。只给自己有权登录的账号用。

两层,按需取用:

| 层 | 文件 | 依赖 | 什么时候用 |
|---|---|---|---|
| 求解器 | `scripts/solve.py` | opencv + numpy(`uv run --script` 自动装进独立环境) | 手里已经有截图,只要一个数字 |
| Playwright 胶水 | `scripts/playwright_slider.py` | 只要 playwright | 流程里有 `page`,想一步「解 + 拖 + 重试」 |

调用方的 venv **不用装 opencv**:胶水层用子进程 `uv run --script solve.py` 调求解器。

## 求解器(任何语言、任何流程都能调)

```bash
uv run --script scripts/solve.py bg.png --piece-box 26,43,68,68
# {"ok": true, "solver": "cv", "dx": 204, "gap_x": 230, "piece_x": 26, "confidence": 0.65, "margin": 0.13, "attempts": [...]}
```

- `bg.png`:验证码背景区域截图,**拼图块要在图上**(Playwright 元素截图会自动带上叠在上面的拼图块)
- `--piece-box`:拼图块在这张图里的 `x,y,w,h`,一般直接用拼图块元素的框(含透明留白也没关系,只取中心 50% 匹配)
- `dx`:拼图块要右移的**图片像素**;高 DPI 截图要除以 devicePixelRatio 再拖
- 退出码 `0` 解出 / `1` 所有求解器都失败

原理:拼图块里是缺口处的原图(被提亮),缺口是同一块被压暗,梯度形状不变 → 梯度幅值做归一化相关匹配,在同一水平带找峰。

### 外部求解器(不绑定模型)

cv 置信度低于 `--min-confidence`(默认 0.35)或报错时,依次调用:

```bash
uv run --script scripts/solve.py bg.png --piece-box 26,43,68,68 \
  --fallback-cmd "python3 my_vision.py" --fallback-cmd "/path/ask_human.sh"
# 或环境变量: SLIDER_CAPTCHA_FALLBACK_CMD="python3 my_vision.py;;/path/ask_human.sh"
```

外部命令的约定:

- 参数:`<图片路径> <x,y,w,h>`,同时有环境变量 `SLIDER_IMAGE` / `SLIDER_PIECE_BOX`
- 输出:stdout **最后一行**是 `{"gap_x": N}`、`{"dx": N}` 或一个纯数字(视为 gap_x,缺口左边缘的图片 x 坐标)
- 退出码非 0 = 失败,轮到下一个

视觉模型就写个脚本把图发给任意多模态 API 让它回缺口 x;人工就把图发到 IM 等人回一个数。**这些属于业务侧,不放进本 skill。**

## Playwright 胶水

```python
sys.path.insert(0, os.path.expanduser("~/.claude/skills/slider-captcha/scripts"))
from playwright_slider import solve_with_retries

login_ok = {"v": False}   # 业务自己判断成功:比如监听登录接口返回 token
result = await solve_with_retries(page, check=lambda: login_ok["v"], preset="tencent", attempts=3)
# {"passed": True, "tries": [{"ok": True, "solver": "cv", "dx": 208, "confidence": 0.62, "dragged": 208.0, ...}]}
```

- 自动找**可见**的验证码 frame(页面常有一个藏在屏外的同源 iframe,别用 `.first`)
- 拖动轨迹先快后慢 + 上下抖动 + 轻微过冲回拉;匀速直线最容易被风控判成机器
- `check` 普通函数或 async 都行;不过就点刷新换图再来
- 其他滑块:`selectors={"frame_url":..., "image":..., "piece":..., "handle":..., "refresh":...}` 覆盖预设;拼图块和滑块不是 1:1 移动时传 `scale`

### 预设

| 预设 | frame | 背景 | 拼图块 | 滑块 | 刷新 |
|---|---|---|---|---|---|
| `tencent` | `captcha.qcloud.com` | `#slideBg` | `#slideBlock` | `#tcaptcha_drag_thumb` | `#reload` |

## 实测

腾讯天御滑块(2026-10-26):离线 3 张真实截图误差 ≤3px;真实登录连跑 3 次全部首次通过(confidence 0.63–0.90)。

```bash
cd skills/slider-captcha
uv run --with opencv-python-headless --with numpy python -m unittest discover -s tests
```

## 红线

- **只用于自己有权登录的账号**。不批量注册、不撞库、不替别人过验证码
- 只在会话过期需要重登时调用,别每次跑任务都登录:频繁登录会触发更难的题型或封号
- 用自动化过验证码可能违反目标站点服务条款,接入前由账号持有人决定
- 截图里可能有账号信息:调用方截图时只截验证码元素,别截整页

## 不做什么

| 想干的事 | 结论 |
|---|---|
| 点选文字/图标、旋转图、短信/邮箱验证码 | **不支持**,只做水平滑块拼图 |
| 判断验证是否通过 | **调用方的事**(看登录接口/跳转),本 skill 只给 `check` 钩子 |
| 内置某家视觉模型或飞书人工通道 | **不内置**。走外部求解器约定,业务侧自己挂 |
| 绕过/伪造验证码票据、逆向加密参数 | **不做** |
