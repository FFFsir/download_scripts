## 1. 环境准备

- [x] 1.1 使用 `uv add` 安装依赖：`earthengine-api`, `requests`, `nicegui`
- [x] 1.2 创建 `SatelliteEmbedding/` 模块目录和 `__init__.py`

## 2. 核心模块 core.py

- [x] 2.1 定义 `CoordPoint`、`DownloadResult` 数据类（复用 DW 结构）
- [x] 2.2 实现 `init_gee(project_id)` — GEE 认证与初始化
- [x] 2.3 实现 `parse_coords(input_str)` — 坐标解析（CSV 文件 / 分号分隔字符串），含验证与跳过逻辑
- [x] 2.4 实现 `create_roi(lon, lat, buffer_m)` — ROI 点缓冲构造
- [x] 2.5 实现 `build_image(roi, year, years, bands, cross_year)` — 影像筛选（calendarRange 年份过滤）与合成（first/mean/median）
- [x] 2.6 实现 `l2_normalize(image)` — mean 合成后 L2 重归一化
- [x] 2.7 实现 `download_image(image, output_dir, name, scale, crs, fmt, region)` — 下载执行（网络重试 3 次指数退避，filePerBand=False）
- [x] 2.8 实现 `download_single_point(point, output_dir, params)` — 单点完整流水线（ROI → 影像构建 → 下载），内部捕获所有异常
- [x] 2.9 实现 `setup_logging(output_dir)` — 日志配置（控制台 + download.log 双写）
- [x] 2.10 实现 `write_error_csv(output_dir, errors)` — 失败清单写入 download_errors.csv
- [x] 2.11 实现 `estimate_data_size(roi, scale)` — 数据量估算，超出 32MB 时 `warnings.warn`

## 3. CLI 模块 cli.py

- [x] 3.1 使用 argparse 实现所有命令行参数（--year / --years 替代 --start-date / --end-date，--cross-year 替代 --composite）
- [x] 3.2 实现 `main()` — 串联：认证 → 解析坐标 → 循环下载 → 汇总统计
- [x] 3.3 实现边界处理：无效坐标跳过、空影像跳过、认证失败提示

## 4. WebUI 模块 web.py (NiceGUI)

- [x] 4.1 实现 NiceGUI 页面结构：参数表单（坐标输入、年份下拉框、波段选择、合成方式、数值参数）
- [x] 4.2 实现 `check_gee_auth()` 认证状态检测和 `build_params()` 参数构建
- [x] 4.3 实现 CSV 文件上传解析和坐标预览功能
- [x] 4.4 实现 `run.io_bound()` 异步下载 + `ui.linear_progress()` + `ui.notify()` 进度反馈
- [x] 4.5 实现 `app.storage.user` 表单记忆（页面刷新恢复上次参数）
- [x] 4.6 实现 `create_ui()` 和 `main()` — NiceGUI 应用启动
- [x] 4.7 实现已下载文件列表浏览功能

## 5. 验证

- [x] 5.1 验证 CLI `--help` 输出规范完整
- [x] 5.2 验证 CLI 单点单年下载成功
- [x] 5.3 验证 CLI 无效坐标不崩溃、容错跳过
- [x] 5.4 验证 WebUI 页面可启动、参数表单正常渲染
- [x] 5.5 验证 WebUI GEE 未认证时显示提示
