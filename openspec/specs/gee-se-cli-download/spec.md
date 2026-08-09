# gee-se-cli-download Specification

## Purpose
TBD - created by archiving change gee-satellite-embedding-downloader. Update Purpose after archive.
## Requirements
### Requirement: CLI 坐标输入
系统 SHALL 支持通过 `--coords` / `-c` 参数接收坐标输入，包含两种模式：
- CSV 文件路径（列: `lon,lat,name`，name 可选）
- 命令行字符串：`"lon1,lat1;lon2,lat2"` 格式

系统 SHALL 自动跳过空行和以 `#` 开头的注释行。
系统 SHALL 验证经纬度范围：lon ∈ [-180, 180], lat ∈ [-90, 90]。

#### Scenario: CSV 文件输入
- **WHEN** 用户执行 `python -m SatelliteEmbedding.cli -c coords.csv -y 2024 -p my-project`
- **THEN** 系统读取 CSV 文件，解析所有有效坐标行，跳过空行和注释行

#### Scenario: 命令行字符串输入
- **WHEN** 用户执行 `python -m SatelliteEmbedding.cli -c "108.95,34.25;109.1,34.5" -y 2024 -p my-project`
- **THEN** 系统解析出两个坐标点 (108.95,34.25) 和 (109.1,34.5)

#### Scenario: 无效坐标不崩溃
- **WHEN** 某行坐标超出合法范围（如 lon=200）
- **THEN** 系统输出警告日志，跳过该坐标，继续处理后续坐标

### Requirement: CLI 参数配置
系统 SHALL 支持以下命令行参数，除 `--coords` 和 `--project` 外均有合理默认值：

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `--coords` | `-c` | 必填 | 坐标输入 |
| `--output` | `-o` | `./output` | 输出目录 |
| `--year` | `-y` | `2024` | 单年份下载 |
| `--years` | | 无 | 多年份逗号分隔，如 `2020,2024` |
| `--buffer` | `-b` | `640` | 缓冲区半径（米） |
| `--bands` | | `all` | 波段选择：`all` 或逗号分隔列表如 `A00,A01,A10` |
| `--scale` | `-s` | `10` | 空间分辨率（米/像素） |
| `--crs` | | 自动 | 输出坐标系（默认自动根据坐标选择 UTM 投影） |
| `--format` | `-f` | `GEO_TIFF` | 输出格式 |
| `--cross-year` | | `first` | 跨年合成方式：`first` / `mean` / `median` |
| `--project` | `-p` | 必填 | GCP 项目 ID |

系统 SHALL 在 `--year` 和 `--years` 同时指定时以 `--years` 为准。

#### Scenario: --help 输出规范
- **WHEN** 用户执行 `python -m SatelliteEmbedding.cli --help`
- **THEN** 系统输出所有参数的名称、说明和默认值

#### Scenario: 默认值生效
- **WHEN** 用户仅提供必填参数 `python -m SatelliteEmbedding.cli -c "108.95,34.25" -p my-project`
- **THEN** 系统使用默认值（year=2024, buffer=640, bands=all, cross-year=first, scale=10, crs=自动选择 UTM 投影, format=GEO_TIFF）

### Requirement: GEE 认证与初始化
系统 SHALL 使用 `ee.Authenticate()` 进行 GEE 认证，使用 `ee.Initialize(project=...)` 初始化连接。

#### Scenario: 认证失败
- **WHEN** GEE 认证或初始化失败
- **THEN** 系统打印友好提示，引导用户检查 `earthengine authenticate` 和 GCP project 配置

### Requirement: 影像筛选与合成
系统 SHALL 使用 `ee.Filter.calendarRange(year, year, 'year')` 进行年份过滤。
系统 SHALL 根据 `--bands` 参数选择波段子集（`all` 或逗号分隔列表如 `A00,A01,A10`）。
系统 SHALL 根据 `--cross-year` 参数选择多年份合成方式（first / mean / median）。
系统 SHALL 在 mean 合成后对每个像素执行 L2 重归一化。

#### Scenario: 单年 first 下载
- **WHEN** 用户指定 `-y 2024 --cross-year first`
- **THEN** 系统选取 2024 年的第一景影像，下载 64 波段 GeoTIFF

#### Scenario: 跨年 mean 合成
- **WHEN** 用户指定 `--years "2020,2024" --cross-year mean`
- **THEN** 系统对多年份影像取均值后执行 L2 重归一化，打印重归一化警告日志

#### Scenario: 空影像跳过
- **WHEN** 指定年份和区域内无可用影像
- **THEN** 系统记录警告日志并跳过，不崩溃

### Requirement: 下载执行
系统 SHALL 通过 `image.getDownloadURL()` 获取临时下载链接，使用 `requests` 下载到本地。
系统 SHALL 默认 `filePerBand=False`（64 波段写入单个 GeoTIFF）。

#### Scenario: 单点下载成功
- **WHEN** 用户执行 `python -m SatelliteEmbedding.cli -c "108.95,34.25" -y 2024 -p my-project`
- **THEN** 系统下载含 64 波段的单一 GeoTIFF 文件到输出目录，打印文件名、大小和耗时

#### Scenario: 网络超时重试
- **WHEN** 下载过程中发生网络超时
- **THEN** 系统自动重试最多 3 次（指数退避 1s/2s/4s），全部失败后记录到错误清单

### Requirement: 日志与汇总
系统 SHALL 使用 `logging` 模块同时输出到控制台和 `download.log` 文件。
系统 SHALL 在全部完成后打印汇总统计：成功 N / 失败 N。
系统 SHALL 将失败清单写入 `download_errors.csv`（列: `lon, lat, name, error`）。

#### Scenario: 批量下载汇总
- **WHEN** 批量下载 5 个点（3 成功、2 失败）
- **THEN** 系统打印 `成功 3 / 失败 2`，错误详情写入 `download_errors.csv`

### Requirement: 数据量过大警告
系统 SHALL 在估算下载数据量超过 getDownloadURL 限制（32MB）时发出警告。

#### Scenario: 大缓冲警告
- **WHEN** `--buffer 3000` 导致估算像素数过大
- **THEN** 系统打印数据量警告，建议减小 buffer 或增大 scale，不中断下载

### Requirement: 并发控制
系统 SHALL 逐个串行处理坐标点，避免并发请求触发 GEE API 限流。

#### Scenario: 批量串行处理
- **WHEN** 用户传入多个坐标点
- **THEN** 系统按顺序逐个下载，每个点完成后才开始下一个

