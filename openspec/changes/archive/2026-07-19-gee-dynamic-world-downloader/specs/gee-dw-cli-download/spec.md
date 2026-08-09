## ADDED Requirements

### Requirement: CLI 坐标输入
系统 SHALL 支持通过 `--coords` / `-c` 参数接收坐标输入，包含两种模式：
- CSV 文件路径（列: `lon,lat,name`，name 可选）
- 命令行字符串：`"lon1,lat1;lon2,lat2"` 格式

系统 SHALL 自动跳过空行和以 `#` 开头的注释行。
系统 SHALL 验证经纬度范围：lon ∈ [-180, 180], lat ∈ [-90, 90]。

#### Scenario: CSV 文件输入
- **WHEN** 用户执行 `python cli.py -c coords.csv -p my-project`
- **THEN** 系统读取 CSV 文件，解析所有有效坐标行，跳过空行和注释行

#### Scenario: 命令行字符串输入
- **WHEN** 用户执行 `python cli.py -c "108.95,34.25;109.1,34.5" -p my-project`
- **THEN** 系统解析出两个坐标点 (108.95,34.25) 和 (109.1,34.5)

#### Scenario: 无效坐标不崩溃
- **WHEN** 某行坐标超出合法范围（如 lon=200）
- **THEN** 系统输出警告日志，跳过该坐标，继续处理后续坐标

### Requirement: CLI 参数配置
系统 SHALL 支持以下命令行参数，所有参数（除 `--coords` 和 `--project`）均有合理默认值：

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `--coords` | `-c` | 必填 | 坐标输入 |
| `--output` | `-o` | `./output` | 输出目录 |
| `--start-date` | | `2024-01-01` | 起始日期 |
| `--end-date` | | `2024-12-31` | 结束日期 |
| `--buffer` | `-b` | `500` | 缓冲区半径（米） |
| `--bands` | | `label` | 波段选择 |
| `--scale` | `-s` | `10` | 空间分辨率 |
| `--crs` | | `EPSG:4326` | 输出坐标系 |
| `--format` | `-f` | `GEO_TIFF` | 输出格式 |
| `--file-per-band` | | `True` | 每波段单独文件 |
| `--composite` | | `first` | 合成方式 |
| `--merge` | | `False` | 合并下载 |
| `--project` | `-p` | 必填 | GCP 项目 ID |

#### Scenario: --help 输出规范
- **WHEN** 用户执行 `python cli.py --help`
- **THEN** 系统输出所有参数的名称、说明和默认值

#### Scenario: 默认值生效
- **WHEN** 用户仅提供必填参数 `python cli.py -c "108.95,34.25" -p my-project`
- **THEN** 系统使用所有其他参数的默认值执行下载

### Requirement: GEE 认证与初始化
系统 SHALL 使用 `ee.Authenticate()` 进行 GEE 认证，使用 `ee.Initialize(project=...)` 初始化连接。

#### Scenario: 首次认证
- **WHEN** 用户首次运行且未认证
- **THEN** 系统触发浏览器 OAuth 流程，认证成功后持久化凭据

#### Scenario: 认证失败
- **WHEN** GEE 认证或初始化失败
- **THEN** 系统打印友好提示，引导用户检查 `gcloud auth` 和 GCP project 配置

### Requirement: 影像筛选与合成
系统 SHALL 根据 `--bands` 参数选择波段（label / probs / all），根据 `--composite` 参数选择合成方式（first / mosaic / mode / mean / median）。

- `label`: 单选 `label` 波段
- `probs`: 选择 9 个概率波段（water, trees, grass, flooded_vegetation, crops, shrub_and_scrub, built, bare, snow_and_ice）
- `all`: 选择全部 10 个波段

#### Scenario: label 波段下载
- **WHEN** 用户指定 `--bands label --composite first`
- **THEN** 系统下载单个 label 波段的 GeoTIFF

#### Scenario: probs 波段均值合成
- **WHEN** 用户指定 `--bands probs --composite mean`
- **THEN** 系统对 9 个概率波段分别取时序均值后下载

#### Scenario: 空影像跳过
- **WHEN** 指定时间范围和区域内无可用影像
- **THEN** 系统记录警告日志并跳过，不崩溃

### Requirement: 下载执行
系统 SHALL 通过 `image.getDownloadURL()` 获取临时下载链接，使用 `requests` 下载到本地。

#### Scenario: 单点下载成功
- **WHEN** 用户执行 `python cli.py -c "108.95,34.25" -p my-project`
- **THEN** 系统下载 GeoTIFF 文件到输出目录，打印文件名、大小和耗时

#### Scenario: 网络超时重试
- **WHEN** 下载过程中发生网络超时
- **THEN** 系统自动重试最多 3 次（指数退避 1s/2s/4s），全部失败后记录到错误清单

#### Scenario: 输出目录自动创建
- **WHEN** 指定的输出目录不存在
- **THEN** 系统自动创建 `os.makedirs` 目录

### Requirement: 日志与汇总
系统 SHALL 使用 `logging` 模块同时输出到控制台和 `download.log` 文件。
系统 SHALL 在全部完成后打印汇总统计：成功 N / 失败 N / 跳过 N。
系统 SHALL 将失败清单写入 `download_errors.csv`（列: `lon, lat, name, error`）。

#### Scenario: 批量下载汇总
- **WHEN** 批量下载 5 个点（3 成功、1 失败、1 跳过）
- **THEN** 系统打印 `成功 3 / 失败 1 / 跳过 1`，错误详情写入 `download_errors.csv`

### Requirement: 区域过大处理
系统 SHALL 在检测到下载区域可能超过 getDownloadURL 限制（32MB 或单边 10000 像素）时发出警告。

#### Scenario: 大区域警告
- **WHEN** 估算下载像素数超过限制
- **THEN** 系统打印警告，建议使用 GEE Code Editor 的 Export 功能

### Requirement: 并发控制
系统 SHALL 逐个串行处理坐标点，避免并发请求触发 GEE API 限流。

#### Scenario: 批量串行处理
- **WHEN** 用户传入多个坐标点
- **THEN** 系统按顺序逐个下载，每个点完成后才开始下一个
