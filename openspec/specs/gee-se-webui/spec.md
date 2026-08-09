# gee-se-webui Specification

## Purpose
TBD - created by archiving change gee-satellite-embedding-downloader. Update Purpose after archive.
## Requirements
### Requirement: WebUI 参数表单
系统 SHALL 使用 NiceGUI 提供纯 Python WebUI 页面，包含所有下载参数对应的 NiceGUI 控件：
- 坐标输入：`ui.textarea()` 粘贴坐标和 `ui.upload()` CSV 上传
- 年份选择：`ui.select()` 下拉框（2017-2024），支持单年或多年多选
- 波段选择：`ui.select()` 下拉框（all / 自定义逗号列表输入）
- 合成方式：`ui.select()` 下拉框（first / mean / median）
- 数值参数：`ui.number()` 输入框（buffer, scale）
- 输出格式：`ui.select()` 下拉框（GEO_TIFF / ZIPPED_GEO_TIFF / NPY）
- CRS：`ui.input()` 文本框
- 必填项：`ui.input()` GCP 项目 ID
- 提交按钮：`ui.button()` 开始下载

#### Scenario: 表单填写并提交
- **WHEN** 用户在 WebUI 填写所有参数并点击"开始下载"
- **THEN** 系统开始执行下载，通过 `ui.linear_progress()` 和 `ui.notify()` 推送进度

#### Scenario: CSV 文件上传
- **WHEN** 用户通过 `ui.upload()` 上传 CSV 文件作为坐标输入
- **THEN** 系统解析 CSV 内容，将坐标填入文本框并显示坐标点数量和列表预览

### Requirement: 实时进度反馈
系统 SHALL 通过 NiceGUI `ui.linear_progress()` 进度条和 `ui.notify()` 通知逐点反馈下载状态。
每个点下载完成后即时更新进度条百分比和通知消息。

#### Scenario: 批量下载进度显示
- **WHEN** 用户提交 3 个坐标点的批量下载
- **THEN** 前端实时显示进度条更新和每个点的完成通知，完成后显示汇总

#### Scenario: 下载错误反馈
- **WHEN** 某个坐标点下载失败
- **THEN** `ui.notify()` 显示该点的错误信息（type='negative'），继续处理后续点

### Requirement: WebUI 独立启动
系统 SHALL 支持通过 `python -m SatelliteEmbedding.web` 独立启动 NiceGUI 服务。

#### Scenario: 启动 Web 服务
- **WHEN** 用户执行 `python -m SatelliteEmbedding.web`
- **THEN** NiceGUI 启动服务，默认监听 `http://127.0.0.1:8000`

### Requirement: GEE 认证状态检测
系统 SHALL 在 WebUI 页面加载时通过 `try ee.Initialize()` 检测 GEE 认证状态。

#### Scenario: 未认证提示
- **WHEN** 用户打开 WebUI 但 GEE 未认证
- **THEN** 页面显示警告 banner，引导用户先运行 `earthengine authenticate` 完成认证

#### Scenario: 已认证正常使用
- **WHEN** 用户打开 WebUI 且 GEE 已认证
- **THEN** 页面正常显示参数表单，可提交下载任务

### Requirement: 表单记忆
系统 SHALL 通过 `app.storage.user` 在页面刷新后恢复用户上次填写的参数值。

#### Scenario: 刷新后参数恢复
- **WHEN** 用户在下载后刷新页面
- **THEN** 之前填写的 project ID、坐标、参数选择自动恢复到对应控件

### Requirement: 不做预览渲染
系统 SHALL NOT 提供 GeoTIFF 预览渲染功能。64 维嵌入向量无可视化语义，DW 的 `tif_to_preview_png` 和统计信息弹窗不适用于 SE 数据。

#### Scenario: 文件列表无预览按钮
- **WHEN** 用户在 WebUI 浏览已下载文件
- **THEN** 文件列表仅显示文件名、大小、修改时间，不显示预览按钮

