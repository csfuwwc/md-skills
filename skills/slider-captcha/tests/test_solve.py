"""slider-captcha:cv 求解精度 / 外部求解器回退约定。不联网。

  uv run --with opencv-python-headless --with numpy python -m unittest discover -s tests
"""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import solve  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 真实腾讯滑块截图(背景元素区域)。piece_box = #slideBlock 的 68x68 元素框;
# expected_dx 是人工对齐拼图块和缺口左边缘量出来的,road 那张 204 在真实登录里一次通过。
CASES = {
    "tencent-road.png": ((26, 16, 68, 68), 204),
    "tencent-penguin.png": ((26, 38, 68, 68), 205),
    "tencent-koala.png": ((26, 14, 68, 68), 207),
}
TOLERANCE = 3


def fake_solver(tmp, body):
    path = os.path.join(tmp, "fake.sh")
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


class CvSolverTest(unittest.TestCase):
    def test_real_tencent_screenshots(self):
        for name, (box, expected) in CASES.items():
            with self.subTest(name):
                result = solve.solve(str(FIXTURES / name), list(box))
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["solver"], "cv")
                self.assertLessEqual(abs(result["dx"] - expected), TOLERANCE, result)

    def test_box_outside_image_is_reported_not_raised(self):
        result = solve.solve(str(FIXTURES / "tencent-road.png"), [900, 0, 68, 68])
        self.assertFalse(result["ok"])
        self.assertIn("超出", result["attempts"][0]["error"])


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.image = str(FIXTURES / "tencent-road.png")

    def test_plain_number_is_gap_x(self):
        cmd = fake_solver(self.tmp, "echo 230")
        result = solve.solve(self.image, [26, 16, 68, 68], fallback_cmds=[cmd], skip_cv=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["dx"], 204)  # 230 - 26

    def test_receives_image_and_box(self):
        cmd = fake_solver(self.tmp, 'echo "{\\"dx\\": 1, \\"seen\\": \\"$2\\"}" && test -f "$1"')
        result = solve.solve(self.image, [26, 16, 68, 68], fallback_cmds=[cmd], skip_cv=True)
        self.assertTrue(result["ok"], result)

    def test_low_cv_confidence_falls_through_in_order(self):
        broken = fake_solver(self.tmp, "exit 3")
        good = os.path.join(self.tmp, "good.sh")
        Path(good).write_text('#!/bin/sh\necho \'{"gap_x": 240}\'\n')
        os.chmod(good, 0o755)
        result = solve.solve(self.image, [26, 16, 68, 68], min_confidence=1.01,
                             fallback_cmds=[broken, good])
        self.assertTrue(result["ok"])
        self.assertEqual(result["solver"], "good.sh")
        self.assertEqual([a["accepted"] for a in result["attempts"]], [False, False, True])

    def test_all_fail_returns_not_ok(self):
        cmd = fake_solver(self.tmp, "echo nope")
        result = solve.solve(self.image, [26, 16, 68, 68], fallback_cmds=[cmd], skip_cv=True)
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
