"""CNKI professional search interactor — uses 专业检索 tab with boolean expression."""

from __future__ import annotations

import logging
import random
import re
import shutil
import time as _time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from playwright.sync_api import Locator, Page

from .browser import CnkiBrowser
from .exceptions import CaptchaError, ExportProcessingError, NavigationStateError, NoResultsError, TimeoutError, ValidationError
from .playwright_helpers import (
    click_first_available,
    disable_checkbox,
    enable_checkbox,
    ensure_checkbox_checked,
    first_visible_locator,
    set_input_value,
    wait_for_any_selector,
)

logger = logging.getLogger("cnki.professional_interactor")

DATE_RANGE_LABEL_MAP = {
    "week": "最近一周",
    "month": "最近一月",
    "half-year": "最近半年",
    "year": "最近一年",
    "ytd": "今年迄今",
    "last-year": "上一年度",
}

NEXT_PAGE_MAX_RETRIES = 3
NEXT_PAGE_RETRY_DELAY = 1
EXPORT_BATCH_SIZE = 500
EXPORT_PAGE_READY_SELECTORS = (
    ".export-sidebar-a",
    ".export-sidebar-a .formatlist",
    "li.current a[displaymode='selfDefine']",
    "a[displaymode='selfDefine']",
    "#litoexcel",
    "#litotxt",
    ".check-labels",
)


class ProfessionalCnkiInteractor:
    """Sync CNKI professional-search interactor — runs in thread pool via asyncio.to_thread."""

    def __init__(self, browser: CnkiBrowser, output_dir: str | Path):
        self.browser = browser
        self.page: Page = browser.page
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._tmp_dir = self.output_dir / "_tmp"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════
    #  FORM — professional search
    # ═══════════════════════════════════════════════════════════

    def _disable_checkbox(self, selector: str) -> None:
        disable_checkbox(self.page, selector, logger=logger, verify_unchecked=True)

    def _enable_checkbox(self, selector: str) -> None:
        enable_checkbox(self.page, selector, logger=logger)

    def _click_first_available(self, selectors: list[str], page: Optional[Page] = None) -> bool:
        return click_first_available(page or self.page, selectors, timeout_ms=500)

    def _first_visible_locator(self, selectors: list[str], page: Optional[Page] = None) -> Optional[Locator]:
        return first_visible_locator(page or self.page, selectors, timeout_ms=500)

    def _build_professional_query(self, group_a: list[str], group_b: list[str], au_group: list[str] | None = None, fu_group: list[str] | None = None) -> str:
        def _quote(kw: str) -> str:
            kw = kw.replace("'", "\\'")
            return f"'{kw}'"

        base = None

        if group_a or group_b:
            a_expr = " + ".join(_quote(kw) for kw in group_a)
            b_expr = " + ".join(_quote(kw) for kw in group_b)
            if group_a and group_b:
                base = (
                    f"(SU=({a_expr}) AND SU=({b_expr}))"
                    f" OR "
                    f"(TKA=({a_expr}) AND TKA=({b_expr}))"
                )
            else:
                expr = a_expr if group_a else b_expr
                base = f"SU=({expr}) OR TKA=({expr})"

        if au_group:
            au_expr = " + ".join(_quote(au) for au in au_group)
            if base:
                base = f"({base}) AND AU=({au_expr})"
            else:
                base = f"AU=({au_expr})"

        if fu_group:
            fu_expr = " + ".join(_quote(fu) for fu in fu_group)
            if base:
                base = f"({base}) AND FU % ({fu_expr})"
            else:
                base = f"FU % ({fu_expr})"

        return base

    def _switch_to_professional_tab(self) -> None:
        deadline = _time.time() + 15
        while _time.time() < deadline:
            tab = self.page.locator("li[name='majorSearch']").first
            if tab.count() > 0:
                try:
                    tab.click()
                    _time.sleep(0.5)
                    return
                except Exception as exc:
                    logger.debug(f"点击专业检索tab失败: {exc}")
            _time.sleep(0.3)
        raise ValidationError("未找到专业检索tab")

    def _fill_professional_search_form(
        self,
        group_a: list[str],
        group_b: list[str],
        date_from: Optional[str],
        date_to: Optional[str],
        core_only: bool,
        include_no_fulltext: bool,
        synonym_extend: bool = False,
        date_range: Optional[str] = None,
        au_group: list[str] | None = None,
        fu_group: list[str] | None = None,
    ) -> None:
        self._disable_checkbox("input[data-id='EN'][name='onlyChecked']")
        if synonym_extend:
            self._enable_checkbox("input[data-id='TY'][name='onlyChecked']")

        self._switch_to_professional_tab()

        query_str = self._build_professional_query(group_a, group_b, au_group=au_group, fu_group=fu_group)
        textarea = self.page.locator("textarea.textarea-major.majorSearch").first
        if textarea.count() == 0:
            textarea = self.page.locator("textarea.majorSearch").first
        if textarea.count() == 0:
            raise ValidationError("未找到专业检索输入框")
        textarea.fill(query_str)

        if date_range:
            self._set_date_range_dropdown(date_range)
        else:
            self._set_year_input_value(["input[placeholder='起始年']", "input[placeholder*='起始']"], date_from or "")
            self._set_year_input_value(["input[placeholder='结束年']", "input[placeholder*='结束']"], date_to or "")

        if include_no_fulltext:
            self._disable_checkbox("#onlyfulltext")
        if core_only:
            self._disable_checkbox("input[name='all']")
            for sel in [
                "input[key='LYBSM'][value='P12']", "input[key='SI'][value='Y']",
                "input[key='EI'][value='Y']", "input[key='HX'][value='Y']",
                "input[key='CSI'][value='Y']", "input[key='CSD'][value='Y']",
                "input[key='AMI'][value='P13']",
            ]:
                self._enable_checkbox(sel)

    def _select_dropdown_option(self, trigger: Locator, option: Locator, force: bool = False) -> None:
        deadline = _time.time() + 30
        while _time.time() < deadline:
            try:
                trigger.wait_for(state="visible", timeout=500)
                trigger.click()
                option.wait_for(state="visible", timeout=500)
                option.click(force=force)
                return
            except Exception as exc:
                logger.debug(f"等待下拉项失败: {exc}")
                _time.sleep(0.2)
        raise ValidationError("下拉选项不存在")

    def _set_year_input_value(self, selectors: list[str], value: str) -> None:
        locator = self._first_visible_locator(selectors)
        if locator is None:
            return
        locator.evaluate("""
            (element, inputValue) => {
                const normalizedValue = inputValue || '';
                element.removeAttribute('readonly');
                element.focus();
                element.value = normalizedValue;
                element.setAttribute('value', normalizedValue);
                element.setAttribute('txt', normalizedValue);
                element.setAttribute('condition', normalizedValue ? `(${normalizedValue})` : '');
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: '0' }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
                element.dispatchEvent(new Event('blur', { bubbles: true }));
            }
        """, value)

    def _set_date_range_dropdown(self, date_range: str) -> None:
        label = DATE_RANGE_LABEL_MAP.get(date_range)
        if not label:
            raise ValidationError(f"不支持的更新时间范围: {date_range}")
        container = self.page.locator(".tit-dropdown-box").first
        if container.count() == 0:
            raise ValidationError("未找到更新时间下拉框")
        trigger = container.locator(".sort-default").first
        trigger.click()
        option = container.locator(".sort-list a").filter(has_text=label).first
        if option.count() == 0:
            raise ValidationError(f"未找到更新时间下拉选项: {label}")
        option.click()

    def _submit_search(self) -> None:
        if not self._click_first_available(["input.btn-search", "div.search", ".btn-search"]):
            raise ValidationError("未找到检索提交按钮")
        self._dismiss_dialog_if_present()

    def _set_results_per_page(self, export_limit: int, total_results: int) -> None:
        if export_limit <= 20 or total_results <= 20:
            return
        try:
            dropdown = self.page.locator("#perPageDiv .sort-default").first
            if dropdown.count() == 0:
                return
            previous_rows = self.page.locator(".result-table-list tbody tr").count()
            dropdown.click()
            option = self.page.locator("#perPageDiv .sort-list li[data-val='50'] a").first
            if option.count() == 0:
                option = self.page.locator("#perPageDiv .sort-list a").filter(has_text="50").first
            if option.count() == 0:
                return
            previous_page = self._results_summary_page()
            option.click()
            self._wait_for_results_page_changed(previous_page, previous_rows)
        except Exception as exc:
            logger.debug(f"设置每页50条失败: {exc}")

    # ═══════════════════════════════════════════════════════════
    #  NAVIGATION
    # ═══════════════════════════════════════════════════════════

    def _is_search_page(self) -> bool:
        for sel in ["#gradetxt", "input[placeholder='结束年']", "textarea.majorSearch", "#onlyfulltext", "input.btn-search"]:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    loc.wait_for(state="visible", timeout=200)
                    return True
            except Exception:
                continue
        return False

    def _ensure_captcha_cleared(self) -> None:
        if self.browser.is_captcha_visible():
            self.browser.wait_for_captcha_completion()

    def _dismiss_dialog_if_present(self) -> None:
        dialog = self.page.locator(".layui-layer-dialog").first
        if dialog.count() == 0:
            return
        confirm = self.page.locator(".layui-layer-btn0").first
        if confirm.count() > 0:
            confirm.click()

    def _wait_for_results_ready(self) -> None:
        deadline = _time.time() + 60
        while _time.time() < deadline:
            self._ensure_captcha_cleared()
            if self.page.locator(".result-table-list tbody tr").count() > 0:
                return
            if self.page.locator("#ModuleSearchResult .no-content").count() > 0:
                return
            if self.page.locator(".pagerTitleCell").count() > 0:
                text = self.page.locator(".pagerTitleCell").first.inner_text()
                if "条结果" in text:
                    return
            _time.sleep(0.5)
        raise TimeoutError("等待结果页超时")

    def _results_summary_page(self) -> str:
        try:
            return self.page.locator(".countPageMark").first.inner_text()
        except Exception:
            return ""

    def _first_result_title(self) -> str:
        try:
            return self.page.locator("td.name a.fz14").first.inner_text().strip()
        except Exception:
            return ""

    def _current_sort_text(self) -> str:
        try:
            loc = self.page.locator("#orderList li.cur").first
            if loc.count() > 0:
                return loc.inner_text().strip()
        except Exception:
            pass
        return ""

    def _has_results_state_changed(self, prev_url: str, prev_page: str, prev_title: str, prev_sort: str) -> bool:
        try:
            if self.page.url != prev_url:
                return True
            if self._results_summary_page() != prev_page:
                return True
            if self._first_result_title() != prev_title:
                return True
            if self._current_sort_text() != prev_sort:
                return True
        except Exception:
            pass
        return False

    def _wait_for_results_changed(self, prev_url: str, prev_page: str, prev_title: str, prev_sort: str, timeout: float = 90) -> None:
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            self._ensure_captcha_cleared()
            try:
                if self._has_results_state_changed(prev_url, prev_page, prev_title, prev_sort):
                    return
            except Exception:
                pass
            _time.sleep(0.5)
        raise TimeoutError("等待结果页变化超时")

    def _wait_for_results_page_changed(self, prev_page: str, prev_rows: int) -> None:
        deadline = _time.time() + 90
        while _time.time() < deadline:
            try:
                cur_page = self._results_summary_page()
                cur_rows = self.page.locator(".result-table-list tbody tr").count()
                if cur_page != prev_page or cur_rows != prev_rows:
                    return
            except Exception:
                pass
            _time.sleep(0.5)

    def _goto_next_results_page(self) -> bool:
        prev_url = self.page.url
        prev_page = self._results_summary_page()
        prev_title = self._first_result_title()
        prev_sort = self._current_sort_text()
        last_error: Optional[Exception] = None

        for attempt in range(1, NEXT_PAGE_MAX_RETRIES + 1):
            next_link = self._find_next_page_link()
            if next_link is None:
                return False
            cls = next_link.get_attribute("class") or ""
            if "disabled" in cls:
                return False

            try:
                try:
                    next_link.scroll_into_view_if_needed(timeout=10000)
                except Exception:
                    pass
                if attempt < NEXT_PAGE_MAX_RETRIES:
                    next_link.click(timeout=10000, no_wait_after=True)
                else:
                    try:
                        next_link.click(timeout=10000, no_wait_after=True)
                    except Exception:
                        next_link.evaluate("(el) => el.click()")

                self._wait_for_results_changed(prev_url, prev_page, prev_title, prev_sort, timeout=90)
                return True
            except Exception as exc:
                last_error = exc
                try:
                    if self._has_results_state_changed(prev_url, prev_page, prev_title, prev_sort):
                        return True
                except Exception:
                    pass
                logger.warning(f"翻页失败重试: attempt={attempt}/{NEXT_PAGE_MAX_RETRIES}, error={exc}")
                self._dismiss_dialog_if_present()
                self._ensure_captcha_cleared()
                if attempt < NEXT_PAGE_MAX_RETRIES:
                    _time.sleep(NEXT_PAGE_RETRY_DELAY)

        raise TimeoutError(f"翻页失败，已重试{NEXT_PAGE_MAX_RETRIES}次: {last_error}")

    def _find_next_page_link(self) -> Optional[Locator]:
        for sel in ["#PageNext", "#Page_next_top", "a#Page_next_top", ".pages a"]:
            group = self.page.locator(sel)
            for i in range(group.count()):
                loc = group.nth(i)
                try:
                    text = loc.inner_text().strip()
                except Exception:
                    text = ""
                if sel == ".pages a" and "下一页" not in text:
                    continue
                return loc
        return None

    # ═══════════════════════════════════════════════════════════
    #  SELECTION
    # ═══════════════════════════════════════════════════════════

    def _clear_selected_results(self) -> None:
        clear_link = self.page.locator(".checkcount a").filter(has_text="清除").first
        if clear_link.count() > 0:
            try:
                clear_link.click()
                _time.sleep(0.3)
            except Exception:
                pass

    def _select_rows_on_current_page(self, row_offset: int, page_target_count: int, row_count: int) -> int:
        cb_locator = self.page.locator(".result-table-list tbody input.cbItem")
        if row_offset == 0 and page_target_count == row_count and self.page.locator("#selectCheckAll1").count() > 0:
            ensure_checkbox_checked(self.page, self.page.locator("#selectCheckAll1").first, selector="#selectCheckAll1")
        else:
            for idx in range(row_offset, row_offset + page_target_count):
                checkbox = cb_locator.nth(idx)
                ensure_checkbox_checked(self.page, checkbox, selector=f"cbItem[{idx}]")

        selected = self._count_checked(cb_locator, row_offset, page_target_count)
        if selected >= page_target_count:
            return selected

        missing = self._find_unchecked(cb_locator, row_offset, page_target_count)
        if missing:
            for idx in missing:
                ensure_checkbox_checked(self.page, cb_locator.nth(idx), selector=f"cbItem_retry[{idx}]")
            selected = self._count_checked(cb_locator, row_offset, page_target_count)
        return selected

    def _count_checked(self, cb_locator: Locator, offset: int, count: int) -> int:
        n = 0
        for i in range(offset, offset + count):
            try:
                if cb_locator.nth(i).is_checked():
                    n += 1
            except Exception:
                pass
        return n

    def _find_unchecked(self, cb_locator: Locator, offset: int, count: int) -> list[int]:
        unchecked = []
        for i in range(offset, offset + count):
            try:
                if not cb_locator.nth(i).is_checked():
                    unchecked.append(i)
            except Exception:
                unchecked.append(i)
        return unchecked

    def _select_batch(self, export_limit: int, row_offset: int = 0) -> dict:
        remaining = export_limit
        selected = 0
        current_offset = row_offset
        start_page = 0
        end_page = 0
        reached_end = False

        while remaining > 0:
            self._wait_for_results_ready()
            row_count = self.page.locator(".result-table-list tbody tr").count()
            if row_count == 0:
                break
            if current_offset >= row_count:
                if not self._goto_next_results_page():
                    reached_end = True
                    break
                current_offset = 0
                continue

            cp = self._current_page_number()
            if start_page <= 0:
                start_page = cp
            end_page = cp
            page_target = min(row_count - current_offset, remaining)
            actual = self._select_rows_on_current_page(current_offset, page_target, row_count)
            selected += actual
            remaining = export_limit - selected
            current_offset += page_target
            if remaining <= 0:
                break
            if current_offset < row_count:
                continue
            if not self._goto_next_results_page():
                reached_end = True
                break
            current_offset = 0

        if selected == 0:
            raise ValidationError("未选中任何文献，无法导出")
        return {"selected": selected, "reached_end": reached_end}

    def _current_page_number(self) -> int:
        try:
            text = self._results_summary_page()
            m = re.match(r"(\d+)", text)
            return int(m.group(1)) if m else 0
        except Exception:
            return 0

    # ═══════════════════════════════════════════════════════════
    #  EXPORT
    # ═══════════════════════════════════════════════════════════

    def _click_link_by_text(self, text: str, page: Optional[Page] = None) -> None:
        target = page or self.page
        deadline = _time.time() + 90
        while _time.time() < deadline:
            links = target.locator("a").filter(has_text=text)
            if links.count() > 0:
                for i in range(links.count()):
                    link = links.nth(i)
                    try:
                        link.wait_for(state="visible", timeout=800)
                        link.click()
                        return
                    except Exception:
                        pass
            _time.sleep(0.2)
        raise TimeoutError(f"等待链接超时: {text}")

    def _export_batch(self, query_label: str, batch_index: int) -> tuple[Path, Path]:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = self._slug(query_label)[:40]
        excel_path = self.output_dir / f"{timestamp}-{slug}-batch{batch_index:03d}-metadata.xlsx"
        txt_path = self.output_dir / f"{timestamp}-{slug}-batch{batch_index:03d}-reference.txt"

        self._click_link_by_text("导出与分析")
        self._click_link_by_text("导出文献")

        export_page = self._open_custom_export_page()
        if export_page is None:
            self._login_personal_account()
            self._click_link_by_text("导出与分析")
            self._click_link_by_text("导出文献")
            export_page = self._open_custom_export_page()
        if export_page is None:
            raise NavigationStateError("未能打开自定义导出页面")

        try:
            export_page.wait_for_load_state("domcontentloaded", timeout=15000)
            wait_for_any_selector(export_page, list(EXPORT_PAGE_READY_SELECTORS),
                                  timeout_seconds=90, poll_interval_seconds=0.2, wait_timeout_ms=300)

            self._click_link_by_text("全选", page=export_page)
            _time.sleep(0.3)

            with export_page.expect_download(timeout=60000) as dl:
                if not click_first_available(export_page, ["#litoexcel"], timeout_ms=500):
                    raise ValidationError("未找到Excel导出按钮")
            tmp_file = dl.value
            tmp_xls = self._tmp_dir / f"batch{batch_index:03d}.xls"
            tmp_file.save_as(str(tmp_xls))
            self._process_exported_excel(tmp_xls, excel_path)

            ref_mode = click_first_available(export_page, ["a[displaymode='GBTREFER']", "li.current a[displaymode='GBTREFER']"], timeout_ms=500)
            if not ref_mode:
                self._click_link_by_text("GB/T 7714-2015 格式引文", page=export_page)
            _time.sleep(0.3)

            with export_page.expect_download(timeout=60000) as dl:
                if not click_first_available(export_page, ["#litotxt"], timeout_ms=500):
                    raise ValidationError("未找到TXT导出按钮")
            tmp_file2 = dl.value
            tmp_txt = self._tmp_dir / f"batch{batch_index:03d}.txt"
            tmp_file2.save_as(str(tmp_txt))
            self._process_reference(tmp_txt, txt_path, excel_path)
        finally:
            try:
                export_page.close()
            except Exception:
                pass

        return excel_path, txt_path

    def _open_custom_export_page(self) -> Optional[Page]:
        existing = list(self.page.context.pages)
        if not click_first_available(self.page, ["a[exporttype='selfDefine']"], timeout_ms=500):
            raise ValidationError("未找到自定义导出入口")
        deadline = _time.time() + 90
        while _time.time() < deadline:
            if self._is_personal_login_visible():
                return None
            for p in self.page.context.pages:
                if p not in existing:
                    return p
            _time.sleep(0.3)
        if self._is_personal_login_visible():
            return None
        return None

    def _is_personal_login_visible(self) -> bool:
        for sel in [".ecp-account-login .ecp_userName", ".ecp-passwordBox .ecp_passWord", "button.ECP_UserLOgin"]:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return True
            except Exception:
                continue
        return False

    def _login_personal_account(self) -> None:
        from app.config import get_settings
        settings = get_settings()
        username = settings.cnki_username
        password = settings.cnki_password
        if not username or not password:
            raise RuntimeError("个人登录弹框，但未配置CNKI_USERNAME/CNKI_PASSWORD")

        inp_user = self._first_visible_locator(["input.ecp_userName"])
        inp_pass = self._first_visible_locator(["input.ecp_passWord"])
        if inp_user:
            inp_user.fill(username)
        if inp_pass:
            inp_pass.fill(password)
        agree = self._first_visible_locator(["#agreement"])
        if agree and not agree.is_checked():
            agree.check(force=True)
        if not click_first_available(self.page, ["button.ECP_UserLOgin"], timeout_ms=500):
            raise ValidationError("未找到个人登录按钮")
        deadline = _time.time() + 30
        while _time.time() < deadline:
            if not self._is_personal_login_visible():
                return
            self._ensure_captcha_cleared()
            _time.sleep(0.5)
        raise ValidationError("个人登录未完成，请检查账号密码")

    def _process_exported_excel(self, src: Path, dst: Path) -> None:
        df = self._sanitize_excel(src)
        df.to_excel(dst, index=False, engine="openpyxl")

    def _sanitize_excel(self, path: Path) -> pd.DataFrame:
        try:
            df = pd.read_excel(path, engine="openpyxl", header=None).fillna("")
        except Exception:
            html_content = path.read_text(encoding="utf-8")
            tables = pd.read_html(StringIO(html_content), flavor="lxml", header=None)
            df = tables[0].fillna("") if tables else pd.DataFrame()
        headers: list = []
        all_cols: list = []
        rows: list = []
        for tup in df.itertuples(index=False, name=None):
            vals = [str(v).strip() if pd.notna(v) else "" for v in tup]
            while vals and not vals[-1]:
                vals.pop()
            if not any(vals):
                continue
            if any(v.startswith(("SrcDatabase-", "Title-", "Author-")) for v in vals if v):
                headers = vals
                for h in headers:
                    if h and h not in all_cols:
                        all_cols.append(h)
                continue
            if not headers:
                continue
            rows.append(vals)
        if not all_cols:
            return pd.DataFrame()
        max_len = max(len(r) for r in rows) if rows else len(all_cols)
        result = pd.DataFrame(rows, columns=all_cols[:max_len]).fillna("")
        for c in all_cols:
            if c not in result.columns:
                result[c] = ""
        return result

    def _process_reference(self, src: Path, dst: Path, excel_path: Path) -> None:
        refs = self._parse_references(src)
        if refs:
            df = pd.read_excel(excel_path, engine="openpyxl").fillna("")
            if len(df) == len(refs):
                df["参考格式"] = refs
                df.to_excel(excel_path, index=False, engine="openpyxl")
        shutil.copy2(src, dst)

    def _parse_references(self, path: Path) -> list[str]:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            return []
        matches = list(re.finditer(r"(?m)^\[(\d+)\]", content))
        if not matches:
            return []
        refs = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            refs.append(re.sub(r"\s*\n\s*", " ", content[start:end].strip()))
        return refs

    # ═══════════════════════════════════════════════════════════
    #  ORCHESTRATION — full search flow
    # ═══════════════════════════════════════════════════════════

    def _parse_summary(self) -> dict:
        try:
            text = self.page.locator(".pagerTitleCell").first.inner_text()
            m = re.search(r"([\d,]+)", text)
            total = int(m.group(1).replace(",", "")) if m else 0
        except Exception:
            total = 0
        return {"total": total}

    def _slug(self, text: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff\-]", "_", text)

    def execute_search(self, params: dict) -> dict:
        group_a = params.get("query_group_a", [])
        group_b = params.get("query_group_b", [])
        au_group = params.get("au_group", [])
        fu_group = params.get("fu_group", [])
        query_label = f"{group_a[0] if group_a else ''}_{group_b[0] if group_b else ''}"
        logger.info(f"[CNKI-PROFESSIONAL] Starting search: A={group_a} B={group_b} AU={au_group} FU={fu_group}")

        self.browser.save_session()
        self.browser.goto(CnkiBrowser.ADVANCED_SEARCH_URL)
        _time.sleep(random.uniform(2, 3))
        self._ensure_captcha_cleared()

        if not self._is_search_page():
            raise NavigationStateError("打开检索页面失败")

        self._fill_professional_search_form(
            group_a=group_a,
            group_b=group_b,
            date_from=str(params.get("year_from")) if params.get("year_from") else None,
            date_to=str(params.get("year_to")) if params.get("year_to") else None,
            date_range=params.get("date_range"),
            core_only=params.get("core_only", False),
            synonym_extend=params.get("synonym_extend", False),
            include_no_fulltext=params.get("include_no_fulltext", False),
            au_group=au_group,
            fu_group=fu_group,
        )
        self._submit_search()
        self._wait_for_results_ready()

        summary = self._parse_summary()
        total = summary["total"]
        logger.info(f"[CNKI-PROFESSIONAL] Total results: {total}")
        if total == 0:
            raise NoResultsError("检索结果为空")

        max_export = params.get("max_export", 50)
        export_limit = min(total, max_export)
        batch_count = (export_limit + EXPORT_BATCH_SIZE - 1) // EXPORT_BATCH_SIZE
        logger.info(f"[CNKI-PROFESSIONAL] Export {export_limit} records in {batch_count} batch(es)")

        self._set_results_per_page(export_limit, total)
        batch_files = []
        batch_remaining = export_limit

        for batch_idx in range(1, batch_count + 1):
            batch_size = min(EXPORT_BATCH_SIZE, batch_remaining)
            self._select_batch(batch_size)
            excel_path, txt_path = self._export_batch(query_label, batch_idx)
            batch_remaining -= EXPORT_BATCH_SIZE
            batch_files.append({"excel": str(excel_path), "txt": str(txt_path)})
            logger.info(f"[CNKI-PROFESSIONAL] Batch {batch_idx}/{batch_count}: {excel_path.name}")
            self._clear_selected_results()
            if batch_idx < batch_count:
                self._goto_next_results_page()
            self.browser.save_session()

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = self._slug(query_label)[:40]
        merged_path = self.output_dir / f"{timestamp}-{slug}-merged.xlsx"
        frames = [pd.read_excel(Path(bf["excel"]), engine="openpyxl").fillna("")
                  for bf in batch_files if Path(bf["excel"]).exists()]
        if frames:
            pd.concat(frames, ignore_index=True).to_excel(merged_path, index=False, engine="openpyxl")

        logger.info(f"[CNKI-PROFESSIONAL] Complete: {merged_path}")
        self.browser.save_session()
        return {
            "final_file": str(merged_path),
            "total": total,
            "exported": export_limit,
            "batches": batch_files,
        }
