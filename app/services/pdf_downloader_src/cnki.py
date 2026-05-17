#!/usr/bin/env python3
"""
CNKI PDF 下载脚本 - 原样复刻自 docs/pdf-download/cnki_pdf_download.py
改动：支持外部浏览器注入（page 参数），退出条件化清理
"""

import sys
import time
import os
import json
import shutil
from pathlib import Path
from camoufox.addons import DefaultAddons

from .keyword_processor import sanitize_for_playwright, diagnose_keyword_issue


def is_captcha_page(page) -> bool:
    try:
        page_url = page.url.lower()
        if any(x in page_url for x in ['captcha', 'validate', 'verify', 'security']):
            return True
        try:
            captcha_iframes = page.locator(
                "iframe[src*='captcha'], iframe[src*='validate'], iframe[src*='verify'], iframe[src*='yidun'], iframe[src*='geetest']"
            ).count()
            if captcha_iframes > 0:
                return True
        except:
            pass
        captcha_selectors = [
            ".nc_wrapper", "#nc_1_n1z", ".geetest_panel", ".geetest_wrap",
            ".yidun_slider", ".yidun_slider", ".yidun_captcha",
            "#captcha", ".captcha-modal", ".modal-captcha",
        ]
        for selector in captcha_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0 and elem.is_visible():
                    bounding_box = elem.bounding_box()
                    if bounding_box and bounding_box['width'] > 50 and bounding_box['height'] > 30:
                        return True
            except:
                continue
        try:
            overlay = page.locator("div[class*='mask'], div[class*='overlay'], div[class*='cover']").all()
            for elem in overlay:
                if elem.is_visible():
                    bounding_box = elem.bounding_box()
                    if bounding_box and bounding_box['width'] > 500 and bounding_box['height'] > 400:
                        style = elem.get_attribute("style") or ""
                        if "z-index" in style or "position" in style:
                            return True
        except:
            pass
        return False
    except Exception as e:
        print(f"   检测验证码时出错: {e}")
        return False


def wait_for_captcha_completion(page, timeout: int = 60) -> bool:
    if not is_captcha_page(page):
        print("   页面无验证码")
        return True
    print(f"\n⚠️  检测到验证码")
    print(f"   请在浏览器中完成验证")
    print(f"   ========================================")
    print(f"   手动完成后，在此处输入 Y 并回车继续...")
    print(f"   或者等待 {timeout} 秒自动超时")
    print(f"   ========================================")
    start_time = time.time()
    check_interval = 2
    import threading
    user_confirmed = threading.Event()
    def listen_for_input():
        try:
            user_input = input("   >> ").strip().upper()
            if user_input == 'Y' or user_input == 'YES' or user_input == '':
                user_confirmed.set()
        except:
            pass
    input_thread = threading.Thread(target=listen_for_input, daemon=True)
    input_thread.start()
    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        remaining = timeout - elapsed
        if user_confirmed.is_set():
            print(f"\n✅ 用户确认验证码已完成!")
            time.sleep(2)
            return True
        if not is_captcha_page(page):
            print(f"\n✅ 验证码已自动消失! (耗时: {elapsed} 秒)")
            time.sleep(2)
            return True
        print(f"   等待验证码完成... {remaining} 秒 remaining...  (输入 Y 确认完成)", end="\r")
        time.sleep(check_interval)
    if not is_captcha_page(page):
        print(f"\n✅ 验证码已通过!")
        return True
    if user_confirmed.is_set():
        print(f"\n✅ 用户确认验证码已完成!")
        return True
    print(f"\n⏰ 验证码等待超时 (已等待 {timeout} 秒)")
    return False


def wait_for_element_or_handle_captcha(page, element_selector: str, timeout: int = 15) -> bool:
    try:
        element = page.locator(element_selector).first
        element.wait_for(timeout=timeout * 1000, state="visible")
        print(f"   目标元素已出现")
        return True
    except Exception:
        if is_captcha_page(page):
            print(f"   目标元素未出现，检测到验证码")
            return wait_for_captcha_completion(page, 60)
        else:
            print(f"   目标元素未出现，等待页面加载...")
            time.sleep(3)
            try:
                element = page.locator(element_selector).first
                element.wait_for(timeout=10000, state="visible")
                return True
            except:
                return is_captcha_page(page) and wait_for_captcha_completion(page, 60)


def cnki_download(keyword: str, output_dir: str = None, reuse_session: bool = True, page=None):
    """从 CNKI 检索并下载 PDF（使用 Camoufox）
    
    流程：
    1. 搜索 → 可能触发验证码
    2. 验证码 → 等待用户确认（60秒超时）→ 返回 "CAPTCHA_TIMEOUT"
    3. 正常 → 点击结果 → 下载 → 保存会话 → 关闭
    
    Args:
        keyword: 检索关键词
        output_dir: 自定义输出目录
        reuse_session: 是否复用已有会话（默认 True）
        page: 外部浏览器页面（None 时自建 Camoufox）
    
    Returns:
        str: 下载文件路径
        None: 其他错误
        "CAPTCHA_TIMEOUT": 验证码超时
    """
    print(f"检索关键词: {keyword}")
    print(f"会话复用: {'启用' if reuse_session else '禁用'}")

    if output_dir is None:
        output_dir = os.environ.get('PDF_OUTPUT_DIR', '')

    if output_dir:
        target_dir = Path(output_dir)
    else:
        target_dir = Path.home() / ".cache" / "scholar-pdf" / "cnki"

    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"保存目录: {target_dir}")

    own_browser = page is None
    result_path = None

    if own_browser:
        from camoufox.sync_api import Camoufox
        _browser_ctx = Camoufox(headless=True, geoip=False, humanize=False, os="linux",
                                exclude_addons=[DefaultAddons.UBO])
        browser = _browser_ctx.__enter__()
        context = browser.new_context(accept_downloads=True, locale="zh-CN")
        page = context.new_page()
    else:
        context = page.context

    # 会话文件（独立路径）
    session_dir = Path(os.environ.get('CNKI_SESSION_DIR', str(Path.home() / ".cache" / "cnki-session")))
    cookies_file = session_dir / "cookies.json"
    local_storage_file = session_dir / "local_storage.json"

    # 共享 cookies 文件（与 cnki-search 同源）
    shared_cookies_file = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cookies" / "cnki_cookies.json"

    def save_session(ctx, pg):
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            cookies = ctx.cookies()
            cookies_file.write_text(json.dumps(cookies, ensure_ascii=False), encoding='utf-8')
            # 同步到共享文件
            shared_cookies_file.parent.mkdir(parents=True, exist_ok=True)
            shared_cookies_file.write_text(json.dumps(cookies, ensure_ascii=False), encoding='utf-8')
            print(f"   ✓ Cookies 已保存")
            try:
                ls = pg.evaluate("() => { let items = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); items[k] = localStorage.getItem(k); } return items; }")
                local_storage_file.write_text(json.dumps(ls, ensure_ascii=False), encoding='utf-8')
                print(f"   ✓ LocalStorage 已保存")
            except Exception:
                pass
        except Exception:
            pass

    def load_session(ctx, pg):
        try:
            candidates = [cookies_file, shared_cookies_file]
            cf = None
            for c in candidates:
                if c.exists():
                    cf = c
                    break
            if cf is None:
                print("   没有找到保存的会话")
                return False
            cookies = json.loads(cf.read_text(encoding='utf-8'))
            ctx.add_cookies(cookies)
            print(f"   ✓ Cookies 已加载 ({cf.name})")
            if local_storage_file.exists():
                try:
                    ls = json.loads(local_storage_file.read_text(encoding='utf-8'))
                    pg.evaluate("(items) => { for (let k in items) localStorage.setItem(k, items[k]); }", ls)
                    print(f"   ✓ LocalStorage 已加载")
                except Exception:
                    pass
            return True
        except Exception:
            return False

    try:
        # ========== 1. 打开 CNKI 首页 ==========
        print("\n[1/7] 打开 CNKI 首页...")
        for attempt in range(3):
            try:
                page.goto("https://www.cnki.net/", timeout=60000, wait_until="domcontentloaded")
                break
            except Exception as e:
                if attempt < 2:
                    print(f"   网络超时，{10*(attempt+1)}秒后重试... ({attempt+1}/3)")
                    time.sleep(10 * (attempt + 1))
                else:
                    raise e
        time.sleep(3)

        if reuse_session and own_browser:
            print("   尝试加载保存的会话...")
            load_session(context, page)
            for attempt in range(3):
                try:
                    page.goto("https://www.cnki.net/", timeout=60000, wait_until="domcontentloaded")
                    break
                except Exception as e:
                    if attempt < 2:
                        print(f"   网络超时，{10*(attempt+1)}秒后重试... ({attempt+1}/3)")
                        time.sleep(10 * (attempt + 1))
                    else:
                        raise e
            time.sleep(2)

        # ========== 2. 输入检索词 ==========
        print("[2/7] 定位搜索框并输入关键词...")

        search_box = None
        selectors = [
            "textarea#txt_SearchText",
            "input[name='txt_search']",
            "textarea[placeholder*='检索']",
            "input[placeholder*='检索']"
        ]
        for sel in selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    search_box = elem
                    break
            except:
                continue

        if search_box is None:
            for elem in page.locator("textarea").all() + page.locator("input[type='text']").all():
                try:
                    if elem.is_visible():
                        search_box = elem
                        break
                except:
                    continue

        if search_box is None:
            raise Exception("无法找到搜索框")

        safe_keyword = sanitize_for_playwright(keyword)
        diagnosis = diagnose_keyword_issue(keyword)
        if diagnosis['issues']:
            print(f"   ⚠️  关键词包含特殊字符: {diagnosis['issues']}")

        search_box.fill(safe_keyword)
        time.sleep(1)
        print(f"   已输入关键词: {safe_keyword}")

        # ========== 3. 执行检索 ==========
        print("[3/7] 执行检索...")
        search_box.press("Enter")
        time.sleep(3)

        if "cnki.net" in page.url and ("search" not in page.url and "kns" not in page.url):
            print("   Enter 没反应，尝试点击检索按钮...")
            for btn_text in ["检索", "搜索", "Search"]:
                try:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        time.sleep(3)
                        break
                except:
                    continue

        # ========== 3.5 检测验证码 ==========
        print("   检查搜索结果...")
        result_selectors = [
            "table.result-table-list",
            ".result-table-list",
            "td.name a",
            "a.fz14",
        ]
        search_results_found = False
        for selector in result_selectors:
            if wait_for_element_or_handle_captcha(page, selector, timeout=10):
                search_results_found = True
                print(f"   搜索结果已加载")
                break
        if not search_results_found:
            page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)

        if is_captcha_page(page):
            print("   检测到验证码（搜索结果加载后）")
            if not wait_for_captcha_completion(page, 60):
                print("\n⚠️  验证码超时")
                result_path = "CAPTCHA_TIMEOUT"
                return result_path

        # ========== 4. 点击第一条结果的题名 ==========
        print("[4/7] 定位并点击第一条结果的题名...")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception as e:
            print(f"   等待 DOM 加载超时: {e}")
        time.sleep(3)

        title_link = None
        title_selectors = [
            "a.fz14",
            "td.name a",
            ".result-table-list td a[target='_blank']",
            "table.result-table-list a[target='_blank']",
            ".list-item a",
            ".result-table-list a",
            "a[class*='fz']",
            "td.name > a",
        ]
        for sel in title_selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    title_link = elem
                    print(f"   通过选择器找到: {sel}")
                    break
            except:
                continue

        if title_link is None:
            print("   尝试遍历所有链接...")
            all_links = page.locator("a").all()
            print(f"   页面共有 {len(all_links)} 个链接")
            for link in all_links:
                try:
                    if not link.is_visible():
                        continue
                    text = link.inner_text()
                    href = link.get_attribute("href") or ""
                    if text and len(text.strip()) > 5 and "pdf" not in text.lower() and "下载" not in text and "kns.cnki.net" in href:
                        title_link = link
                        print(f"   找到候选链接: {text[:40]}...")
                        break
                except:
                    continue

        if title_link is None:
            page.screenshot(path=str(target_dir / "debug_search.png"))
            print(f"   调试截图: {target_dir / 'debug_search.png'}")
            raise Exception("无法找到结果链接")

        title_text = title_link.inner_text().strip()
        print(f"   找到题名: {title_text[:60]}...")
        title_href = title_link.get_attribute("href")
        print(f"   获取到链接: {title_href[:60]}..." if title_href else "   无法获取链接")

        detail_page = None
        try:
            print("   尝试点击链接...")
            with context.expect_page(timeout=15000) as page_info:
                title_link.dispatch_event("click")
            detail_page = page_info.value
            print("   点击成功，新页面已打开")
        except Exception as click_error:
            print(f"   点击失败: {click_error}")
            if title_href and "kns.cnki.net" in title_href:
                print("   尝试直接导航到详情页...")
                try:
                    detail_page = context.new_page()
                    detail_page.goto(title_href, timeout=60000, wait_until="domcontentloaded")
                    time.sleep(3)
                    print("   直接导航成功")
                except Exception as nav_error:
                    print(f"   直接导航也失败: {nav_error}")
                    raise Exception(f"点击和直接导航都失败: {click_error}, {nav_error}")
            else:
                raise click_error

        if detail_page is None:
            raise Exception("无法打开详情页")
        detail_page.bring_to_front()
        time.sleep(3)

        detail_loaded = False
        detail_selectors = [
            "a:has-text('PDF下载')", "a:has-text('PDF')",
            "button:has-text('PDF下载')", "button:has-text('PDF')",
            ".btn-download", ".pdf a", "a[href*='pdf']",
            ".detail", ".article", "h1", "h2",
        ]
        for selector in detail_selectors:
            try:
                elem = detail_page.locator(selector).first
                if elem.count() > 0 and elem.is_visible():
                    detail_loaded = True
                    print(f"   详情页已加载 (找到: {selector})")
                    break
            except:
                continue

        if not detail_loaded:
            try:
                detail_page.wait_for_load_state("domcontentloaded", timeout=10000)
            except:
                pass
            time.sleep(2)
            for selector in detail_selectors:
                try:
                    elem = detail_page.locator(selector).first
                    if elem.count() > 0 and elem.is_visible():
                        detail_loaded = True
                        break
                except:
                    continue

        if is_captcha_page(detail_page):
            print("   检测到验证码（详情页加载后）")
            if not wait_for_captcha_completion(detail_page, 60):
                print("\n⚠️  验证码超时")
                result_path = "CAPTCHA_TIMEOUT"
                return result_path

        # ========== 5. 点击 PDF 下载按钮 ==========
        print("[5/7] 定位 PDF 下载按钮...")
        time.sleep(2)

        pdf_button = None
        pdf_selectors = [
            'a:has-text("PDF下载")', 'a:has-text("PDF")',
            'button:has-text("PDF下载")', 'button:has-text("PDF")',
        ]
        for sel in pdf_selectors:
            try:
                elem = detail_page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    pdf_button = elem
                    break
            except:
                continue

        if pdf_button is None:
            for link in detail_page.locator("a").all() + detail_page.locator("button").all():
                try:
                    if not link.is_visible():
                        continue
                    text = link.inner_text()
                    if text and "PDF" in text:
                        pdf_button = link
                        break
                except:
                    continue

        if pdf_button is None:
            detail_page.screenshot(path=str(target_dir / "debug_detail.png"))
            print(f"   已保存调试截图: {target_dir / 'debug_detail.png'}")
            raise Exception("无法找到 PDF 下载按钮")

        print("[6/7] 点击下载按钮...")
        pdf_href = pdf_button.get_attribute("href")
        print(f"   获取到 href: {pdf_href[:60]}..." if pdf_href else "   无 href")

        initial_page_count = len(context.pages)

        try:
            with detail_page.expect_download(timeout=60000) as download_info:
                pdf_button.click()
                time.sleep(2)
                current_page_count = len(context.pages)
                if current_page_count > initial_page_count:
                    print(f"   检测到新页面打开 ({current_page_count - initial_page_count} 个)")
                    new_page = context.pages[-1]
                    new_page.bring_to_front()
                    time.sleep(2)
                    has_login = new_page.locator("text=登录").count() > 0
                    if has_login:
                        print("   新页面检测到登录提示，尝试 IP 登录...")
                        ip_login_selectors = [
                            "text=IP登录", "text=IP 登录", "button:has-text('IP登录')",
                            "button:has-text('IP 登录')", ".ecp_IPLogin", "a:has-text('IP登录')",
                        ]
                        for selector in ip_login_selectors:
                            try:
                                ip_login = new_page.locator(selector).first
                                if ip_login.count() > 0 and ip_login.is_visible():
                                    ip_login.click()
                                    print("   已点击 IP 登录按钮")
                                    time.sleep(5)
                                    break
                            except:
                                continue
                        time.sleep(3)
                else:
                    has_login = detail_page.locator("text=登录").count() > 0
                    if has_login:
                        print("   检测到登录提示，尝试 IP 登录...")
                        ip_login_selectors = [
                            "text=IP登录", "text=IP 登录", "button:has-text('IP登录')",
                            "button:has-text('IP 登录')", ".ecp_IPLogin", "a:has-text('IP登录')",
                        ]
                        for selector in ip_login_selectors:
                            try:
                                ip_login = detail_page.locator(selector).first
                                if ip_login.count() > 0 and ip_login.is_visible():
                                    ip_login.click()
                                    print("   已点击 IP 登录按钮")
                                    time.sleep(5)
                                    break
                            except:
                                continue

            download = download_info.value
            suggested_filename = download.suggested_filename
            save_path = target_dir / suggested_filename
            download.save_as(str(save_path))
            result_path = str(save_path)

        except Exception as e:
            print(f"   下载等待超时: {e}")
            print("   尝试使用 href 直接下载...")
            if pdf_href and pdf_href.startswith("http"):
                try:
                    import requests
                    cookies = context.cookies()
                    cookie_dict = {c['name']: c['value'] for c in cookies}
                    response = requests.get(pdf_href, cookies=cookie_dict, timeout=60, stream=True)
                    if response.status_code == 200:
                        content_disposition = response.headers.get('Content-Disposition', '')
                        if 'filename=' in content_disposition:
                            import urllib.parse
                            filename = urllib.parse.unquote(content_disposition.split('filename=')[1].strip('"'))
                        else:
                            filename = f"{keyword[:20]}.pdf"
                        save_path = target_dir / filename
                        with open(save_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        result_path = str(save_path)
                        print(f"   通过 href 直接下载成功: {filename}")
                    else:
                        print(f"   href 下载失败，状态码: {response.status_code}")
                except Exception as download_error:
                    print(f"   href 直接下载失败: {download_error}")

            if result_path is None:
                print("   尝试检查下载目录...")
                downloads_dir = Path.home() / "Downloads"
                for i in range(30):
                    pdf_files = sorted(
                        downloads_dir.glob("*.pdf"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True
                    )
                    if pdf_files:
                        latest_pdf = pdf_files[0]
                        age = time.time() - latest_pdf.stat().st_mtime
                        if age < 120:
                            final_path = target_dir / latest_pdf.name
                            shutil.move(str(latest_pdf), str(final_path))
                            result_path = str(final_path)
                            break
                    time.sleep(1)
                    print(f"   等待中... ({i+1}/30)", end="\r")

        if result_path and Path(result_path).exists():
            size_mb = Path(result_path).stat().st_size / 1024 / 1024
            print("\n✅ 下载成功！")
            print(f"文件路径: {result_path}")
            if reuse_session and own_browser:
                print("\n保存会话...")
                save_session(context, page)
        else:
            print("\n⚠️  未检测到下载文件")
            result_path = None

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
        try:
            page.screenshot(path=str(target_dir / "error.png"))
            print(f"   错误截图已保存: {target_dir / 'error.png'}")
        except:
            pass
        result_path = None

    finally:
        if own_browser:
            try:
                page.close()
            except:
                pass
            try:
                context.close()
            except:
                pass
            try:
                _browser_ctx.__exit__(None, None, None)
            except:
                pass

    return result_path


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else "数智时代图书馆学本科专业知识体系与人才培养模式探索"
    reuse_session = True
    output_dir = None
    for arg in sys.argv[2:]:
        if arg == "--no-session":
            reuse_session = False
        elif arg.startswith("--output="):
            output_dir = arg.split("=", 1)[1]
    cnki_download(keyword, output_dir=output_dir, reuse_session=reuse_session)
