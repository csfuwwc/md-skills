#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless>=4.8", "numpy>=1.24"]
# ///
"""滑块拼图:给一张验证码背景截图 + 拼图块在图里的框,算出要拖多远。

  uv run --script solve.py bg.png --piece-box 26,43,68,68
  {"ok": true, "solver": "cv", "dx": 204, "gap_x": 230, "confidence": 0.65, ...}

原理:拼图块里显示的就是缺口处的原图(只是被提亮),缺口是同一块被压暗。亮度线性变换不改
梯度的「形状」,所以拿拼图块中心区域的梯度幅值,在同一水平带里做归一化相关匹配,峰值就是缺口。
只取中心 50%:拼图块的元素框带透明留白,留白里露出的是起点处背景,会干扰匹配。

cv 置信度低于阈值时,按顺序调用 --fallback-cmd(可多次给)里的外部求解器:任何能读图、
往 stdout 打 {"gap_x": N} 或一个数字的程序都行 —— 视觉模型、人工回复、别家打码,本脚本不关心。
"""
import argparse
import json
import os
import shlex
import subprocess
import sys

DEFAULT_MIN_CONFIDENCE = 0.35
CENTER_FRACTION = 0.5


def parse_box(text):
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("piece-box 要写成 x,y,w,h(像素,相对背景图左上角)")
    return parts


def solve_cv(image_path, piece_box):
    import cv2
    import numpy as np

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"读不了图片: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    grad = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    h, w = gray.shape

    bx, by, bw, bh = piece_box
    side = int(min(bw, bh) * CENTER_FRACTION)
    tx = int(round(bx + (bw - side) / 2))
    ty = int(round(by + (bh - side) / 2))
    if side < 8 or tx < 0 or ty < 0 or tx + side > w or ty + side > h:
        raise ValueError(f"piece-box 超出图片范围或太小: box={piece_box} image={w}x{h}")

    pad = 4  # 允许缺口和拼图块上下差几像素
    y0, y1 = max(0, ty - pad), min(h, ty + side + pad)
    template = grad[ty:ty + side, tx:tx + side]
    scores = cv2.matchTemplate(grad[y0:y1, :], template, cv2.TM_CCOEFF_NORMED)
    columns = scores.max(axis=0)
    columns[: tx + side] = -1  # 缺口一定在拼图块右边
    best = int(columns.argmax())
    confidence = float(columns[best])

    # 第二峰离最高峰太近说明图里有相似纹理,置信度打折
    masked = columns.copy()
    masked[max(0, best - side // 2): best + side // 2] = -1
    runner_up = float(masked.max())
    margin = confidence - runner_up

    dx = best - tx
    return {
        "dx": int(dx),
        "gap_x": int(round(bx + dx)),
        "piece_x": int(round(bx)),
        "confidence": round(confidence, 3),
        "margin": round(margin, 3),
    }


def run_fallback(cmd, image_path, piece_box, timeout):
    env = {**os.environ,
           "SLIDER_IMAGE": image_path,
           "SLIDER_PIECE_BOX": ",".join(str(int(round(v))) for v in piece_box)}
    proc = subprocess.run(shlex.split(cmd) + [image_path, env["SLIDER_PIECE_BOX"]],
                          capture_output=True, text=True, timeout=timeout, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"退出码 {proc.returncode}: {proc.stderr.strip()[-300:]}")
    out = proc.stdout.strip().splitlines()
    if not out:
        raise RuntimeError("没有输出")
    last = out[-1].strip()
    try:
        data = json.loads(last)
    except json.JSONDecodeError:
        raise RuntimeError(f"输出不是 JSON 或数字: {last[:100]}") from None
    if isinstance(data, (int, float)):
        data = {"gap_x": data}
    if "dx" in data:
        dx = float(data["dx"])
    elif "gap_x" in data:
        dx = float(data["gap_x"]) - piece_box[0]
    else:
        raise RuntimeError("输出里没有 gap_x / dx")
    return {"dx": int(round(dx)), "gap_x": int(round(piece_box[0] + dx)),
            "piece_x": int(round(piece_box[0])), "confidence": data.get("confidence")}


def solve(image_path, piece_box, min_confidence=DEFAULT_MIN_CONFIDENCE,
          fallback_cmds=(), fallback_timeout=600, skip_cv=False):
    attempts = []
    if not skip_cv:
        try:
            result = solve_cv(image_path, piece_box)
            accepted = result["confidence"] >= min_confidence
            attempts.append({"solver": "cv", "accepted": accepted, **result})
            if accepted:
                return {"ok": True, "solver": "cv", **result, "attempts": attempts}
        except Exception as exc:  # noqa: BLE001 —— 任何失败都交给下一个求解器
            attempts.append({"solver": "cv", "accepted": False, "error": str(exc)})
    for cmd in fallback_cmds:
        name = os.path.basename(shlex.split(cmd)[0])
        try:
            result = run_fallback(cmd, image_path, piece_box, fallback_timeout)
            attempts.append({"solver": name, "accepted": True, **result})
            return {"ok": True, "solver": name, **result, "attempts": attempts}
        except Exception as exc:  # noqa: BLE001
            attempts.append({"solver": name, "accepted": False, "error": str(exc)})
    return {"ok": False, "attempts": attempts}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", help="验证码背景图(截图或原图都行,含缺口和拼图块)")
    ap.add_argument("--piece-box", type=parse_box, required=True,
                    help="拼图块在这张图里的 x,y,w,h(像素)")
    ap.add_argument("--min-confidence", type=float,
                    default=float(os.environ.get("SLIDER_MIN_CONFIDENCE", DEFAULT_MIN_CONFIDENCE)))
    ap.add_argument("--fallback-cmd", action="append", default=[],
                    help="cv 不够把握时依次调用的外部求解器;也可用环境变量 "
                         "SLIDER_CAPTCHA_FALLBACK_CMD(多个用 ;; 分隔)")
    ap.add_argument("--fallback-timeout", type=int, default=600)
    ap.add_argument("--no-cv", action="store_true", help="跳过 cv,直接走外部求解器")
    args = ap.parse_args(argv)

    fallbacks = list(args.fallback_cmd)
    env_cmds = os.environ.get("SLIDER_CAPTCHA_FALLBACK_CMD", "")
    fallbacks += [c.strip() for c in env_cmds.split(";;") if c.strip()]

    result = solve(args.image, args.piece_box, args.min_confidence, fallbacks,
                   args.fallback_timeout, args.no_cv)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
