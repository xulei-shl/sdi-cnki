import ast, os
base = r"F:\Github\sdi-cnki\backend\app"
files = [
    "services/pdf_downloader_src/__init__.py",
    "services/pdf_downloader_src/keyword_processor.py",
    "services/pdf_downloader_src/zhesheke.py",
    "services/pdf_downloader_src/wanfang.py",
    "services/pdf_downloader_src/cnki.py",
    "services/keyword_normalizer.py",
    "services/pdf_downloader.py",
    "worker/download_worker.py",
]
ok = True
for f in files:
    p = os.path.join(base, f)
    with open(p, "r", encoding="utf-8") as fh:
        ast.parse(fh.read())
    print(f"  OK  {p}")
print("All OK!")
