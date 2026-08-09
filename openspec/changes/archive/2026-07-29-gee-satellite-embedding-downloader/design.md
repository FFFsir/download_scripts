## Context

当前所内研究人员已通过 Dynamic World 下载工具（`DynamicWorld/`）获取土地利用分类数据。现需扩展支持 Satellite Embedding V1（`GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`）——Google DeepMind 出品的 64 维嵌入向量数据集，年度合成（2017–2024），10m 分辨率，值域 [-1, 1] 单位向量。

该数据集与 DW 有本质差异：64 波段必须整体使用、年度合成而非逐景、原始投影为 local UTM 而非 WGS84、均值聚合后需 L2 重归一化。本项目在 `SatelliteEmbedding/` 目录下新建独立模块，复用 DW 的 core/cli/web 三层架构和 NiceGUI 交互模式。

## Goals / Non-Goals

**Goals:**
- 提供 CLI 命令行工具，支持单点和批量坐标的 Satellite Embedding 数据下载
- 提供 NiceGUI WebUI，通过可视化页面降低使用门槛
- 支持多年份跨年合成（first/mean/median）与 64 波段子集选择
- 均值聚合后自动 L2 重归一化，确保输出仍为单位向量
- 完善的错误处理：认证失败、坐标验证、网络重试、数据量警告

**Non-Goals:**
- 不做嵌入向量后处理、降维、聚类分析
- 不做 GCS / AWS COG 直接下载（仅通过 GEE getDownloadURL）
- 不修改 Dynamic World 现有代码
- 大区域不强制 toDrive 自动切换（仅警告）
- 不做 GeoTIFF 预览渲染（64 维向量无可视化语义）

## Decisions

### 1. 模块结构: 三层分离 core.py + cli.py + web.py

**选择**: 复用 DW 的三层分离结构

```
SatelliteEmbedding/
├── core.py          # GEE 认证、坐标解析、ROI 构造、影像筛选（calendarRange）、合成、L2 重归一化、下载执行
├── cli.py           # argparse CLI 入口，调用 core 模块
├── web.py           # NiceGUI + run.io_bound，调用 core 模块
└── templates/
    └── index.html   # WebUI 页面
```

**理由**: CLI 和 WebUI 共享同一套核心逻辑，与 DW 保持一致的代码组织方式，降低维护者认知负担。

**备选方案**: 单文件合体 — 结构简单但 ~500+ 行难以维护，且与仓库现有模式不一致。

### 2. Web 框架: NiceGUI

**选择**: 使用 NiceGUI（而非裸 FastAPI + Jinja2）

**理由**: DW 实际使用 NiceGUI 构建 WebUI，提供 `ui.notify()` 进度通知、`ui.linear_progress()` 进度条、`run.io_bound()` 异步 IO 包装、`app.storage.user` 表单记忆等便利功能。SE 与 DW 保持一致可最大化代码复用和理解成本。

**备选方案**: 裸 FastAPI + Jinja2 + SSE — 更轻量但需手工实现进度推送和表单状态管理，且与 DW 实际实现不一致。

### 3. 年份选择: calendarRange 过滤 + filterBounds

**选择**: 使用 `ee.Filter.calendarRange(year, year, 'year')` 进行年份过滤

**理由**: SE 数据集为年度合成产品，每景的 `system:time_start` 对应该年份。calendarRange 是 GEE 标准的年份过滤方式，比字符串日期匹配更准确。

**备选方案**: 使用 `filterDate(f"{year}-01-01", f"{year}-12-31")` — 效果等价但语义不如 calendarRange 明确，且跨年份场景不便。

### 4. 均值聚合后 L2 重归一化

**选择**: 跨年 mean 合成后，逐像素计算 L2 范数并除以范数，恢复单位向量

**理由**: 均值聚合会破坏单位向量性质（多个单位向量的均值通常不是单位向量）。L2 重归一化是数学上正确的恢复方式：`v_normalized = v / ||v||₂`。

**备选方案**: 不重归一化 — 下游用户需自行处理，增加使用门槛，违背"开箱即用"原则。

### 5. 波段命名与输出格式

**选择**: 64 波段默认写入单个 GeoTIFF，波段名保持 GEE 原始命名（A00–A63），`filePerBand=False`

**理由**: 嵌入向量各维度不可独立使用，分开存储无实际意义且增加管理负担。单文件输出与下游 ML 工作流（如 `rasterio.open()` 一次性读取全部波段）兼容。

**备选方案**: 每波段单独文件 — 64 个文件管理复杂，无实际收益。

## Risks / Trade-offs

- [跨年合成时不同年份 UTM 投影不一致] → GEE `ImageCollection.mean()` 内部自动重投影到首景投影。用户指定 `--crs EPSG:4326` 输出时会再次重投影。10m 分辨率下精度损失可忽略，但需在下载日志中记录原始 UTM_ZONE 信息。
- [getDownloadURL 单次限制 32MB] → 默认 buffer=640m 下约 3MB 安全；buffer=3000m 时约 72MB 可能超限，需检测并警告。
- [64 波段 GeoTIFF 文件体积较大] → 默认 buffer=640m 约 3MB/点，可接受；批量下载多点时通过 SSE 逐点推送进度保证体验。
- [GEE 认证在无头服务器上无法弹出浏览器] → CLI 引导用户在有 GUI 环境先运行 `earthengine authenticate`；WebUI 检测凭据状态，未认证时页面显示提示并阻止提交。
- [网络不稳定导致下载中断] → 复用 DW 的指数退避重试机制（1s/2s/4s，最多 3 次，超时 300s）。
