## Why

为所内研究人员提供便捷的 Dynamic World V1 数据下载工具。当前手动在 GEE Code Editor 中编写代码下载数据效率低、门槛高。需要一个支持 CLI 批量和 WebUI 可视化操作的统一工具，降低使用门槛，提高数据获取效率。

## What Changes

- 新增 GEE Dynamic World V1 数据下载 Python 脚本，支持 CLI 命令行和 FastAPI WebUI 两种交互方式
- 实现坐标解析（CSV 文件 / 命令行字符串）、ROI 构造、影像筛选与合成、下载执行等核心功能
- 提供 FastAPI WebUI 页面，支持表单参数配置、CSV 上传、SSE 实时进度推送
- 完善错误处理：认证失败提示、坐标验证、网络重试、空影像跳过、大区域自动切换 toDrive
- 统一日志输出：控制台 + 文件双写、下载汇总统计、失败清单 CSV

## Capabilities

### New Capabilities
- `gee-dw-cli-download`: GEE Dynamic World V1 数据 CLI 下载，支持多坐标批量下载、多种合成方式与波段选择
- `gee-dw-webui`: FastAPI WebUI，提供可视化参数配置、CSV 上传、SSE 实时下载进度反馈

### Modified Capabilities
<!-- 无已有 capability 需修改 -->

## Impact

- 新增文件: `DynamicWorld/core.py`, `DynamicWorld/cli.py`, `DynamicWorld/web.py`, `DynamicWorld/templates/index.html`
- 新增依赖: `earthengine-api`, `requests`, `fastapi`, `uvicorn`, `jinja2`
- 下载目标路径: `D:\Project\光机所项目\download\DynamicWorld`（可通过参数覆盖）
- 不影响现有代码
