## 1. 环境准备

- [x] 1.1 使用 `uv add` 安装依赖：`earthengine-api`, `requests`, `nicegui`, `pytest`

## 2. 核心模块 core.py

- [x] 2.1 实现 `init_gee(project_id)` — GEE 认证与初始化
- [x] 2.2 实现 `parse_coords(input_str)` — 坐标解析（CSV 文件路径 / 命令行字符串两种模式），含验证与跳过逻辑
- [x] 2.3 实现 `create_roi(lon, lat, buffer_m)` — ROI 点缓冲构造
- [x] 2.4 实现 `build_image(roi, start_date, end_date, bands, composite)` — 影像筛选与合成
- [x] 2.5 实现 `download_image(image, output_path, name, scale, crs, fmt, file_per_band)` — 下载执行（含网络重试3次指数退避）
- [x] 2.6 实现 `setup_logging(output_dir)` — 日志配置（控制台 + download.log 双写）
- [x] 2.7 实现 `write_error_csv(output_dir, errors)` — 失败清单写入 download_errors.csv

## 3. CLI 模块 cli.py

- [x] 3.1 使用 argparse 实现所有命令行参数
- [x] 3.2 实现 `main()` — 串联：认证 → 解析坐标 → 循环下载 → 汇总统计
- [x] 3.3 实现边界处理：无效坐标跳过、空影像跳过、认证失败提示

## 4. WebUI 模块 web.py (NiceGUI)

- [x] 4.1 实现 NiceGUI 页面：参数表单（文本框/日期选择器/下拉框/开关/文件上传）
- [x] 4.2 实现 `check_gee_auth()` 认证状态检测和 `build_params()` 参数构建
- [x] 4.3 实现 `create_ui()` 和 `main()` — NiceGUI 应用启动
- [x] 4.4 实现 `await run.io_bound()` 异步下载 + `ui.linear_progress()` + `ui.notify()` 进度反馈
- [x] 4.5 实现 CSV 文件上传解析和坐标预览功能

## 5. 验证

- [x] 5.1 验证完整测试套件：51 passed
- [x] 5.2 验证 CLI `--help` 输出规范
- [x] 5.3 验证 CLI 无效坐标不崩溃（测试覆盖）
