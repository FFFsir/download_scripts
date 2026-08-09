## Why

Dynamic World 下载器 WebUI 当前的"已下载文件"浏览功能存在两个易用性缺陷：只能列出单层目录下的文件而无法浏览子文件夹，以及预览 TIF 文件时缺少直观的地物类别比色卡。此外，用户对 Dynamic World V1 数据集除 label/probs 外还可获取哪些数据缺乏清晰了解。本次优化针对这三个痛点进行集中改进。

## What Changes

- **文件夹导航**：在"浏览文件框"中新增目录浏览功能，子目录以文件夹图标展示，点击文件夹名称自动进入对应目录；新增"上一层"按钮支持回退到父目录
- **比色卡图例**：点击 TIF 文件预览时，除渲染图片和文本统计外，新增 HTML 表格形式的比色卡，以色块 + 类别名 + 像素统计的格式展示 9 个地物类别
- **数据集调研报告**：新增 `docs/research/dynamic-world-v1-bands.md`，说明 Dynamic World V1 全部可用波段及是否包含直接图像数据

## Capabilities

### New Capabilities
<!-- 本次不新增独立 capability，所有改动属于现有 WebUI 的增强 -->
_无_

### Modified Capabilities
- `gee-dw-webui`: 为"已下载文件"卡片新增文件夹导航功能；为 TIF 文件预览对话框新增比色卡图例

## Impact

| 层面 | 影响 |
|------|------|
| `DynamicWorld/core.py` | 扩展 `list_tif_files()` 同时返回子目录列表 |
| `DynamicWorld/web.py` | 改造 `refresh_file_list()` 支持目录导航、"上一层"按钮；改造 `show_preview()` 增加比色卡 HTML 表格 |
| 新增文件 | `docs/research/dynamic-world-v1-bands.md` 调研报告 |
| 不涉及 | CLI、GEE 认证、下载核心逻辑 |
