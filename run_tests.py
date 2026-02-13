"""
Crypto-Pilot 一键测试脚本。
自动发现并执行 tests/ 目录下的所有测试用例。

用法:
    conda activate kronos
    python run_tests.py
"""

import sys
import unittest


def main():
    """发现并运行所有测试，打印彩色结果摘要。"""
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py", top_level_dir=".")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # ── 结果摘要 ──
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("\033[92m✅ 所有系统自检通过！后端链路 Data → Model → Strategy 畅通。\033[0m")
        sys.exit(0)
    else:
        failures = len(result.failures) + len(result.errors)
        print(f"\033[91m❌ 测试未通过 — {failures} 个失败/错误，请检查以上报错信息。\033[0m")
        sys.exit(1)


if __name__ == "__main__":
    main()
