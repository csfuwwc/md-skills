"""Playwright 侧的胶水:截验证码 → 调 solve.py → 拟人轨迹拖动 → 失败刷新重试。

只依赖 playwright(调用方环境里本来就有);opencv 只在 solve.py 的独立 uv 环境里,
调用方 venv 不用装任何新东西。

    sys.path.insert(0, "<skill>/scripts")
    from playwright_slider import solve_with_retries

    result = await solve_with_retries(page, check=lambda: login_ok_event.is_set(), preset="tencent")

check 由调用方给:验证码过没过只有业务自己知道(看登录接口返回、看 URL 跳转都行)。
"""
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOLVE = Path(__file__).resolve().parent / "solve.py"

PRESETS = {
    # 腾讯天御 / 防水墙滑块(turing.captcha.qcloud.com)
    "tencent": {
        "frame_url": "captcha.qcloud.com",
        "image": "#slideBg",
        "piece": "#slideBlock",
        "handle": "#tcaptcha_drag_thumb",
        "refresh": "#reload",
    },
}


def _solver_argv():
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--quiet", "--script", str(SOLVE)]
    return [sys.executable, str(SOLVE)]  # 当前解释器自己装了 opencv 时也能跑


async def find_frame(page, selectors, timeout=20):
    """找到真正显示着验证码的 frame(页面上常有一个藏在屏外的同源 iframe)。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        for frame in page.frames:
            if selectors.get("frame_url") and selectors["frame_url"] not in frame.url:
                continue
            loc = frame.locator(selectors["image"]).first
            try:
                if await loc.count():
                    box = await loc.bounding_box()
                    if box and box["width"] > 50 and box["y"] >= 0:
                        return frame
            except Exception:  # noqa: BLE001 —— frame 可能正在导航
                pass
        await asyncio.sleep(0.5)
    raise TimeoutError("没找到可见的滑块验证码")


async def human_drag(page, x, y, dx):
    """先快后慢、带抖动和轻微过冲的拖动轨迹。匀速直线最容易被风控判成机器。"""
    await page.mouse.move(x - random.uniform(5, 15), y + random.uniform(-4, 4))
    await asyncio.sleep(random.uniform(0.1, 0.3))
    await page.mouse.move(x, y, steps=random.randint(3, 6))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.08, 0.2))
    overshoot = random.uniform(2, 5) if dx > 40 else 0
    steps = random.randint(22, 34)
    for i in range(1, steps + 1):
        t = i / steps
        eased = 1 - (1 - t) ** 3
        await page.mouse.move(x + (dx + overshoot) * eased, y + random.uniform(-1.2, 1.2))
        await asyncio.sleep(random.uniform(0.008, 0.028))
    if overshoot:
        await asyncio.sleep(random.uniform(0.05, 0.15))
        for i in range(1, 5):
            await page.mouse.move(x + dx + overshoot * (1 - i / 4), y + random.uniform(-0.6, 0.6))
            await asyncio.sleep(random.uniform(0.02, 0.05))
    await asyncio.sleep(random.uniform(0.05, 0.2))
    await page.mouse.up()


async def solve_slider(page, preset="tencent", selectors=None, workdir=None,
                       fallback_cmds=(), scale=1.0, timeout=20):
    """解一次:返回 solve.py 的结果 + 实际拖动距离。不判断成功与否。"""
    sel = {**PRESETS.get(preset, {}), **(selectors or {})}
    frame = await find_frame(page, sel, timeout)
    image = frame.locator(sel["image"]).first
    piece = frame.locator(sel["piece"]).first
    handle = frame.locator(sel["handle"]).first
    await asyncio.sleep(0.8)  # 等拼图块入场动画结束

    img_box = await image.bounding_box()
    piece_box = await piece.bounding_box()
    handle_box = await handle.bounding_box()
    if not (img_box and piece_box and handle_box):
        raise RuntimeError("验证码元素没有可见尺寸")

    workdir = Path(workdir or tempfile.mkdtemp(prefix="slider-"))
    shot = workdir / "slider-bg.png"
    await image.screenshot(path=str(shot))  # 元素截图会带上叠在上面的拼图块

    # 截图像素 / CSS 像素(高 DPI 下不是 1)
    ratio = await page.evaluate("window.devicePixelRatio") or 1
    rel = [(piece_box["x"] - img_box["x"]) * ratio, (piece_box["y"] - img_box["y"]) * ratio,
           piece_box["width"] * ratio, piece_box["height"] * ratio]

    argv = _solver_argv() + [str(shot), "--piece-box", ",".join(f"{v:.1f}" for v in rel)]
    for cmd in fallback_cmds:
        argv += ["--fallback-cmd", cmd]
    proc = await asyncio.to_thread(subprocess.run, argv, capture_output=True, text=True,
                                   timeout=900, env=os.environ.copy())
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise RuntimeError(f"solve.py 没有给出结果: {proc.stderr.strip()[-300:]}") from None
    result["image"] = str(shot)
    if not result.get("ok"):
        return result

    drag = result["dx"] / ratio * scale
    await human_drag(page, handle_box["x"] + handle_box["width"] / 2,
                     handle_box["y"] + handle_box["height"] / 2, drag)
    result["dragged"] = round(drag, 1)
    return result


async def refresh(page, preset="tencent", selectors=None):
    sel = {**PRESETS.get(preset, {}), **(selectors or {})}
    frame = await find_frame(page, sel, timeout=5)
    await frame.locator(sel["refresh"]).first.click()
    await asyncio.sleep(2)


async def solve_with_retries(page, check, attempts=3, settle=6, preset="tencent",
                             selectors=None, workdir=None, fallback_cmds=(), scale=1.0):
    """解 → 等 settle 秒问 check() → 不过就刷新再来,最多 attempts 次。

    check 可以是普通函数或 async 函数,返回真表示验证已通过。
    返回 {"passed": bool, "tries": [...每次 solve_slider 的结果...]}。
    """
    tries = []
    for n in range(attempts):
        if n:
            try:
                await refresh(page, preset, selectors)
            except Exception:  # noqa: BLE001 —— 失败后组件有时自己换了图
                await asyncio.sleep(2)
        result = await solve_slider(page, preset, selectors, workdir, fallback_cmds, scale)
        tries.append(result)
        if not result.get("ok"):
            continue
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settle
        while loop.time() < deadline:
            ok = check()
            if asyncio.iscoroutine(ok):
                ok = await ok
            if ok:
                return {"passed": True, "tries": tries}
            await asyncio.sleep(0.5)
    return {"passed": False, "tries": tries}
