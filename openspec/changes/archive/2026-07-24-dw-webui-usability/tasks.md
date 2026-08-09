## 1. 后端改造

- [x] 1.1 在 `core.py` 中新增 `list_dir_contents(dir)` 函数，返回统一 `list[dict]`（每项含 `type` 字段区分 "dir"/"file"），同时保留 `list_tif_files()` 向后兼容

## 2. 文件夹导航

- [x] 2.1 在 `web.py` 中改造 `refresh_file_list()`：调用新 `list_dir_contents()`，子目录以可点击按钮展示（点击进入子目录），文件展示逻辑保持不变
- [x] 2.2 在 `web.py` 中新增"上一层"按钮：在子目录时显示，点击回退到父目录并刷新列表；根目录时不显示
- [x] 2.3 在 `web.py` 中维护 `current_browse_path` 状态变量，目录切换时同步更新 `browse_dir_input`

## 3. 比色卡图例

- [x] 3.1 在 `web.py` 的 `show_preview()` 对话框中新增比色卡 HTML 表格：使用 `ui.html()` 渲染色块 + 类别名 + 像素数 + 占比，颜色取自 `DW_COLORS`

## 4. 调研报告

- [x] 4.1 创建 `docs/research/dynamic-world-v1-bands.md`：包含数据集概述、全部波段列表、比色卡颜色映射表、以及"无直接图像数据"的明确结论

## 5. 测试

- [x] 5.1 为 `list_dir_contents()` 添加单元测试
- [x] 5.2 端到端验证：启动 WebUI 确认文件夹导航和比色卡功能正常

## 6. TIF 新标签页预览

- [x] 6.1 在 `web.py` 中新增 `/preview-tif` FastAPI 端点，直接返回 PNG 图片响应
- [x] 6.2 改造文件列表中的 TIF 按钮：点击文件名 → `ui.navigate.to(..., new_tab=True)` 新标签页打开预览
- [x] 6.3 新增 📊 按钮保留原有弹窗预览（比色卡 + 统计信息）
