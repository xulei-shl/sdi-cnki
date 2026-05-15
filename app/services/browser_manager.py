from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger("browser_manager")

settings = get_settings()


class CnkiBrowserManager:
    ADVANCED_SEARCH_URL = "https://kns.cnki.net/kns8s/AdvSearch?classid=YSTT4HG0"
    HOME_URL = "https://www.cnki.net/"

    def __init__(self, cookies_dir: str | None = None):
        self._cookies_dir = Path(cookies_dir or settings.cookies_dir)
        self._cookies_dir.mkdir(parents=True, exist_ok=True)
        self._cookies_file = self._cookies_dir / "cnki_cookies.json"
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def start(self, headless: bool = True) -> None:
        from camoufox.async_api import NewBrowser
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await NewBrowser(
            self._playwright,
            headless=headless,
            geoip=False,
        ).__aenter__()
        self._context = await self._browser.new_context(
            locale="zh-CN",
            accept_downloads=True,
        )
        self._context.set_default_timeout(30000)
        self._page = await self._context.new_page()
        await self._load_cookies()

    async def close(self) -> None:
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                await self._browser.__aexit__(None, None, None)
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    @property
    def page(self):
        return self._page

    async def navigate(self, url: str) -> None:
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.goto(url, wait_until="domcontentloaded", timeout=60000)

    async def ensure_login(self) -> bool:
        await self.navigate(self.HOME_URL)
        if await self._is_logged_in():
            return True
        username = settings.cnki_username
        password = settings.cnki_password
        if not username or not password:
            logger.error("CNKI 未登录且未配置账号密码")
            return False
        try:
            await self._do_login(username, password)
            await self._save_cookies()
            return await self._is_logged_in()
        except Exception as e:
            logger.error(f"CNKI 自动登录失败: {e}")
            return False

    async def _is_logged_in(self) -> bool:
        if not self._page:
            return False
        try:
            text = await self._page.inner_text("body")
            return "登录" not in text[:500] or "个人登录" not in text[:500]
        except Exception:
            return False

    async def _do_login(self, username: str, password: str) -> None:
        login_btn = self._page.locator("a[href*='Login']").first
        if await login_btn.count() > 0:
            await login_btn.click()
            await self._page.wait_for_timeout(2000)
        username_input = self._page.locator("input[name='username'], input[placeholder*='用户名']").first
        if await username_input.count() > 0:
            await username_input.fill(username)
        pwd_input = self._page.locator("input[type='password']").first
        if await pwd_input.count() > 0:
            await pwd_input.fill(password)
        submit = self._page.locator("button[type='submit'], a[class*='login-btn']").first
        if await submit.count() > 0:
            await submit.click()
            await self._page.wait_for_timeout(5000)

    async def navigate_advanced_search(self) -> None:
        await self.navigate(self.ADVANCED_SEARCH_URL)
        await self._page.wait_for_timeout(2000)

    async def fill_advanced_form(self, params: dict) -> None:
        query = params.get("query", "")
        year_from = params.get("year_from")
        year_to = params.get("year_to")
        date_range = params.get("date_range")
        core_only = params.get("core_only", False)
        synonym_extend = params.get("synonym_extend", False)
        include_no_fulltext = params.get("include_no_fulltext", False)

        await self._page.evaluate("""
            (opts) => {
                const disableCb = (sel) => { const e = document.querySelector(sel); if(e && e.checked) e.click(); };
                const enableCb = (sel) => { const e = document.querySelector(sel); if(e && !e.checked) e.click(); };
                const setVal = (sel, v) => { const e = document.querySelector(sel); if(e) e.value = v; };
                disableCb("input[data-id='EN'][name='onlyChecked']");
                if (opts.synonym_extend) enableCb("input[data-id='TY'][name='onlyChecked']");
                setVal("#txt_1_value1", opts.query);
                setVal("#txt_1_value2", opts.query);
                if (opts.date_range) {
                    const sel = document.querySelector("select[class*='date']");
                    if (sel) sel.value = opts.date_range;
                } else {
                    if (opts.year_from) setVal("input[placeholder='起始年']", opts.year_from);
                    if (opts.year_to) setVal("input[placeholder='结束年']", opts.year_to);
                }
                if (opts.include_no_fulltext) disableCb("#onlyfulltext");
                if (opts.core_only) {
                    disableCb("input[name='all']");
                    ["input[key='LYBSM'][value='P12']", "input[key='SI'][value='Y']",
                     "input[key='EI'][value='Y']", "input[key='HX'][value='Y']",
                     "input[key='CSI'][value='Y']", "input[key='CSD'][value='Y']",
                     "input[key='AMI'][value='P13']"].forEach(s => enableCb(s));
                }
            }
        """, {
            "query": query,
            "year_from": str(year_from) if year_from else "",
            "year_to": str(year_to) if year_to else "",
            "date_range": date_range or "",
            "synonym_extend": synonym_extend,
            "include_no_fulltext": include_no_fulltext,
            "core_only": core_only,
        })
        search_btn = self._page.locator("input.btn-search, a.btn-search").first
        if await search_btn.count() > 0:
            await search_btn.click()
            await self._page.wait_for_timeout(3000)

    async def export_batch(self, query: str, batch_index: int, output_dir: Path) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_query = re.sub(r"[^\w\-]", "_", query)[:30]
        excel_path = output_dir / f"{timestamp}-{safe_query}-batch{batch_index:03d}-metadata-cleaned.xlsx"
        txt_path = output_dir / f"{timestamp}-{safe_query}-batch{batch_index:03d}-reference.txt"
        tmp_dir = output_dir / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self._page.wait_for_timeout(500)

        select_all = self._page.locator("input.cbItemAll, input[name='selectAll']").first
        if await select_all.count() > 0:
            await select_all.click()
            await self._page.wait_for_timeout(500)

        export_btn = self._page.locator("a.export, button.export, .exportBar a").first
        if await export_btn.count() > 0:
            await export_btn.click()
            await self._page.wait_for_timeout(1000)

        lit_output = self._page.locator("a[href*='LitOutput'], a:has-text('导出文献')").first
        if await lit_output.count() > 0:
            await lit_output.click()
            await self._page.wait_for_timeout(1000)

        custom_btn = self._page.locator("a:has-text('自定义'), a:has-text('自定义格式')").first
        if await custom_btn.count() > 0:
            await custom_btn.click()
            await self._page.wait_for_timeout(1000)

        for col_name in ["Title-题名", "Author-作者", "Organ-单位", "Source-文献来源",
                         "Keyword-关键词", "Summary-摘要", "PubTime-发表时间", "Year-年",
                         "Volume-卷", "Period-期", "PageCount-页码", "CLC-中图分类号",
                         "ISSN-国际标准刊号", "URL-网址", "DOI-DOI", "Fund-基金", "FirstDuty-第一责任人"]:
            cb = self._page.locator(f"input[type='checkbox'][value='{col_name}']").first
            if await cb.count() > 0:
                checked = await cb.is_checked()
                if not checked:
                    await cb.click()

        await self._page.wait_for_timeout(500)

        async with self._page.expect_download() as dl_info:
            dl_btn = self._page.locator("a:has-text('导出'), input[value='导出']").first
            if await dl_btn.count() > 0:
                await dl_btn.click()
            else:
                raise RuntimeError("Cannot find export button")
        download = await dl_info.value
        tmp_xls = tmp_dir / f"batch{batch_index:03d}.xls"
        await download.save_as(str(tmp_xls))
        self._process_exported_file(tmp_xls, excel_path)

        async with self._page.expect_download() as dl_info2:
            ref_btn = self._page.locator("a:has-text('GB/T'), a[href*='Ref']").first
            if await ref_btn.count() > 0:
                await ref_btn.click()
        download2 = await dl_info2.value
        tmp_txt = tmp_dir / f"batch{batch_index:03d}.txt"
        await download2.save_as(str(tmp_txt))
        self._process_reference_file(tmp_txt, txt_path, excel_path)

        close_btn = self._page.locator(".closeLayer, a.close, button.close").first
        if await close_btn.count() > 0:
            await close_btn.click()
            await self._page.wait_for_timeout(500)

        return excel_path, txt_path

    def _process_exported_file(self, src: Path, dst: Path) -> None:
        import openpyxl
        try:
            wb = openpyxl.load_workbook(src)
            wb.save(dst)
            wb.close()
        except Exception:
            import shutil
            shutil.copy2(src, dst)

    def _process_reference_file(self, src: Path, dst: Path, excel_path: Path) -> None:
        refs = self._parse_reference_txt(src)
        if not refs:
            src.rename(dst)
            return
        df = pd.read_excel(excel_path, engine="openpyxl").fillna("")
        if len(df) == len(refs):
            df["参考格式"] = refs
            df.to_excel(excel_path, index=False, engine="openpyxl")
        import shutil
        shutil.copy2(src, dst)

    def _parse_reference_txt(self, txt_path: Path) -> list[str]:
        content = txt_path.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            return []
        matches = list(re.finditer(r"(?m)^\[(\d+)\]", content))
        if not matches:
            return []
        refs = []
        for idx, m in enumerate(matches):
            start = m.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
            item = content[start:end].strip()
            refs.append(re.sub(r"\s*\n\s*", " ", item))
        return refs

    async def _load_cookies(self) -> bool:
        if not self._cookies_file.exists():
            return False
        try:
            cookies = json.loads(self._cookies_file.read_text(encoding="utf-8"))
            if cookies:
                await self._context.add_cookies(cookies)
            return True
        except Exception as e:
            logger.warning(f"Load cookies failed: {e}")
            return False

    async def _save_cookies(self) -> None:
        if not self._context:
            return
        try:
            cookies = await self._context.cookies()
            self._cookies_file.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Save cookies failed: {e}")

    async def check_captcha(self) -> bool:
        try:
            return await self._page.evaluate("""
                () => {
                    const el = document.querySelector('#tcaptcha_transform_dy');
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.top >= 0 && r.width > 0 && r.height > 0;
                }
            """)
        except Exception:
            return False


import re as _re
_re = __import__("re")
import pandas as pd
