"""PatWiki 后端启动入口（供 PyInstaller 打包使用）。

打包后由 Tauri 作为 sidecar 拉起。
启动后监听环境变量 PATWIKI_PORT 指定的端口（默认 8765）。
"""
import os
import sys
import socket
import time
import threading
from pathlib import Path


def _find_free_port(default: int = 8765) -> int:
    """优先用 default 端口；若被占用则找一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", default))
            return default
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_port_file(port: int):
    """把实际监听端口写到数据目录，便于前端读取。"""
    try:
        from app.config import settings
        port_file = settings.DATA_DIR / "backend.port"
        port_file.write_text(str(port), encoding="utf-8")
    except Exception:
        pass


def _flush_stdout():
    """Windows 下 PyInstaller 的 stdout 可能缓冲。"""
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass


def main():
    _flush_stdout()

    # 打包后需要把 _MEIPASS 加入 sys.path（PyInstaller 临时解压目录）
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and meipass not in sys.path:
            sys.path.insert(0, meipass)

    # 环境变量优先（Tauri 启动 sidecar 时可注入端口）
    preferred_port = int(os.environ.get("PATWIKI_PORT", "8765"))
    port = _find_free_port(preferred_port)

    # 确保数据目录初始化
    from app.database import init_db
    from init_data import init_default_data
    init_db()
    init_default_data()

    _write_port_file(port)
    print(f"[PatWiki] Backend listening on http://127.0.0.1:{port}", flush=True)

    # 直接传入 app 对象，避免 uvicorn 用字符串导入时掩盖真实导入错误
    # （字符串方式遇到任何 ImportError 都只会报 "Could not import module"）
    try:
        from app.main import app as asgi_app
    except Exception as e:
        import traceback
        print(f"[PatWiki] FATAL: failed to import app.main: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    import uvicorn
    uvicorn.run(
        asgi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
