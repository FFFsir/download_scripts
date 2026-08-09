## Context

当前所内研究人员通过 GEE Code Editor 手动编写代码下载 Dynamic World V1 数据，效率低、门槛高。本项目为 `download_scripts` 仓库的新增子模块，位于 `DynamicWorld/` 目录下，使用项目已有 `.venv` 虚拟环境和 `uv` 包管理。

Dynamic World V1 是 10m 分辨率的近实时全球土地利用分类产品（`GOOGLE/DYNAMICWORLD/V1`），通过 GEE Python API 的 `getDownloadURL()` 方法可直接下载为 GeoTIFF。

## Goals / Non-Goals

**Goals:**
- 提供 CLI 命令行工具，支持单点和批量坐标的数据下载
- 提供 FastAPI WebUI，通过可视化页面降低使用门槛
- 支持 CSV 文件上传和坐标文本粘贴两种输入方式
- SSE 实时推送下载进度到 WebUI
- 完善的错误处理和日志记录

**Non-Goals:**
- 不做 GEE 之外的数据源
- 不做数据后处理、分析或可视化
- 不替代 GEE Code Editor
- 不做多用户权限系统
- 不做下载历史持久化存储

## Decisions

### 1. 模块分离: core.py + cli.py + web.py

**选择**: 三层分离结构

```
DynamicWorld/
├── core.py          # GEE 认证、坐标解析、ROI 构造、影像合成、下载执行
├── cli.py           # argparse CLI 入口，调用 core 模块
├── web.py           # FastAPI + SSE + Jinja2 模板，调用 core 模块
└── templates/
    └── index.html   # WebUI 页面
```

**理由**: CLI 和 WebUI 共享同一套核心逻辑，避免代码重复。分离后各模块职责清晰，便于测试和维护。

**备选方案**: 单文件合体 — 结构简单但文件过长（~500+ 行），难以维护。

### 2. FastAPI SSE 进度推送

**选择**: 使用 Server-Sent Events 逐点推送下载状态

**理由**: SSE 比 WebSocket 更轻量，浏览器原生支持，不需要额外依赖。每个坐标点的下载结果作为一个事件推送到前端，前端实时更新进度条。

**备选方案**: 简单 POST + 等待 — 实现最简单，但批量下载多个点时用户体验差，等待数分钟无反馈。

### 3. Web 框架: FastAPI + Jinja2

**选择**: FastAPI 作为 Web 框架，Jinja2 模板渲染 HTML

**理由**: FastAPI 原生支持 SSE（StreamingResponse），异步性能好。Jinja2 是 FastAPI 默认推荐的模板引擎，`uvicorn` 作为 ASGI 服务器成熟稳定。

**备选方案**: Flask — 同样成熟但 SSE 支持需额外处理，且非异步原生。

### 4. 下载方式: getDownloadURL + requests

**选择**: 使用 `image.getDownloadURL()` 获取临时下载链接，`requests` 下载文件

**理由**: `getDownloadURL()` 是 GEE 推荐的轻量下载方式，直接返回可下载 URL，无需 Google Drive 中转。对于小区域（<32MB, <10000px）数据下载最高效。

**备选方案**: `Export.image.toDrive()` — 适合超大区域，但需要 Google Drive 中转，用户需额外操作下载。

### 5. GEE 认证: ee.Authenticate() + ee.Initialize(project=...)

**选择**: 首次运行通过 `ee.Authenticate()` 触发浏览器 OAuth，后续使用持久化凭据

**理由**: GEE 标准认证流程。`--project` 参数必填确保用户明确指定 GCP 项目。

## Risks / Trade-offs

- [GEE 认证在无头服务器上无法弹出浏览器] → CLI 模式下引导用户在有 GUI 环境先运行一次认证；WebUI 模式下检测凭据状态，未认证时页面显示提示
- [getDownloadURL 单次限制 32MB/10000px] → 检测区域大小，超出限制时警告并建议使用 GEE Code Editor 的 Export 功能
- [网络不稳定导致下载中断] → 自动重试 3 次指数退避（1s/2s/4s），超时 300s
- [批量下载大量坐标点耗时长] → SSE 逐点推送进度，用户可感知进度；不阻塞整个流程
