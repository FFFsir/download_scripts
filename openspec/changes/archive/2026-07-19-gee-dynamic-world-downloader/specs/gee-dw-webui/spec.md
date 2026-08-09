## ADDED Requirements

### Requirement: WebUI 参数表单
系统 SHALL 使用 NiceGUI 提供纯 Python WebUI 页面，包含所有下载参数对应的 NiceGUI 控件：
- 坐标输入：tabs 切换 `ui.textarea()` 粘贴坐标和 `ui.upload()` CSV 上传
- 日期范围：`ui.date()` 选择器
- 数值参数：`ui.number()` 输入框
- 下拉选择：`ui.select()` 控件
- 开关：`ui.switch()` 控件
- 必填项：`ui.input()` GCP 项目 ID
- 提交按钮：`ui.button()` 开始下载

#### Scenario: 表单填写并提交
- **WHEN** 用户在 WebUI 填写所有参数并点击"开始下载"
- **THEN** 系统开始执行下载，通过 `ui.linear_progress()` 和 `ui.notify()` 推送进度

#### Scenario: CSV 文件上传
- **WHEN** 用户通过 `ui.upload()` 上传 CSV 文件作为坐标输入
- **THEN** 系统解析 CSV 内容，显示坐标点数量和列表预览

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
系统 SHALL 支持通过 `python web.py` 独立启动 NiceGUI 服务。

#### Scenario: 启动 Web 服务
- **WHEN** 用户执行 `python web.py`
- **THEN** NiceGUI 启动服务，默认监听 `http://127.0.0.1:8000`

### Requirement: GEE 认证状态检测
系统 SHALL 在 WebUI 页面加载时通过 `try ee.Initialize()` 检测 GEE 认证状态。

#### Scenario: 未认证提示
- **WHEN** 用户打开 WebUI 但 GEE 未认证
- **THEN** 页面显示警告 banner，引导用户先在有 GUI 环境运行 `python cli.py --auth-only` 完成认证；隐藏下载表单

#### Scenario: 已认证正常使用
- **WHEN** 用户打开 WebUI 且 GEE 已认证
- **THEN** 页面正常显示参数表单，可提交下载任务
