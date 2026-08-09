# SatelliteEmbedding 下载教程

> 面向 `SatelliteEmbedding/` 模块的项目结构分析、下载工作流程与 WebUI 使用指南。
> 核验时间：2026-08-09。文中所有 `file:line` 引用均指向 `D:\Project\光机所项目\download_scripts` 下的源码。
> ⚠️ **CLI 已弃用**：本模块仅通过 WebUI（端口 8001）提供使用入口，`cli.py` 保留仅作代码参考。

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

**Satellite Embedding V1 遥感嵌入向量批量下载工具**，基于 Google Earth Engine，按坐标批量下载遥感嵌入向量数据。使用方式：

```bash
uv run se-web     # WebUI（浏览器访问 http://127.0.0.1:8001）
```

数据来自 GEE 公开数据集 `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`，核心特征：

| 属性 | 值 |
|------|-----|
| 数据集 ID | `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` |
| 波段数量 | 64（A00–A63），整体构成 64 维嵌入向量 |
| 值域 | [-1, 1]，单位向量 |
| 空间分辨率 | 10m |
| 时间范围 | 2017–2024 年度合成 |
| 原始投影 | 本地 UTM（下载时自动重投影至指定 CRS） |

64 个波段是一个整体，代表地理位置的 64 维嵌入向量，各维度不可独立使用。

> 深度技术细节（像素对齐原理、GEE API 调用链）可参考
> [2026-07-29-dw-se-architecture-guide.md](./2026-07-29-dw-se-architecture-guide.md)。

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

浏览器会弹出 Google 登录页面，按提示授权即可。

> 依赖项见 `pyproject.toml`：`earthengine-api`、`nicegui`、`pillow`、`rasterio`、`requests`。其中 **rasterio + numpy 是 GeoTIFF 预览功能**的可选依赖——缺省时预览自动降级，下载本身不受影响。

---

## 3. WebUI 使用方法

### 3.1 启动

```bash
uv run se-web
```

浏览器打开 **http://127.0.0.1:8001**。

> **注意端口为 8001**，与 DW WebUI 的 8000 不同，两者可同时运行。首次使用如提示未认证，先完成 [2. 环境与依赖](#2-环境与依赖)。

### 3.2 页面布局

单页应用，自上而下五个卡片：

```
┌─ ① 认证 ───────────────────────────────────────────┐
│   GEE 认证状态提示 + Project ID + [初始化认证]        │
├─ ② 坐标输入 ────────────────────────────────────────┤
│   坐标文本框（分号分隔）+ CSV 文件上传                 │
├─ ③ 下载参数 ────────────────────────────────────────┤
│   年份/多年份 · 波段 · 合成策略 · 输出尺寸 · 分辨率    │
│   输出格式 · CRS                                     │
├─ ④ 下载执行 ────────────────────────────────────────┤
│   输出目录 + [开始下载] 进度条 + 逐点结果              │
├─ ⑤ 已下载文件 ──────────────────────────────────────┤
│   目录浏览 + [预览]/[查看数据]                       │
└─────────────────────────────────────────────────────┘
```

### 3.3 认证区

- 页面加载时自动检测认证状态（`check_gee_auth`），未认证时顶部显示红色警告：*"请在终端运行 `earthengine authenticate` 完成认证后刷新页面"*。
- 输入 **Google Cloud Project ID**，点击「初始化认证」。成功后绿色通知提示。

**获取 Google Cloud Project ID**：

1. 打开 [Google Cloud Console](https://console.cloud.google.com)
2. 项目选择器 → **新建项目**
3. 输入项目名称，系统自动生成 Project ID
4. 启用 Earth Engine API: https://console.cloud.google.com/apis/library/earthengine.googleapis.com
5. 注册 Earth Engine: https://signup.earthengine.google.com

### 3.4 坐标输入

**坐标格式**：

- **文本框粘贴**：分号分隔的坐标字符串，如 `108.95,34.25;116.40,39.90;121.47,31.23`；
  坐标对用 `;` 分隔，经纬度用 `,` 分隔（经度在前）。lon ∈ [-180,180]，lat ∈ [-90,90]，
  **越界坐标自动跳过**并打 warning；无法解析的片段也会跳过，不中断任务。
- **上传 CSV**：点击上传文件（≤10MB，需含 `lon,lat` 列，`name` 可选）。上传后自动解析并填入文本框，并显示识别到的坐标点名称列表（最多前 20 个）；被跳过的无效行（越界或格式错误）会弹出黄色提示。

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

### 3.5 下载参数

| 控件 | 默认值 | 说明 |
|------|--------|------|
| 单年份 | `2024` | 下拉框选择 2017–2024 |
| 多年份 | 留空 | 逗号分隔如 `2022,2023,2024`，**优先级高于单年份** |
| 波段选择 | `all` | `all`（全部 64 波段）或逗号分隔如 `A00,A01,A10` |
| 跨年合成策略 | `first` | `first` / `mean` / `median`（mean 自动 L2 归一化） |
| 输出尺寸 (像素) | `128` | 正方形宽=高，如 128 → 输出 128×128 |
| 空间分辨率 | `10` | 米/像素 |
| 输出格式 | `GEO_TIFF` | `GEO_TIFF` / `ZIPPED_GEO_TIFF` / `NPY` |
| CRS | 留空 | 留空自动选择 UTM 投影，可手动指定如 `EPSG:4326` |

> 「输出尺寸 (target_pixels)」直接控制下载像素范围（N×N 像素，边长 = N × scale）。
> 128px @ 10m 的下载范围是 1280m × 1280m 正方形，半边长 640m——与 core 层默认圆形缓冲
> 半径 640m 量级相当（缓冲半径仅存在于 core 层，WebUI 无该参数）。

### 3.6 下载执行

1. 填写**输出目录**（默认 `./output`，相对启动目录）。
2. 点击「开始下载」。页面校验：坐标为必填；多年份需为逗号分隔整数。
3. 下载过程：顶部进度条实时推进，标签显示 `下载中: 点名称 (i/total)`；每点完成后弹出通知（成功绿色 / 失败红色），下方结果列表逐行显示 `点名称: 完成 (大小MB, 耗时s)` 或 `点名称: 失败 -- 错误信息`。
4. 全部结束后进度条 100%，显示 `完成! 成功 x/total，失败 y/total`，并自动刷新下方文件列表。

### 3.7 已下载文件浏览与预览

内置目录浏览器（默认浏览 `./output`）：

- **目录导航**：`📁 子目录` 可点击进入；非根目录时显示「📂 上一层」按钮；右上角「查看」「🔄 刷新」按钮。
- **文件列表**：显示名称、大小 (MB)、修改时间。
  - `📄 *.tif` → 右侧「**预览**」按钮
  - `📊 *.npy` → 右侧「**查看数据**」按钮
  - `*.zip` → 仅展示（无预览按钮）

**GeoTIFF 预览**（`.tif`，需已安装 `rasterio` + `Pillow`）：
- 弹出弹窗显示选中波段的**灰度预览图**（值域 [-1,1] 线性映射 → 黑白色带，长边最大 900px）。
- 下拉框可切换波段 **A00–A63**，预览图实时更新。
- 侧栏显示文件大小、修改时间、波段数 (64)、值域 ([-1,1] float32)，附黑→白渐变图例。
- 仅单波段灰度预览：SE 是 64 维向量，无分类语义，不做 DW 那样的分类彩色图。

**NPY 数据预览**（`.npy`）：
- 显示数据**形状**、**维度**、**数据类型**（如 `(64, 128, 128)` float32）。
- 二维以内且元素 ≤ 16384 时直接显示数据矩阵；否则显示 min / max / mean 统计。
- 同时展示文件大小与修改时间。NPY 下载时自动生成的 `.npz` 压缩副本保存在同目录（文件浏览器仅列出 `.tif/.zip/.npy`，`.npz` 不在列表内，可在本地目录查看）。

### 3.8 表单记忆（Cookie 持久化）

WebUI 通过 `app.storage.user`（cookie 加密存储，密钥 `storage_secret`）在每次「开始下载」时保存全部输入，页面刷新/重开浏览器后自动恢复：Project ID、坐标、年份、多年份、波段、合成策略、输出尺寸、分辨率、格式、CRS、输出目录。**无需重复填写**。

---

## 4. 项目结构分析

### 4.1 目录结构

```
download_scripts/
├── SatelliteEmbedding/            # SE 数据集下载模块
│   ├── __init__.py                # 包说明（CLI / Web 两种用法）
│   ├── core.py                    # 核心逻辑（700 行）
│   ├── web.py                     # NiceGUI WebUI（503 行）
│   ├── cli.py                     # 命令行入口（已弃用，仅 WebUI 入口）
│   └── 使用指南.md                # 用户使用指南
│
├── DynamicWorld/                  # DW 数据集下载模块（架构镜像，独立代码）
│
├── docs/                          # 项目文档
├── tests/                         # 单元测试
│   ├── test_se_core.py            # SE core 测试（832 行）
│   ├── test_se_cli.py             # SE cli 测试（153 行）
│   └── test_se_web.py             # SE web 测试（164 行）
│
└── pyproject.toml                 # 定义入口脚本 se-web
```

`pyproject.toml` 中声明的 WebUI 入口：

```toml
[project.scripts]
se-web = "SatelliteEmbedding.web:main"
```

### 4.2 模块引用关系

```
                     ┌─────────────────────────────┐
                     │          core.py             │
                     │  ┌───────────────────────┐   │
                     │  │ CoordPoint (数据类)    │   │
                     │  │ DownloadResult (数据类)│   │
                     │  │ init_gee()            │   │
                     │  │ parse_coords()        │   │
                     │  │ _get_utm_epsg()       │   │
                     │  │ _create_square_roi()  │   │
                     │  │ build_image()         │   │
                     │  │ download_image()      │   │
                     │  │ download_single_point()│  │
                     │  │ setup_logging()       │   │
                     │  │ write_error_csv()     │   │
                     │  │ list_dir_contents()   │   │
                     │  └───────────────────────┘   │
                     └──────┬──────────┬────────────┘
                            │          │
                ┌───────────▼─┐    ┌───▼────────────┐
                │  web.py     │    │   cli.py        │
                │ NiceGUI 界面│    │（已弃用，代码参考）│
                │ from core   │    │ from core       │
                │ 显式命名导入 │    │ 显式命名导入     │
                └──────────────┘    └────────────────┘
                            │          │
                            └────┬─────┘
                                 │
                      ┌──────────▼───────────┐
                      │  GEE getDownloadURL   │
                      │  + requests HTTP GET  │
                      └──────────────────────┘
```

架构要点：

- **core.py 是 WebUI 共享的核心模块**，所有 GEE 交互、坐标解析、影像构建、下载执行逻辑都在 core 中。
- web.py 对 core 采用**显式命名导入**（web.py:17-24），非 `from core import *`。
- SE 与 DynamicWorld 是两个**独立模块，架构镜像但不共享代码**（SE 并非 import DW），各自拥有完整的 core/cli/web 三层。

### 4.3 core.py — 核心模块

#### 数据类

**`CoordPoint`** — 单个坐标点
| 字段 | 类型 | 说明 |
|------|------|------|
| `lon` | float | 经度 [-180, 180] |
| `lat` | float | 纬度 [-90, 90] |
| `name` | str | 点位名称，未提供时自动生成 `"lon,lat"` |

**`DownloadResult`** — 单点下载结果
| 字段 | 类型 | 说明 |
|------|------|------|
| `point` | CoordPoint | 原始坐标点 |
| `success` | bool | 是否成功 |
| `filepath` | str\|None | 成功时的文件路径 |
| `size_mb` | float | 文件大小 (MB) |
| `elapsed_sec` | float | 耗时 (秒) |
| `error` | str\|None | 失败时的错误信息 |

#### 主要函数（位置索引）

| 函数 | 位置 | 作用 |
|------|------|------|
| `init_gee(project_id)` | core.py:54 | 执行 `ee.Authenticate()` + `ee.Initialize(project=...)`，失败时打印引导信息并退出 |
| `parse_coords(input_str)` | core.py:79 | 自动识别坐标输入：存在文件则按 CSV 解析，否则按分号分隔字符串解析；越界坐标跳过并警告 |
| `_get_utm_epsg(lon, lat)` | core.py:112 | 根据经纬度返回 UTM 投影 EPSG 码（北半球 32601–32660 / 南半球 32701–32760，极地回退 4326） |
| `_create_square_roi(lon, lat, scale, target_pixels)` | core.py:186 | 在 UTM 投影中构造精确 N×N 正方形 ROI，返回 `(wgs84_rect, utm_rect)` 元组 |
| `create_roi(lon, lat, buffer_m)` | core.py:240 | 用 `point.buffer()` 构造以坐标点为中心的圆形 ROI（用于 filterBounds / clip） |
| `build_image(roi, year, years, bands, cross_year, scale)` | core.py:293 | 从数据集中筛选、合成、裁剪影像，返回 `ee.Image` 或 `None` |
| `_l2_normalize(image)` | core.py:257 | 逐像素 L2 归一化（仅 `mean` 合成后调用），恢复单位向量 |
| `_check_size_limit(roi, scale)` | core.py:271 | 估算下载像素数，超过 131,072 像素（约 32MB）时打印警告 |
| `download_image(image, output_dir, name, scale, crs, fmt, region)` | core.py:394 | 通过 `getDownloadURL()` 下载到本地，指数退避重试（1s→2s→4s，最多 3 次） |
| `download_single_point(point, output_dir, params)` | core.py:460 | **顶层流水线**：ROI → 影像构建 → 下载。WebUI 与已弃用的 CLI 共享，内部捕获所有异常、从不抛出 |
| `_convert_npy_to_npz(npy_filepath)` | core.py:374 | NPY 下载后自动生成 `.npz` 压缩副本（保留原 .npy） |
| `setup_logging(output_dir)` | core.py:540 | 配置日志：控制台 + `download.log` 双写 |
| `write_error_csv(output_dir, errors)` | core.py:572 | 失败项写入 `download_errors.csv`（仅失败时创建） |
| `list_dir_contents(directory)` | core.py:590 | 浏览目录：目录在前、文件在后，文件限 `.tif` / `.zip` / `.npy` |
| `se_tif_to_preview_png(filepath, max_size, band_index)` | core.py:649 | 将 GeoTIFF 指定波段渲染为灰度 PNG 预览图（[-1,1] → 0–255） |
| `SE_BAND_NAMES` | core.py:646 | 常量 `("A00" ... "A63")`，64 个波段名 |

### 4.4 web.py — WebUI 入口

基于 [NiceGUI](https://nicegui.io/) 构建（FastAPI + Vue.js 的 Python Web UI 框架）。

| 函数 | 位置 | 作用 |
|------|------|------|
| `check_gee_auth()` | web.py:54 | 检测 GEE 认证状态（不强制认证，仅 `ee.Initialize()` 探测） |
| `_preview_npy(filepath)` | web.py:27 | 读取 .npy 返回形状 / dtype / 统计摘要 HTML |
| `build_params(...)` | web.py:64 | 将 WebUI 表单值组装为 `download_single_point` 参数字典 |
| `create_ui()` | web.py:89 | 定义页面结构（`@ui.page("/")` 五个卡片） |
| `main()` | web.py:493 | 启动服务器：host `127.0.0.1`，**port 8001**，`storage_secret="se-downloader-2026"`（cookie 加密密钥，web.py:497） |

### 4.5 cli.py — 命令行入口（已弃用）

| 函数 | 位置 | 作用 |
|------|------|------|
| `build_parser()` | cli.py:23 | 用 `argparse` 定义全部命令行参数（已弃用） |
| `cmd_list(output_dir)` | cli.py:63 | 列出输出目录中已下载文件（已弃用） |
| `cmd_download(args)` | cli.py:81 | 下载主流程（已弃用） |
| `main()` | cli.py:147 | 入口（已弃用） |

### 4.6 测试文件

| 文件 | 行数 | 覆盖范围 |
|------|------|---------|
| `tests/test_se_core.py` | 832 | core 单元测试：坐标解析、UTM 计算、ROI 构造、影像构建、L2 归一化、下载、日志、目录浏览、预览图生成等 |
| `tests/test_se_cli.py` | 153 | cli 测试（已弃用入口的回归测试） |
| `tests/test_se_web.py` | 164 | web 测试：`check_gee_auth`（3 个）+ `build_params`（6 个），共 9 个，均为纯函数/状态检测，不涉及页面结构与预览逻辑 |

---

## 5. 工作流程

### 5.1 整体流水线

WebUI 触发下载时的核心流程：

```
① 初始化 GEE           ② 解析坐标            ③ 逐点处理循环          ④ 汇总与错误处理
ee.Authenticate()      CSV 文件 或           for point in points:    成功/失败计数
ee.Initialize(project) "lon,lat;lon,lat"       download_single_point  总大小/总耗时
                       字符串                          │           失败 → download_errors.csv
                  （越界/格式错误自动跳过）      download.log 全程记录
```

（WebUI 通过 `await run.io_bound(...)` 异步逐点执行；进度条 + 逐点通知展示进度。）

### 5.2 单点下载详细流程

`download_single_point(point, output_dir, params)` 是下载流水线的顶层函数（WebUI 与已弃用的 CLI 共用），完整流水线：

```
① 计算 UTM 投影
   crs = params["crs"] 或 _get_utm_epsg(lon, lat)

② 构造双 ROI（_create_square_roi）
   wgs84_rect  ← 用于 build_image 的 filterBounds / clip
   utm_rect    ← 用于 getDownloadURL 的 region（精确 N×N 像素）

③ 构造缓冲圆（create_roi，buffer 默认 640m）
   roi = point.buffer(640)     ← 实际参与 filterBounds/clip 的区域

④ 构建影像（build_image）
   filterBounds → 按年份 calendarRange 过滤 → 波段选择 → 跨年合成 → clip

⑤ 下载（download_image）
   getDownloadURL({scale, crs, format, region, filePerBand: False})
   → requests.get 下载 → NPY 格式额外生成 .npz

⑥ 返回 DownloadResult（成功含文件路径/大小/耗时；失败含错误信息）
```

> 注意两个 ROI 的分工：`utm_rect`（正方形）决定**下载像素范围**，保证输出严格 N×N；`roi`（圆形 buffer）决定**影像有效数据范围**，因此下载的 tif 是圆形有效区、外部为 NoData。

### 5.3 UTM 投影与精确正方形 ROI

**为什么用 UTM**：EPSG:4326（WGS84 度）中 scale≈0.00009°/px，且 cos(lat) 使经度方向拉长；UTM 是米制投影，scale=10 严格对应 10m/px。

**精确 N×N 的实现（关键）**：GEE 对 region 取 bounding box 后，像素网格起点对齐到 scale 的整数倍。若 region 四个角点本身已是 scale 整数倍，GEE 无需扩展 → 像素数精确等于 target_pixels：

```python
half = (target_pixels * scale) / 2.0          # 半边长（米），如 128×128@10m → 640m
nw_x = floor((cx - half) / scale) * scale     # NW 角点向下对齐到 10m 网格
nw_y = ceil((cy + half) / scale) * scale      # NW 角点向上对齐到 10m 网格
se_x = nw_x + target_pixels * scale
se_y = nw_y - target_pixels * scale
utm_rect = ee.Geometry.Rectangle([nw_x, se_y, se_x, nw_y], proj=utm_crs, evenOdd=False)
wgs84_rect = utm_rect.transform("EPSG:4326", 1)
```

### 5.4 跨年合成与 L2 归一化

`build_image` 对每个目标年份取第一景影像，再按策略合成：

| 策略 | 实现 | L2 归一化 | 适用场景 |
|------|------|-----------|---------|
| `first` | `multi_year.first()` | 否 | 快速预览 |
| `mean` | `multi_year.mean()` + `_l2_normalize()` | **是** | **推荐**，多年信息融合 |
| `median` | `multi_year.median()` | 否 | 抗异常年份 |

**L2 归一化原理**：多个单位向量的均值不再是单位向量，`mean` 合成后需逐像素除以 L2 范数恢复单位长度：

```python
norm = image.pow(2).reduce(ee.Reducer.sum()).sqrt()
return image.divide(norm).where(norm.eq(0), image)   # 零向量保护，避免 NaN
```

### 5.5 下载执行与重试机制

```python
params = {
    "scale": scale,        # 分辨率（米/像素）
    "crs": crs,            # 输出 CRS（默认自动 UTM）
    "format": fmt,         # GEO_TIFF / ZIPPED_GEO_TIFF / NPY
    "region": utm_rect,    # UTM 原生正方形矩形
    "filePerBand": False,  # 固定 False：64 波段单一文件
}
url = image.getDownloadURL(params)
resp = requests.get(url, timeout=300)
```

- 网络错误或 HTTP 非 200 时**指数退避重试**：等待 1s → 2s → 4s，最多 3 次，全部失败抛 `RuntimeError`。
- **数据量限制**：GEE 单次下载 ≤ 32MB（约 131,072 像素）。`_check_size_limit` 按 `roi.area / scale²` 估算像素数，超出阈值打印警告（不强制中断）。
- NPY 格式下载完成后自动生成同名 `.npz` 压缩副本（保留原始 `.npy`）。

### 5.6 GEE API 调用链

```
ee.Authenticate()                                        OAuth2 浏览器授权
ee.Initialize(project=...)                               GCP 项目绑定
ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")   加载数据集
  .filterBounds(roi)                                     空间过滤
  .filter(ee.Filter.calendarRange(y, y, "year"))         年度过滤（每年取第一景）
  .select([bands])                                       波段子集（all → 64 波段）
  .first() / .mean()(+L2) / .median()                    跨年合成
  .clip(roi)                                             裁剪（圆形缓冲）
─────────────────────────────────────────────────────────────────────
  .getDownloadURL({scale, crs, region, format, filePerBand: False})
      │   GEE 内部: region → CRS bounding box → 像素数计算（NW 角点对齐）→ 临时 URL
      ▼
requests.get(url, timeout=300)                            HTTP 下载（重试 3 次）
```

---

## 6. 输出文件结构

### 6.1 文件命名规则

`{波段}_{合成策略}_E{经度}_N{纬度}_{年份}.tif`

示例：

```
all_first_E108.95_N34.25_2024.tif
all_mean_E121.4025_N25.1947_2020_2021_2022_2023_2024.tif
A00_A01_A10_median_E116.4_N39.9_2022_2023.tif
```

### 6.2 Python 读取示例

```python
import rasterio
with rasterio.open("all_first_E108.95_N34.25_2024.tif") as src:
    data = src.read()  # shape: (64, height, width)
```

NPY 格式：`numpy.load()` → shape: `all` (64,N,N) float32 / 子集 `(K,N,N)` float32。

### 6.3 汇总输出

WebUI 下载完成后的汇总展示：

```
========== 下载汇总 ==========
  总计: 7 点
  成功: 7 点
  失败: 0 点
  下载总量: 21.0 MB
  总耗时: 45.3 s
================================
```

---

## 7. 常见问题（FAQ）

**Q1: "Caller does not have required permission"**
Project ID 未启用 Earth Engine API。在 Cloud Console 中启用。

**Q2: "Earth Engine client library not initialized"**
运行 `earthengine authenticate` 完成认证。

**Q3: 下载文件打不开**
- `GEO_TIFF` → QGIS 打开，或用 `rasterio` 读取
- `ZIPPED_GEO_TIFF` → 先解压
- `NPY` → `numpy.load()`（同目录已自动生成 `.npz` 压缩版）

**Q4: 区域过大报错**
GEE 单次限制 ≤ 32MB。在 WebUI 中增大「空间分辨率（米/像素）」或减小「输出尺寸（像素）」。

**Q5: "跳过越界坐标"**
坐标超出合法范围（lon ±180, lat ±90）。检查经纬度顺序，经度在前。

**Q6: "无可用影像"**
该区域在指定年份无数据。数据集覆盖 2017–2024，确认坐标在陆地区域。

**Q7: 下载的 tif 是圆形的**
这是 `buffer()` 产生的圆形 ROI，正常现象。像素值在圆形区域内有效，外部为 NoData（下载像素范围是精确正方形，但有效数据区是圆形）。

**Q8: 为什么 SE 只能做灰度预览？**
Satellite Embedding 是 64 维向量，每个波段值域 [-1,1]，无分类语义。WebUI 支持单波段灰度预览（黑白灰度映射），可切换 A00–A63 任意波段查看。

**Q9: mean 合成的 L2 归一化是什么？**
多个单位向量的均值不再是单位向量。`mean` 合成后自动逐像素做 L2 归一化（`v / ||v||`），恢复单位向量性质。`first` 和 `median` 不改变向量方向，无需归一化。

**Q10: 和 Dynamic World 下载器有什么区别？**

| | Dynamic World | Satellite Embedding |
|------|------|------|
| 波段 | 1 或 9 | 64（整体使用） |
| 时间 | 逐景（双周） | 年度合成 |
| 年份选择 | 起始/结束日期 | 单年份/多年份 |
| 合成方式 | first/mosaic/mode/mean/median/collection | first/mean/median |
| WebUI 端口 | 8000 | 8001 |
| 预览功能 | 有（label 分类图） | 有（单波段灰度预览，切换 A00–A63） |
| 逐景下载 | 支持（collection 模式） | 不支持 |
| 每波段单独文件 | 可配置 | 固定单文件输出 |

---

## 8. 附录

### 8.1 波段与合成方式

**波段选择**：

| 参数值 | 说明 | 用途 |
|--------|------|------|
| `all` | 全部 64 波段（A00–A63） | 完整嵌入向量，**推荐** |
| `A00,A01,A10,A11,…` | 指定波段逗号列表 | 仅需部分维度时使用 |

**跨年合成策略**：

| 策略 | 说明 | L2 归一化 | 推荐场景 |
|------|------|-----------|---------|
| `first` | 取第一个年份的影像 | 不归一化 | 快速预览 |
| `mean` | 多年份取均值 | **自动 L2 重归一化** | **推荐**，多年信息融合 |
| `median` | 多年份取中位数 | 不归一化 | 抗异常年份 |

> **L2 重归一化说明**：多个单位向量的均值通常不再是单位向量。`mean` 合成后自动逐像素除以 L2 范数，确保输出仍为单位向量；零向量（极罕见）不做除法以避免 NaN。

**输出尺寸与数据量**：输出范围由「输出尺寸（像素）」与「空间分辨率（米/像素）」决定。
GEE 单次下载限制 ≤ 32MB（约 131,072 像素）：

| 输出尺寸 @ 分辨率 | 下载范围 | 估算大小（64 波段） |
|------|-------------|--------------------------------|
| 64 × 64 @ 10m | 640m × 640m | ~0.5 MB |
| 128 × 128 @ 10m（默认） | 1280m × 1280m | ~2 MB |
| 256 × 256 @ 10m | 2560m × 2560m | ~8 MB |
| 512 × 512 @ 10m | 5120m × 5120m | ~32 MB ⚠️ 接近上限 |

> 超过约 131,072 像素时会打印数据量警告，提醒减小输出尺寸或增大分辨率，但不会强制中断。

### 8.2 坐标参考系 (CRS)

默认根据坐标自动选择 UTM 投影（EPSG:32601–32660 北半球 / EPSG:32701–32760 南半球）。极地区域（纬度 > 84° 或 < -80°）回退到 `EPSG:4326`。

| EPSG 代码 | 名称 | 适用区域 |
|-----------|------|---------|
| `EPSG:326XX` | UTM 北半球 | 北纬 0°–84°（默认） |
| `EPSG:327XX` | UTM 南半球 | 南纬 0°–80°（默认） |
| `EPSG:4326` | WGS84 | 全球（极地区域回退） |
| `EPSG:3857` | Web Mercator | Web 地图 |
| `EPSG:4490` | CGCS2000 | 中国大陆 |

> 原始数据为本地 UTM 投影，GEE 下载时自动重投影到指定 CRS。

### 8.3 已知问题

> 本节记录代码中已发现但**尚未修复**的问题，便于使用者规避。

- **web.py 表单恢复引用未定义的 `buffer_input`**：`web.py` 中恢复上次输入时存在 `if mem.get("buffer"): buffer_input.set_value(...)`（web.py:259-260），但页面并未创建 `buffer_input` 控件（SE WebUI 本身没有 buffer 参数）。若浏览器 cookie 中残留 `buffer` 键（旧版本表单保存过），页面加载时会抛 `NameError`，导致 WebUI 无法打开。规避方式：清除该站点的 cookie（或按 F12 删除 `buffer` cookie）后刷新。
- 与 DynamicWorld 模块的已知问题同源（DW 见其教程[附录 8.3](#83-已知问题)）。

### 8.4 与 DynamicWorld 模块的关系

- SatelliteEmbedding 与 DynamicWorld 是**两个独立模块**：架构镜像（都是 core/cli/web 三层），但**不共享代码**——SE 并不 `import DynamicWorld`；
- 两者共享同一份 `pyproject.toml` 依赖，各自注册独立 WebUI 入口：`se-web` 与 `dw-web`；
- 数据集不同：SE = `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`（年度 64 维嵌入向量），DW = `GOOGLE/DYNAMICWORLD/V1`（逐日分类）；
- 功能差异：SE 为 64 波段单文件输出、按年份/多年份合成（单年份/多年份控件）、mean 合成自动 L2 归一化；DW 支持 label/probs 波段、collection 逐景下载、每波段单独文件。
- 差异速查表见[第 7 节 Q10](#q10-和-dynamic-world-下载器有什么区别)。
- DW 的细节参见 `DynamicWorld/使用指南.md` 与仓库架构文档 `docs/2026-07-29-dw-se-architecture-guide.md`。
