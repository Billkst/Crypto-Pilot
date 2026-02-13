"""
Crypto-Pilot E2E UI 验收测试脚本。
使用 Playwright 自动化浏览器进行端到端界面交互验收。
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

# 测试结果收集
results = {
    "service_ok": False,
    "page_load_ok": False,
    "title_ok": False,
    "sidebar_ok": False,
    "prediction_ok": False,
    "chart_ok": False,
    "kpi_ok": False,
    "errors": []
}

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "test_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def save_screenshot(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  [截图] 已保存: {path}")
    return path

def main():
    print("=" * 60)
    print("  Crypto-Pilot E2E 界面交互验收测试")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        # ──── Step 2: 访问与视觉检查 ────
        print("\n[Step 2] 访问页面并进行视觉检查...")
        try:
            page.goto("http://localhost:8501", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
            # Streamlit 可能需要额外时间渲染
            page.wait_for_timeout(5000)
            results["page_load_ok"] = True
            results["service_ok"] = True
            print("  ✅ 页面加载成功")
        except Exception as e:
            results["errors"].append(f"页面加载失败: {e}")
            print(f"  ❌ 页面加载失败: {e}")
            save_screenshot(page, "error_page_load")
            browser.close()
            print_report()
            return

        save_screenshot(page, "01_initial_page")

        # 验收点 1: 页面标题是否包含 "Crypto-Pilot"
        print("\n  [验收点 1] 检查页面标题...")
        page_title = page.title()
        page_content = page.content()
        has_crypto_pilot = "Crypto-Pilot" in page_title or "Crypto-Pilot" in page_content
        results["title_ok"] = has_crypto_pilot
        if has_crypto_pilot:
            print(f"  ✅ 页面包含 'Crypto-Pilot' (title='{page_title}')")
        else:
            print(f"  ❌ 页面未找到 'Crypto-Pilot' (title='{page_title}')")

        # 验收点 2: 检查侧边栏
        print("\n  [验收点 2] 检查侧边栏元素...")
        sidebar_checks = []

        # 检查 Symbol 输入框
        try:
            # Streamlit sidebar 通常在 [data-testid="stSidebar"] 中
            sidebar = page.locator('[data-testid="stSidebar"]')
            sidebar_visible = sidebar.is_visible()
            if sidebar_visible:
                sidebar_checks.append("侧边栏可见")
            else:
                # 尝试点击展开侧边栏
                expand_btn = page.locator('[data-testid="collapsedControl"]')
                if expand_btn.is_visible():
                    expand_btn.click()
                    page.wait_for_timeout(1000)
                    sidebar_visible = sidebar.is_visible()
                    sidebar_checks.append(f"侧边栏展开后可见: {sidebar_visible}")
        except Exception as e:
            sidebar_checks.append(f"侧边栏检查异常: {e}")

        # 检查侧边栏中的文本内容
        try:
            sidebar_text = sidebar.inner_text()
            if "Symbol" in sidebar_text or "交易对" in sidebar_text:
                sidebar_checks.append("✅ 找到 Symbol/交易对 输入框")
            else:
                sidebar_checks.append("❌ 未找到 Symbol/交易对 标签")

            if "Threshold" in sidebar_text or "阈值" in sidebar_text:
                sidebar_checks.append("✅ 找到阈值滑块")
            else:
                sidebar_checks.append("❌ 未找到阈值滑块")

            if "Stop Loss" in sidebar_text or "止损" in sidebar_text:
                sidebar_checks.append("✅ 找到止损滑块")
            else:
                sidebar_checks.append("❌ 未找到止损滑块")

            if "Start Prediction" in sidebar_text or "开始预测" in sidebar_text:
                sidebar_checks.append("✅ 找到开始预测按钮")
            else:
                sidebar_checks.append("❌ 未找到开始预测按钮")

            results["sidebar_ok"] = all("✅" in c for c in sidebar_checks if "✅" in c or "❌" in c)
        except Exception as e:
            sidebar_checks.append(f"侧边栏内容读取异常: {e}")

        for check in sidebar_checks:
            print(f"    {check}")

        save_screenshot(page, "02_sidebar_check")

        # ──── Step 3: 模拟核心业务流 ────
        print("\n[Step 3] 模拟核心业务流...")

        # 动作 1: 修改 Symbol 输入框为 ETH/USDT
        print("  [动作] 输入交易对 ETH/USDT...")
        try:
            # 找到侧边栏中的文本输入框
            symbol_input = page.locator('[data-testid="stSidebar"] input[type="text"]').first
            if symbol_input.is_visible():
                symbol_input.click()
                symbol_input.fill("")  # 清空
                symbol_input.fill("ETH/USDT")
                page.wait_for_timeout(500)
                # 按 Enter 确认
                symbol_input.press("Enter")
                page.wait_for_timeout(2000)
                print("  ✅ 已输入 ETH/USDT")
            else:
                print("  ❌ Symbol 输入框不可见")
                results["errors"].append("Symbol 输入框不可见")
        except Exception as e:
            print(f"  ❌ 输入 Symbol 失败: {e}")
            results["errors"].append(f"输入 Symbol 失败: {e}")

        save_screenshot(page, "03_symbol_entered")

        # 动作 2: 点击 "开始预测" 按钮
        print("  [动作] 点击 '开始预测 (Start Prediction)' 按钮...")
        try:
            # 尝试多种选择器来定位按钮
            start_btn = page.locator('[data-testid="stSidebar"] button:has-text("开始预测")')
            if not start_btn.is_visible():
                start_btn = page.locator('[data-testid="stSidebar"] button:has-text("Start Prediction")')
            if not start_btn.is_visible():
                start_btn = page.locator('button:has-text("开始预测")')
            
            if start_btn.is_visible():
                start_btn.click()
                print("  ✅ 已点击开始预测按钮")
            else:
                print("  ❌ 未找到开始预测按钮")
                results["errors"].append("未找到开始预测按钮")
                save_screenshot(page, "error_no_start_button")
        except Exception as e:
            print(f"  ❌ 点击按钮失败: {e}")
            results["errors"].append(f"点击按钮失败: {e}")

        # 观察加载状态
        print("  [观察] 等待加载状态...")
        try:
            # 检查是否出现 Spinner
            page.wait_for_timeout(2000)
            save_screenshot(page, "04_loading_state")

            spinner_visible = False
            try:
                spinner = page.locator('[data-testid="stSpinner"]')
                spinner_visible = spinner.is_visible()
            except:
                pass
            
            status_text = page.locator('text="正在分析"')
            status_visible = False
            try:
                status_visible = status_text.is_visible()
            except:
                pass

            if spinner_visible or status_visible:
                print("  ✅ 检测到加载状态 (Spinner)")
            else:
                print("  ⚠️ 未检测到 Spinner (可能已加载完成或未触发)")

            # 等待预测完成 (最多 60 秒)
            print("  [等待] 等待预测完成 (最多 60 秒)...")
            for i in range(12):  # 12 * 5 = 60 seconds
                page.wait_for_timeout(5000)
                
                # 检查是否出现错误
                error_el = page.locator('[data-testid="stException"]')
                alert_el = page.locator('[data-testid="stAlert"]')
                
                # 检查是否有 st.error 消息 (红色错误框)
                error_visible = False
                try:
                    error_visible = error_el.is_visible()
                except:
                    pass
                
                if error_visible:
                    error_text = error_el.inner_text()
                    print(f"  ❌ 检测到 Traceback 错误!")
                    print(f"  错误内容: {error_text[:500]}")
                    results["errors"].append(f"页面错误: {error_text[:500]}")
                    save_screenshot(page, "05_error_traceback")
                    break

                # 检查是否预测完成 (出现 KPI 卡片或图表)
                success_el = page.locator('text="预测完成"')
                chart_el = page.locator('[data-testid="stPlotlyChart"]')
                metric_el = page.locator('[data-testid="stMetric"]')
                
                success_visible = False
                chart_visible = False
                metric_visible = False
                
                try:
                    success_visible = success_el.is_visible()
                except:
                    pass
                try:
                    chart_visible = chart_el.is_visible()
                except:
                    pass
                try:
                    metric_visible = metric_el.is_visible()
                except:
                    pass

                if success_visible or chart_visible or metric_visible:
                    print(f"  ✅ 预测完成！(耗时约 {(i+1)*5} 秒)")
                    results["prediction_ok"] = True
                    break
                
                print(f"    ... 等待中 ({(i+1)*5}s)")

                # 也检查 stAlert 是否是错误提示
                try:
                    if alert_el.is_visible():
                        alert_text = alert_el.inner_text()
                        if "错误" in alert_text or "Error" in alert_text:
                            print(f"  ❌ 检测到错误提示: {alert_text[:300]}")
                            results["errors"].append(f"Alert 错误: {alert_text[:300]}")
                            save_screenshot(page, "05_alert_error")
                            break
                except:
                    pass
            else:
                print("  ⚠️ 超时: 60 秒内未检测到预测完成")
                results["errors"].append("预测超时 (60s)")

        except Exception as e:
            print(f"  ❌ 等待过程异常: {e}")
            results["errors"].append(f"等待异常: {e}")

        save_screenshot(page, "06_after_prediction")

        # 验收点 3: 检查 K 线图
        print("\n  [验收点 3] 检查 K 线图渲染...")
        try:
            chart = page.locator('[data-testid="stPlotlyChart"]')
            if chart.is_visible():
                results["chart_ok"] = True
                print("  ✅ K 线图已渲染")
                
                # 尝试检查图表内容 (SVG / 颜色等)
                chart_html = chart.inner_html()
                has_gray = "gray" in chart_html.lower() or "grey" in chart_html.lower() or "#808080" in chart_html.lower() or "rgb(128" in chart_html.lower()
                has_blue = "blue" in chart_html.lower() or "#0000ff" in chart_html.lower() or "rgb(0, 0, 255" in chart_html.lower() or "royalblue" in chart_html.lower() or "#4169e1" in chart_html.lower()
                
                if has_gray:
                    print("  ✅ 检测到灰色 (历史) 元素")
                else:
                    print("  ⚠️ 未检测到明显的灰色元素 (可能颜色不同)")
                if has_blue:
                    print("  ✅ 检测到蓝色 (预测) 元素")
                else:
                    print("  ⚠️ 未检测到明显的蓝色元素 (可能颜色不同)")
            else:
                print("  ❌ K 线图未渲染")
        except Exception as e:
            print(f"  ❌ 图表检查异常: {e}")
            results["errors"].append(f"图表检查异常: {e}")

        # 验收点 4: 检查 KPI 卡片
        print("\n  [验收点 4] 检查 KPI 卡片...")
        try:
            metrics = page.locator('[data-testid="stMetric"]')
            metric_count = metrics.count()
            if metric_count > 0:
                results["kpi_ok"] = True
                print(f"  ✅ 找到 {metric_count} 个 KPI 卡片")
                for i in range(metric_count):
                    metric_text = metrics.nth(i).inner_text()
                    print(f"    卡片 {i+1}: {metric_text.strip()[:80]}")

                # 检查是否包含信号
                all_metric_text = metrics.all_inner_texts()
                all_text = " ".join(all_metric_text)
                if "BULLISH" in all_text or "BEARISH" in all_text or "NEUTRAL" in all_text:
                    print("  ✅ 检测到交易信号 (BULLISH/BEARISH/NEUTRAL)")
                else:
                    print("  ⚠️ 未在 KPI 中检测到明确的信号文本")
            else:
                print("  ❌ 未找到 KPI 卡片")
        except Exception as e:
            print(f"  ❌ KPI 检查异常: {e}")
            results["errors"].append(f"KPI 检查异常: {e}")

        save_screenshot(page, "07_final_state")

        browser.close()

    print_report()


def print_report():
    """打印最终测试报告。"""
    print("\n" + "=" * 60)
    print("  测试结果汇报")
    print("=" * 60)
    
    checks = [
        ("服务启动成功", results["service_ok"]),
        ("页面加载正常", results["page_load_ok"]),
        ("标题包含 Crypto-Pilot", results["title_ok"]),
        ("侧边栏元素完整", results["sidebar_ok"]),
        ("预测流程跑通", results["prediction_ok"]),
        ("图表渲染正确", results["chart_ok"]),
        ("KPI 卡片显示", results["kpi_ok"]),
    ]

    all_pass = True
    for name, passed in checks:
        icon = "✅" if passed else "❌"
        status = "通过" if passed else "失败"
        print(f"  {icon} {name}: {status}")
        if not passed:
            all_pass = False

    if results["errors"]:
        print(f"\n  ⚠️ 错误详情 ({len(results['errors'])} 个):")
        for err in results["errors"]:
            print(f"    - {err}")

    print("\n" + "-" * 60)
    conclusion = "✅ 综合结论: 通过" if all_pass else "❌ 综合结论: 失败"
    print(f"  {conclusion}")
    print("-" * 60)


if __name__ == "__main__":
    main()
