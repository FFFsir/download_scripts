## Context

Dynamic World 下载器的 WebUI 基于 NiceGUI 构建，当前"已下载文件"卡片通过 `list_tif_files()` 扫描指定目录并展示 `.tif/.zip/.npy` 文件列表，点击文件弹出预览对话框显示渲染图片和文本统计。两个缺陷：(1) 不支持浏览子目录，(2) 预览缺少直观的比色卡。

## Goals / Non-Goals

**Goals:**
- `list_tif_files()` 同时返回子目录列表，支持目录导航
- 文件列表中子目录以可点击按钮展示，点击进入子目录
- "上一层"按钮回退到父目录
- 预览对话框增加比色卡 HTML 表格（色块 + 类别名 + 像素统计）
- 生成数据集调研报告

**Non-Goals:**
- 不修改 CLI 下载逻辑
- 不新增下载功能或参数
- 不限制浏览路径的根目录范围

## Decisions

### 1. `list_tif_files()` 扩展为 `list_dir_contents()`

**选择**: 新增函数 `list_dir_contents(dir)` 返回 `{"dirs": [...], "files": [...]}`，同时保留 `list_tif_files()` 向后兼容。

`dirs` 每项包含 `name`（目录名）、`path`（完整路径）；`files` 结构不变。

**替代方案**: 直接在 `list_tif_files()` 返回值中增加 `dirs` 字段。未采用，因为改动现有函数签名可能影响 CLI 端使用（虽然当前 CLI 未调用此函数，但未来可能有风险）。

### 2. 目录导航状态管理

**选择**: 在 `refresh_file_list()` 闭包中维护 `current_browse_path` 变量（初始值为 `browse_dir_input.value`），目录点击和"上一层"操作均修改此变量并刷新列表。

不使用 NiceGUI 全局 state 或 URL 参数，因为导航状态是临时的 UI 交互状态，不需要跨页面持久化。

### 3. 比色卡渲染方式

**选择**: 使用 NiceGUI `ui.html()` 注入内联 HTML `<table>`，每行包含一个 `<div>` 色块 + 类别名 + 像素数 + 占比。

色块使用 `DW_COLORS` 中的 RGB 值，通过 `rgb(r,g,b)` CSS 设置 `background-color`。

**替代方案**: 使用 NiceGUI 原生 `ui.row()` + `ui.element()` 逐行构建。未采用，因为 9 行需要大量 Python 循环代码，HTML 表格更简洁且排版一致。

### 4. 调研报告格式

**选择**: 独立 Markdown 文件 `docs/research/dynamic-world-v1-bands.md`，包含数据集概述、全部波段列表（含名称、类型、说明）、比色卡颜色映射表、以及"无直接图像数据"的明确结论。

## Risks / Trade-offs

- [NiceGUI 动态刷新] `files_container.clear()` 后重新构建组件，频繁导航可能产生轻微闪烁 → 使用 `ui.refreshable` 或接受当前行为（目录导航频率低）
- [比色卡 HTML 注入] `ui.html()` 内联样式不继承 NiceGUI 主题 → 使用独立 CSS 确保颜色正确渲染，不受全局样式影响
