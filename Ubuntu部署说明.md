# Ubuntu 部署说明

## 验证环境

| 项目 | 版本 |
|------|------|
| OS | Ubuntu 24.04 |
| Python | 3.12.3 |
| Playwright | 1.58.0 |
| Camoufox | 0.4.11 |
| Firefox | 146.0.1（Playwright 内置） |

## 安装步骤

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装 Playwright Firefox（Camoufox 底层使用 Firefox，非 Chromium）
playwright install firefox

# 3. 验证浏览器可启动
python -c "from camoufox.sync_api import NewBrowser; print('camoufox OK')"

# 4. 初始化数据库
mkdir -p data
python -c "
import asyncio
from app.database import init_db, engine
from app.dependencies import hash_password
from sqlalchemy import text
async def s():
    await init_db()
    async with engine.begin() as c:
        await c.execute(text(\"INSERT OR IGNORE INTO users (username, password_hash, email, role, is_active) VALUES ('admin', :pw, 'admin@example.com', 'admin', 1)\"), {'pw': hash_password('admin123')})
    print('DB ready')
    await engine.dispose()
asyncio.run(s())
"

# 5. 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
python worker_runner.py cnki 1
python worker_runner.py llm 5
python worker_runner.py download 1
python worker_runner.py export 2

# 6. （可选）前端
npm install && npm run dev
```

## 与现有部署手册的关键差异

> 对照 `docs/deploy/部署运维手册.md`，Ubuntu 实测需要调整以下事项：

| 手册中原写法 | Ubuntu 实测需改为 | 原因 |
|---|---|---|
| `playwright install chromium` | `playwright install firefox` | Camoufox `NewBrowser` / `Camoufox` 均基于 Firefox |
| `playwright install chromium --with-deps` | `playwright install firefox --with-deps`（首次安装系统库） | 同上 |

## CNKI 搜索测试结果

2026-05-18 在 headless 模式下对 `app/services/cnki/` 全套功能进行验证，**7/7 全部通过**：

| 参数 | 检索结果数 | 导出 | 耗时 |
|---|---|---|---|
| 基础搜索「新青年」 | 9,742 | 10 | 17s |
| 核心期刊 `core_only` | 2,812 | 10 | 16s |
| 年份范围 2024–2025 | 1,197 | 10 | 18s |
| 时间范围 `year` | 537 | 10 | 19s |
| 同义词扩展 `synonym_extend` | 9,742 | 10 | 17s |
| 起始年份 2024 | 1,296 | 10 | 16s |
| 截止年份 2023 | 8,440 | 10 | 17s |

覆盖模块：`browser.py`（Camoufox 启动 / Cookie 持久化 / headless）、`interactor.py`（高级检索表单 / 翻页 / 勾选 / Excel+TXT 导出 / 合并）。

## 常见问题

- **`ModuleNotFoundError: No module named 'app'`** → 在项目根目录执行，或设置 `PYTHONPATH=/path/to/sdi-cnki`
- **`playwright install firefox` 后仍报浏览器缺失** → 执行 `playwright install firefox --with-deps` 安装系统共享库
- **Camoufox 初始化 TypeError** → `browser.py` 已内置 fallback 到标准 Playwright Firefox，无需干预
