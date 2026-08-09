## Why

为所内研究人员提供便捷的 Satellite Embedding V1（AlphaEarth Foundations v2.1）数据下载工具。该数据集是 Google DeepMind 出品的 64 维嵌入向量产品，与已支持的 Dynamic World 分类数据有本质差异（年度合成、多波段整体使用、UTM 投影）。需要独立的下载工具覆盖该数据集的 CLI 批量下载和 WebUI 可视化操作需求。

## What Changes

- 新增 `SatelliteEmbedding/` 模块，包含 core.py（核心逻辑）、cli.py（CLI 入口）、web.py（NiceGUI WebUI）
- 实现 GEE `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` 数据集的影像筛选（calendarRange 年份过滤）、合成（first/mean/median）、下载功能
- 提供 CLI 命令行工具，支持单点和批量坐标下载，参数风格与 DW 保持一致
- 提供 NiceGUI WebUI 页面，支持年份选择、波段子集自定义、CSV 上传、进度反馈
- 均值聚合后自动 L2 重归一化处理
- 完善错误处理：认证失败提示、坐标验证、网络重试、大区域数据量警告

## Capabilities

### New Capabilities
- `gee-se-cli-download`: GEE Satellite Embedding V1 数据 CLI 下载，支持多年份跨年合成与 64 波段选择
- `gee-se-webui`: NiceGUI WebUI，提供可视化参数配置、CSV 上传、实时下载进度反馈

### Modified Capabilities
<!-- 无已有 capability 需修改 -->

## Impact

- 新增文件: `SatelliteEmbedding/core.py`, `SatelliteEmbedding/cli.py`, `SatelliteEmbedding/web.py`, `SatelliteEmbedding/templates/index.html`
- 新增依赖: `earthengine-api`, `requests`, `nicegui`（与 DW 共用 `.venv`）
- 下载目标路径: `D:\Project\光机所项目\download\SatelliteEmbedding`（可通过参数覆盖）
- 不影响 Dynamic World 现有代码
