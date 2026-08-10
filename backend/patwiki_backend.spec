# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。
打包命令：pyinstaller patwiki_backend.spec
产物：dist/patwiki-backend/patwiki-backend.exe (Windows)
"""
import sys
from pathlib import Path

block_cipher = None

# 后端代码根目录（spec 文件所在目录 = backend/）
backend_root = Path(SPECPATH).resolve()

a = Analysis(
    [str(backend_root / "run.py")],
    pathex=[str(backend_root)],
    binaries=[],
    datas=[
        # 打包 .env.example 作为默认配置模板
        (str(backend_root / ".env.example"), "."),
    ],
    hiddenimports=[
        # FastAPI / Pydantic 常见遗漏
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # SQLAlchemy 方言
        "sqlalchemy.dialects.sqlite",
        # pandas / openpyxl
        "pandas",
        "openpyxl",
        "xlrd",
        # 本项目模块 - API
        "app",
        "app.api",
        "app.api.api",
        "app.api.patents",
        "app.api.imports",
        "app.api.ai",
        "app.api.meta",
        "app.api.deps",
        "app.api.fields",
        "app.api.settings",
        "app.api.databases",
        "app.api.views",  # P0-13 新增
        "app.api.formula",  # M1 公式字段
        "app.api.export",  # M1 数据导出
        "app.api.form",  # M4 表单视图公开提交
        "app.api.automation",  # M5 自动化规则
        "app.api.attachments",  # M5 附件字段
        "app.api.dashboards",  # M5 可配置仪表盘
        # 本项目模块 - models（P0-8 拆分为子模块）
        "app.models",
        "app.models.enums",
        "app.models.association",
        "app.models.organization",
        "app.models.project",
        "app.models.tag",
        "app.models.field",
        "app.models.database",
        "app.models.patent",
        "app.models.ai",
        "app.models.importing",
        "app.models.view",  # P0-13 新增
        # 本项目模块 - schemas/services
        "app.schemas.schemas",
        "app.services.import_service",
        "app.services.patent_service",
        "app.services.field_registry",
        "app.services.merge_service",
        "app.services.relation_service",
        "app.services.database_service",
        "app.services.view_service",  # P0-13 新增
        "app.services.formula_engine",  # M1 公式字段
        "app.services.formula_service",  # M1 公式字段
        "app.services.export_service",  # M1 数据导出
        "app.services.form_service",  # M4 表单视图
        "app.services.automation_service",  # M5 自动化执行引擎
        "app.services.attachment_service",  # M5 附件服务
        "app.services.dashboard_service",  # M5 仪表盘聚合
        "app.models.formula",  # M1 公式依赖
        "app.models.form",  # M4 表单分享链接
        "app.models.automation",  # M5 自动化规则与日志
        "app.models.attachment",  # M5 附件元数据
        "app.models.dashboard",  # M5 仪表盘
        "app.ai.fields.engine",
        "init_data",
        # openai SDK 及其依赖
        "openai",
        "httpx",
        "httpcore",
        "anyio",
        "distro",
        "tiktoken_ext.openai_public",
        "tiktoken_ext",
        "tiktoken",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不必要的模块以减小体积
        "tkinter",
        "matplotlib",
        "pytest",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="patwiki-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 保留控制台便于调试；Tauri 会隐藏
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="patwiki-backend",
)
