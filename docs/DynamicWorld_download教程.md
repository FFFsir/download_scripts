# DynamicWorld 下载教程

> 面向 `DynamicWorld/` 模块的项目结构分析、下载工作流程与 WebUI 使用指南。
> 核验时间：2026-08-09。文中所有 `file:line` 引用均指向 `D:\Project\光机所项目\download_scripts` 下的源码。
> ⚠️ **CLI 已弃用**：本模块仅通过 WebUI（端口 8000）提供使用入口，`cli.py` 保留仅作代码参考。

## 目录

1. [项目概述](#1-项目概述)
2. [环境与依赖](#2-环境与依赖)
3. [WebUI 使用方法](#3-webui-使用方法)
4. [项目结构分析](#4-项目结构分析)
5. [工作流程](#5-工作流程)
6. [输出文件结构](#6-输出文件结构)
7. [常见问题（FAQ）](#7-常见问题faq)
8. [附录](#8-附录)

---

## 1. 项目概述

**Dynamic World V1（Google Earth Engine）地物分类数据批量下载工具**，按坐标批量下载
DW 逐日分类影像（label 硬分类 0–8 / probs 概率 9 类）。使用方式：

```bash
uv run dw-web     # WebUI（浏览器访问 http://127.0.0.1:8000）
```

要点：

- **数据集**：GEE 公开数据集 `GOOGLE/DYNAMICWORLD/V1`（2016 年起逐日分类，10m 分辨率）。
- **输出**：按坐标点下载 GeoTIFF / ZIPPED_GEO_TIFF / NPY；支持 label（单波段 0-8）与
  probs（9 个概率波段）两类波段。
- **合成策略**：first / mosaic / mode / mean / median / collection（逐景）。
- **代码规模**：`core.py` 840 行 / `cli.py` 158 行 / `web.py` 574 行。
- 深度技术细节（像素对齐原理、GEE API 调用链）可参考
  [2026-07-29-dw-se-architecture-guide.md](./2026-07-29-dw-se-architecture-guide.md)。

---

## 2. 环境与依赖

```bash
cd D:\Project\光机所项目\download_scripts
uv sync
```

首次使用 GEE 需要完成认证（只需一次）：

```bash
earthengine authenticate
```

浏览器会弹出 Google 登录页面，按提示授权即可。之后 `ee.Authenticate()` 会读取本地缓存的凭据，不再弹窗。

> 依赖项见 `pyproject.toml`：`earthengine-api`、`nicegui`、`pillow`、`rasterio`、`requests`。其中 **rasterio + numpy 是文件统计与预览功能**（WebUI 预览图/比色卡）的可选依赖——缺省时这些功能自动降级，下载本身不受影响。

---

## 3. WebUI 使用方法

### 3.1 启动与访问

```bash
uv run dw-web
```

浏览器打开 **http://127.0.0.1:8000**（NiceGUI 服务器，绑定本机 8000 端口，不自动开浏览器）。

### 3.2 页面布局总览

页面为单列布局（最大宽度 900px），从上到下依次为 **5 张卡片**：

```
┌─ ① 认证 ──────────────────────────────┐
│  未认证红色警告 + Project ID 输入 + 初始化按钮 │
├─ ② 坐标输入 ──────────────────────────┤
│  文本框 + CSV 上传（自动回填）              │
├─ ③ 下载参数 ──────────────────────────┤
│  日期 / 波段 / 合成策略 / 输出尺寸 / 分辨率  │
│  输出格式 / CRS / 每波段单独文件           │
├─ ④ 下载执行 ──────────────────────────┤
│  输出目录 + [开始下载]                    │
│  进度条 + 逐点状态通知                    │
├─ ⑤ 已下载文件 ─────────────────────────┤
│  目录导航 + tif/npy 预览 + 统计比色卡      │
└────────────────────────────────────────┘
```

### 3.3 ① 认证

- 页面加载时 `check_gee_auth()` 静默检测凭据（`ee.Initialize()` 试跑，失败不弹浏览器）；
- **未认证**时顶部显示红色警告："请在终端运行 `earthengine authenticate` 完成认证后刷新页面"；
- 输入 **Google Cloud Project ID** 后点 **「初始化认证」**，调用 `init_gee()`（`ee.Authenticate()` + `ee.Initialize(project=...)`），成功/失败均有通知提示。

**获取 Google Cloud Project ID**：

1. 打开 [Google Cloud Console](https://console.cloud.google.com)，项目选择器 → **新建项目**；
2. 输入项目名称，系统自动生成 Project ID（形如 `my-earth-engine-project`）；
3. 启用 Earth Engine API：https://console.cloud.google.com/apis/library/earthengine.googleapis.com
4. 注册 Earth Engine：https://signup.earthengine.google.com

### 3.4 ② 坐标输入

**坐标格式**：

- **文本框**：粘贴分号分隔的坐标字符串，如 `108.95,34.25;116.40,39.90;121.47,31.23`；
  坐标对用 `;` 分隔，经纬度用 `,` 分隔（经度在前）。lon ∈ [-180, 180]，lat ∈ [-90, 90]，
  **越界坐标自动跳过**并打 warning；无法解析的片段也会跳过并打 warning，不中断任务。
- **CSV 上传**：上传含 `lon,lat`（可选 `name`）列的 CSV，自动解析并在文本框中填入坐标；下方显示识别到的点列表（最多预览前 20 个）；解析失败会提示"未能解析到有效坐标"。单文件上限 10MB。

```csv
# 最简模板
lon,lat
108.95,34.25
116.40,39.90

# 含名称模板
lon,lat,name
108.95,34.25,西安
116.40,39.90,北京
121.47,31.23,上海
```

（以 `#` 开头的行和空行会被跳过。）

### 3.5 ③ 下载参数

| 控件 | 默认值 | 说明 |
|------|--------|------|
| 起始日期 / 结束日期 | `2024-01-01` / `2024-12-31` | 原生日期选择器 |
| 波段选择 | `label` | label / probs / all |
| 合成策略 | `first` | first / mosaic / mode / mean / median / collection |
| 输出尺寸（像素，宽=高） | `128` | `target_pixels`，输出正方形边长（推荐 64–512） |
| 空间分辨率（米/像素） | `10` | `scale` |
| 输出格式 | `GEO_TIFF` | GEO_TIFF / ZIPPED_GEO_TIFF / NPY |
| 坐标参考系 (CRS) | 留空 | 留空自动选 UTM 投影 |
| 每波段单独文件 | 开 | `file_per_band` 开关 |

> 输出范围由「输出尺寸 × 分辨率」决定；WebUI **没有**缓冲半径参数（缓冲半径仅存在于 core 层，固定默认 500m，用于合成模式的圆形裁剪）。

### 3.6 ④ 下载执行

- **输出目录**：默认 `./output`，可改任意路径；
- 点击 **「开始下载」** 后：
  - 校验坐标非空，`parse_coords()` 解析，逐点调用 `download_single_point()`（通过 `run.io_bound` 异步执行，不阻塞 UI）；
  - **进度条**实时更新（i/N）；每个点完成后状态区追加一行（成功显示大小与耗时，失败显示原因）并弹通知；
  - 全部完成后进度条满格，提示"完成! 成功 X/N，失败 Y/N"，并自动刷新文件列表。

### 3.7 ⑤ 已下载文件

**文件浏览器**：
- 顶部输入框可输入任意目录路径，点「查看」或刷新图标刷新；
- 子目录以 `📁` 显示（点击进入），非根目录时提供「📂 上一层」按钮；
- 文件以 `📄 名称 (大小)` 显示，附带修改时间；仅列出 `.tif / .zip / .npy` 文件。

**两种预览方式**：
1. 点击文件名 → 新标签页打开 `/preview-tif?filepath=...`，直接渲染 PNG 大图（可另存）；
2. 点击 `📊` 按钮 → **弹窗预览**：
   - **label 文件**：彩色预览图 + 9 类比色卡（类别/颜色/像素数/占比）+ 各类像素统计；
   - **probs 单波段**：灰度图 + 比色卡 + 灰度-概率渐变条（低→高）+ min/max/mean/std；
   - **probs 多波段**：预览图可切换波段（9 个概率波段或 argmax 彩色映射），右侧显示逐波段 μ/σ 统计；
   - **NPY 文件**：显示 shape / ndim / dtype；小尺寸（≤2 维且 ≤16384 元素）展示完整矩阵，否则显示 min/max/mean。

> 预览依赖 `rasterio` + `numpy` + `pillow`；缺失时点击预览会提示"需要 rasterio + Pillow"，下载功能不受影响。

### 3.8 表单记忆

- 每次点「开始下载」时，当前全部表单值（Project ID、坐标、日期、波段、合成、scale、target_pixels、格式、CRS、file_per_band、输出目录）保存到 `app.storage.user`（浏览器 cookie）；
- 关闭浏览器后重新打开页面，自动恢复上次输入。这是 NiceGUI 基于 cookie 的持久化，**按浏览器隔离**。

---

## 4. 项目结构分析

### 4.1 目录树

```
download_scripts/
├── DynamicWorld/                  # DW 数据集下载模块
│   ├── __init__.py                # 模块说明（CLI/WebUI 两种入口）
│   ├── core.py                    # 核心逻辑 (840 行)
│   ├── web.py                     # NiceGUI WebUI (574 行)
│   ├── cli.py                     # 命令行入口（已弃用，仅 WebUI 入口）
│   └── 使用指南.md                # 用户使用指南（本文档的简版入口）
│
├── SatelliteEmbedding/            # SE 数据集下载模块（镜像架构，独立代码）
│   ├── __init__.py / core.py / cli.py / web.py / 使用指南.md
│
├── tests/
│   ├── test_core.py               # DW core 单元测试
│   ├── test_cli.py                # DW cli 单元测试
│   ├── test_web.py                # DW web 单元测试
│   └── test_se_*.py               # SE 对应测试
│
├── pyproject.toml                 # 依赖 + 入口脚本注册
└── output/                        # 默认输出目录（`./output`，WebUI 输出目录默认值）
```

`pyproject.toml` 注册的 WebUI 入口：

| 入口 | 命令 | 等价调用 |
|------|------|---------|
| `dw-web` | `uv run dw-web` | `python -m DynamicWorld.web` |

### 4.2 三模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| `core.py` | 全部核心逻辑：GEE 认证、坐标解析、UTM 投影计算、ROI 构造、影像构建、下载执行、日志、文件统计与预览 | 仅依赖 `ee` / `requests` 等第三方库 |
| `web.py` | NiceGUI WebUI：表单、CSV 上传、进度反馈、文件浏览器、预览弹窗 | `from DynamicWorld.core import ...`（显式命名导入，web.py:17-28） |
| `cli.py` | 命令行入口（**已弃用**，仅作代码参考） | `from DynamicWorld.core import ...`（显式命名导入，cli.py:14-22） |

**依赖关系**：`web.py` 只调用 `core.py` 的函数，`core.py` 不反向依赖任何 UI 层——这是标准的"核心逻辑与界面分离"结构。

```
                ┌─────────────────────┐
                │      core.py         │
                │  CoordPoint /        │
                │  DownloadResult      │
                │  init_gee()          │
                │  parse_coords()      │
                │  _get_utm_epsg()     │
                │  _create_square_roi()│
                │  build_image()       │
                │  download_image()    │
                │  download_single_    │
                │    point()           │
                │  setup_logging()     │
                └─────────┬───────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
    ┌───────▼────────┐        ┌─────────▼───────┐
    │  web.py (WebUI) │        │  cli.py（已弃用）│
    │  NiceGUI 界面   │        │  仅作代码参考     │
    └───────┬─────────┘        └─────────┬───────┘
            └─────────────┬──────────────┘
                          │
              ┌───────────▼────────────┐
              │ GEE getDownloadURL +   │
              │ requests HTTP 下载     │
              └────────────────────────┘
```

### 4.3 关键数据类（core.py）

**`CoordPoint`** — 单个坐标点

| 字段 | 类型 | 说明 |
|------|------|------|
| `lon` | float | 经度，[-180, 180] |
| `lat` | float | 纬度，[-90, 90] |
| `name` | str | 点位名称；用户未提供时自动生成为 `"lon,lat"` |

**`DownloadResult`** — 单点下载结果

| 字段 | 类型 | 说明 |
|------|------|------|
| `point` | CoordPoint | 原始坐标点 |
| `success` | bool | 是否成功 |
| `filepath` | str\|None | 成功时的文件路径（collection 模式为目录） |
| `size_mb` | float | 文件大小 (MB) |
| `elapsed_sec` | float | 下载耗时 (秒) |
| `error` | str\|None | 失败原因 |

`download_single_point()` **从不抛出异常**——内部捕获一切错误并包装成 `DownloadResult(success=False)`，WebUI 据此判断成功/失败。

### 4.4 核心函数索引

| 函数 | 位置 | 功能 |
|------|------|------|
| `init_gee(project_id)` | core.py:55 | 认证 + 初始化 GEE |
| `parse_coords(input)` | core.py:80 | CSV 或字符串 → `list[CoordPoint]` |
| `_get_utm_epsg(lon, lat)` | core.py:164 | 自动选 UTM EPSG 码 |
| `_create_square_roi(...)` | core.py:187 | 构造像素对齐的 N×N 正方形 ROI |
| `create_roi(lon, lat, buffer)` | core.py:241 | 圆形缓冲 ROI（500m 默认） |
| `build_image(roi, ...)` | core.py:264 | 筛选 + 合成 DW 影像 |
| `download_image(image, ...)` | core.py:342 | getDownloadURL + 重试下载 |
| `download_single_point(...)` | core.py:404 | **顶层单点流水线** |
| `setup_logging(output)` | core.py:524 | 控制台 + download.log 双写 |
| `write_error_csv(...)` | core.py:552 | 失败清单 → download_errors.csv |
| `list_tif_files(dir)` | core.py:573 | 平铺文件列表 |
| `list_dir_contents(dir)` | core.py:601 | 目录+文件统一列表（WebUI 用） |
| `get_tif_stats(filepath)` | core.py:644 | label 类别统计 / probs 数值统计 |
| `tif_to_preview_png(...)` | core.py:733 | GeoTIFF → 彩色 PNG 预览 |

---

## 5. 工作流程

### 5.1 单点下载流水线 `download_single_point()`（core.py:404）

WebUI 与 CLI（已弃用）共用的顶层流水线：

```
参数: (point, output_dir, params)
   │
   ├─ 1. scale = params["scale"]，crs = params["crs"] 或 _get_utm_epsg(lon, lat)
   ├─ 2. _create_square_roi() → (wgs84_rect, utm_rect)
   │       在 UTM 米制坐标系中构造 N×N 正方形，NW 角点对齐到 scale 整数倍，
   │       保证输出像素精确 = target_pixels × target_pixels
   ├─ 3. create_roi(buffer=500) → 中心点 buffer 的圆形几何（供影像裁剪）
   ├─ 4. 生成基础文件名: {bands}_{composite}_E{lon}_N{lat}_{start}_{end}
   ├─ 5. build_image(roi, start, end, bands, composite)
   │       ImageCollection("GOOGLE/DYNAMICWORLD/V1")
   │         .filterBounds(roi).filterDate(start, end)
   │         .select(波段子集)
   │         .合成 或 .逐景返回
   │       无影像 → DownloadResult(success=False, "无可用影像")
   │
   ├─ ◆ collection 模式（逐景）─────────────────────────────
   │   ├─ 建点位子目录: output/{base_name}/
   │   ├─ aggregate_array("system:time_start") 取每景时间戳
   │   ├─ 逐景: download_image(img.clip(wgs84_rect), region=utm_rect)
   │   │        文件名追加时间戳 {base_name}_{YYYYMMDD_HHMMSS}.tif
   │   └─ 汇总各景大小；若全部失败 → success=False
   │
   └─ ◆ 合成模式（first/mosaic/mode/mean/median）──────────
       └─ download_image(image, region=utm_rect, crs=utm_crs)
            单文件输出到 output/{base_name}.tif
```

> **输出尺寸说明**：输出边长像素由 WebUI 的「输出尺寸（像素）」控件（`target_pixels`，默认 128）
> 与「分辨率（米/像素）」（`scale`，默认 10）共同决定；`buffer`（core 层默认 500m）只决定
> 合成模式的圆形有效数据区，**不决定输出尺寸**，且 WebUI 无该参数。

### 5.2 下载执行与重试 `download_image()`（core.py:342）

```python
params = {
    "scale": scale,        # 米/像素（UTM 投影下）
    "crs": crs,            # 自动选择的 EPSG:326XX / 327XX
    "format": fmt,         # GEO_TIFF / ZIPPED_GEO_TIFF / NPY
    "filePerBand": file_per_band,   # DW 默认 True，每波段单独文件
    "region": utm_rect,    # UTM 原生矩形（保证像素精确对齐）
}
url = image.getDownloadURL(params)   # GEE 返回临时下载链接
requests.get(url, timeout=300)        # 单次超时 5 分钟
```

**重试策略**：指数退避 `1s → 2s → 4s`，最多 3 次；HTTP 非 200 或网络异常均重试；全部失败抛 `RuntimeError`。

### 5.3 输出裁剪细节

| 模式 | 裁剪方式 | 结果 |
|------|---------|------|
| 合成模式 (first/mosaic/mode/mean/median) | `image.clip(圆形 buffer ROI)` | 圆形可见区域，**四角为 NoData**（默认灰/黑） |
| collection 模式（逐景） | `img.clip(方形 wgs84_rect)` | 正方形裁剪，四角无 NoData |

> 注意：两种模式裁剪范围不同。合成模式为 **500m 半径圆形缓冲**，输出尺寸（边长像素）由 `target_pixels` 决定；collection 模式输出尺寸同样由 `target_pixels` 决定，但裁剪为正方形。

### 5.4 日志

- `setup_logging()` 将日志同时写入**控制台**（INFO 级）和 **`output/download.log`**（DEBUG 级，UTF-8）。
- 失败点额外写入 **`output/download_errors.csv`**（列：`lon,lat,name,error`），仅在存在失败时生成。
- 注意：download.log 会在 `setup_logging` 指定的 `output_dir` 下创建；WebUI 中该目录为页面填写的"输出目录"。

---

## 6. 输出文件结构

### 6.1 文件命名格式

```
{波段}_{合成}_E{经度}_N{纬度}_{起始日期}_{结束日期}.tif
```

日期部分**直接使用用户输入的原始字符串**（含连字符 `-`）：

```
label_mode_E121.4025_N25.1947_2024-01-01_2024-12-31.tif
probs_mean_E121.4025_N25.1947_2024-01-01_2024-12-31.tif
```

### 6.2 目录结构

合成模式（默认输出目录 `./output`）：

```
output/
├── label_mode_E108.95_N34.25_2024-01-01_2024-12-31.tif
├── download.log
└── download_errors.csv        # 仅当存在失败点时生成
```

collection 模式下每个点位一个子文件夹，逐景文件追加时间戳：

```
output/
└── label_collection_E108.95_N34.25_2024-01-01_2024-12-31/
    ├── label_collection_E108.95_N34.25_2024-01-01_2024-12-31_20240101_030000.tif
    ├── label_collection_E108.95_N34.25_2024-01-01_2024-12-31_20240102_030000.tif
    └── ...
```

### 6.3 汇总输出

WebUI 下载完成后的汇总展示：

```
========== 下载汇总 ==========
  总计: 7 点
  成功: 7 点
  失败: 0 点
  下载总量: 35.2 MB
  总耗时: 120.5 s
================================
```

---

## 7. 常见问题（FAQ）

**Q1: "Caller does not have required permission"**
Project ID 未启用 Earth Engine API。在 Cloud Console 中启用（见 [3.3 认证](#33-认证)）。

**Q2: "Earth Engine client library not initialized"**
运行 `earthengine authenticate` 完成认证，或在 WebUI 认证卡片填入 Project ID 点击「初始化认证」。

**Q3: 下载文件打不开**
- `GEO_TIFF` → QGIS 直接打开；
- `ZIPPED_GEO_TIFF` → 先解压；
- `NPY` → `numpy.load()`（shape: label `(N,N)` uint8 / probs `(9,N,N)` float32）。

**Q4: 区域过大报错**
GEE 单次限制 ≤ 32MB、≤ 10000×10000 像素。在 WebUI 中增大「空间分辨率（米/像素）」或减小「输出尺寸（像素）」。

**Q5: "跳过越界坐标"**
坐标超出合法范围（lon ±180, lat ±90）。检查经纬度顺序：**经度在前，纬度在后**。

**Q6: "无可用影像"**
该区域在指定时间范围内无数据。检查日期（DW 数据从 2016 年起）、确认坐标在陆地。

**Q7: 合成模式下载的 tif 是圆形的 / 四角是黑的**
正常现象：合成模式用 500m 半径的**圆形**缓冲裁剪，四角为 NoData。collection 模式则是正方形裁剪。

**Q8: label vs probs 怎么选**
- 做分类图 → 波段选 `label` + 合成策略 `mode`；
- 做不确定性分析 → 波段选 `probs` + 合成策略 `mean`。

**Q9: WebUI 打开后一直提示"未检测到 GEE 认证"**
1. 终端运行 `earthengine authenticate`；
2. 页面填入 Project ID 并点击「初始化认证」；
3. 刷新页面。

---

## 8. 附录

### 8.1 波段与合成方式

**label vs probs**：

| 波段 | 内容 | 用途 |
|------|------|------|
| `label` | 单波段，值 0-8 | 分类图，直接可用 |
| `probs` | 9 个概率波段，值 0-1 | 不确定性分析、变化检测 |
| `all` | 以上全部 10 个波段 | 完整数据 |

**Dynamic World 类别**（label 值 → 类别 → 颜色）：

| 值 | 类别 | 颜色 |
|----|------|------|
| 0 | 水体 | `#419BDF` |
| 1 | 树木 | `#397D49` |
| 2 | 草地 | `#88B053` |
| 3 | 淹水植被 | `#7A87C6` |
| 4 | 作物 | `#E49635` |
| 5 | 灌丛 | `#DFC35A` |
| 6 | 建筑 | `#C4281B` |
| 7 | 裸地 | `#A59B8F` |
| 8 | 冰雪 | `#B39FE1` |

**合成策略**（WebUI「合成策略」下拉）：

| 策略 | 说明 | 推荐场景 |
|------|------|---------|
| `first` | 取第一景（时间最早，`collection.first()`） | 快速预览 |
| `mosaic` | 空间镶嵌 | 大区域 |
| `mode` | 时序众数 | **label 推荐** |
| `mean` | 时序均值 | **probs 推荐** |
| `median` | 时序中位数 | 抗噪声 |
| `collection` | 不做合成，逐景下载 | 时间序列分析 |

**WebUI 推荐组合**：
- 分类图 → 波段 `label` + 合成 `mode`
- 概率分布 → 波段 `probs` + 合成 `mean`
- 每景原始数据 → 合成 `collection`

### 8.2 坐标参考系 (CRS)

默认根据坐标自动选择 UTM 投影（EPSG:32601–32660 北半球 / EPSG:32701–32760 南半球）。极地区域（纬度 > 84° 或 < -80°）回退到 `EPSG:4326`。

| EPSG 代码 | 名称 | 适用区域 |
|-----------|------|---------|
| `EPSG:326XX` | UTM 北半球 | 北纬 0°–84°（默认） |
| `EPSG:327XX` | UTM 南半球 | 南纬 0°–80°（默认） |
| `EPSG:4326` | WGS84 | 全球（极地区域回退） |
| `EPSG:3857` | Web Mercator | Web 地图 |
| `EPSG:4490` | CGCS2000 | 中国大陆 |
| `EPSG:32650` | WGS84 / UTM 50N | 中国东部 |

**为什么用 UTM**：EPSG:4326 以度为像素单位，`cos(lat)` 会让经度方向像素被拉长；UTM 是米制投影，`scale=10` 即严格 10m/px。

### 8.3 已知问题

> 本节记录代码中已发现但**尚未修复**的问题，便于使用者规避。

- **web.py 表单恢复引用未定义的 `buffer_input`**：`web.py` 中恢复上次输入时存在 `if mem.get("buffer"): buffer_input.set_value(...)`（web.py:260-261），但页面并未创建 `buffer_input` 控件。若浏览器 cookie 中残留 `buffer` 键（旧版本表单保存过），页面加载时会抛 `NameError`，导致 WebUI 无法打开。规避方式：清除该站点的 cookie（或按 F12 删除 `buffer` cookie）后刷新。**注意：WebUI 本身没有 buffer 参数，此键不应存在。**

### 8.4 与 SatelliteEmbedding 模块的关系

- DynamicWorld 与 SatelliteEmbedding 是**两个独立模块**：架构镜像（都是 core/cli/web 三层），但**不共享代码**——SE 并不 `import DynamicWorld`；
- 两者共享同一份 `pyproject.toml` 依赖，各自注册独立 WebUI 入口：`dw-web` 与 `se-web`；
- 数据集不同：DW = `GOOGLE/DYNAMICWORLD/V1`（逐日分类），SE = `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`（年度 64 维嵌入向量）；
- 功能差异：DW 支持 label/probs 波段与 collection 逐景下载、每波段单独文件；SE 为 64 波段单文件输出、按年份/多年份合成、mean 合成自动 L2 归一化。
- SE 的细节参见 `SatelliteEmbedding/使用指南.md` 与仓库架构文档 `docs/2026-07-29-dw-se-architecture-guide.md`。
