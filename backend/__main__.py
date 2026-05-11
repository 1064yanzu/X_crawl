"""
桌面端/PyInstaller 后端入口。

环境变量：
    XCRAWL_PORT     —— 后端监听端口（必填，由 Electron 注入）
    XCRAWL_HOST     —— 监听地址（默认 127.0.0.1）
    XCRAWL_DATA_DIR —— 数据根目录（桌面端模式下由 Electron 注入到 userData 路径）
"""
import os
import sys
from pathlib import Path


def _ensure_backend_on_path() -> None:
    """PyInstaller --onedir/-onefile 模式下，把 backend 目录加进 sys.path
    以保证 `from api ...` / `from crawler ...` 这类绝对导入可用。"""
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))


def main() -> None:
    _ensure_backend_on_path()

    import uvicorn
    from api.main import app

    host = os.environ.get("XCRAWL_HOST", "127.0.0.1")
    port = int(os.environ.get("XCRAWL_PORT", "8000"))

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
