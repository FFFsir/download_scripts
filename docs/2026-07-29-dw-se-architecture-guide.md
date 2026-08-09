# DynamicWorld / SatelliteEmbedding 下载脚本架构说明书

> 版本: 2026-07-29
> 总代码量: ~2900 行 Python，~163 tests
> 数据集: Dynamic World V1 / Satellite Embedding V1
> 平台: Google Earth Engine + NiceGUI

---

## 1. 项目结构总览

```
download_scripts/
├── DynamicWorld/                 # DW 数据集下载模块
│   ├── core.py                   # 核心逻辑 (840 行)
│   ├── cli.py                    # CLI 命令行入口 (158 行)
│   ├── web.py                    # NiceGUI WebUI (574 行)
│   └── 使用指南.md
│
├── SatelliteEmbedding/           # SE 数据集下载模块
│   ├── core.py                   # 核心逻辑 (700 行)
│   ├── cli.py                    # CLI 命令行入口 (158 行)
│   ├── web.py                    # NiceGUI WebUI (503 行)
│   └── 使用指南.md
│
└── tests/
    ├── test_core.py              # DW core tests (54 tests)
    ├── test_cli.py               # DW cli tests (11) → 含 build_params
    ├── test_web.py               # DW web tests (22)
    ├── test_se_core.py           # SE core tests (54)
    ├── test_se_cli.py            # SE cli tests (13)
    └── test_se_web.py            # SE web tests (9)
```

### 1.1 模块引用关系

```
                    ┌──────────────────────┐
                    │      core.py          │
                    │  ┌────────────────┐   │
                    │  │ CoordPoint      │   │
                    │  │ DownloadResult   │   │
                    │  │ init_gee()       │   │
                    │  │ parse_coords()   │   │
                    │  │ _get_utm_epsg()  │   │
                    │  │ _create_square_roi()│  │
                    │  │ build_image()    │   │
                    │  │ download_image() │   │
                    │  │ download_single  │   │
                    │  │   _point()       │   │
                    │  │ setup_logging()  │   │
                    │  └────────────────┘   │
                    └──────┬───────┬───────┘
                           │       │
              ┌────────────▼─┐  ┌──▼──────────────┐
              │   cli.py      │  │    web.py        │
              │  argparse CLI │  │  NiceGUI WebUI   │
              │  from core    │  │  from core        │
              │  import *     │  │  import *         │
              └───────────────┘  └──────────────────┘
                           │       │
                           └───┬───┘
                               │
                    ┌──────────▼───────────┐
                    │  GEE getDownloadURL   │
                    │  + requests HTTP GET  │
                    └──────────────────────┘
```

DW 和 SE 是两个独立模块，架构镜像但**不共享代码**（SE 并非 import DW）。每个模块都有完整的 core/cli/web 三层。

---

## 2. core.py — 核心模块详解

core.py 是下载工具的核心，包含所有 GEE 交互、坐标解析、影像构建和下载执行逻辑。

### 2.1 数据类

**CoordPoint**: 单个坐标点
- `lon: float` — 经度 [-180, 180]
- `lat: float` — 纬度 [-90, 90]
- `name: str` — 点位名称

**DownloadResult**: 单点下载结果
- `point: CoordPoint` — 原始坐标
- `success: bool` — 是否成功
- `filepath: str|None` — 文件路径
- `size_mb: float` — 文件大小
- `elapsed_sec: float` — 耗时
- `error: str|None` — 错误信息

### 2.2 `init_gee(project_id)` — GEE 认证与初始化

```python
ee.Authenticate()              # OAuth2 浏览器授权
ee.Initialize(project=...)     # 绑定 GCP 项目
```

调用 Earth Engine Python SDK 的认证/初始化。首次需浏览器交互，后续使用缓存凭据。

### 2.3 `parse_coords(input_str)` — 坐标解析

自动识别 CSV 文件路径 vs 命令行字符串:
- **CSV**: `csv.DictReader`，需要 `lon,lat` 列，可选 `name`
- **字符串**: 分号分隔 `"lon1,lat1;lon2,lat2"`

验证: lon ∈ [-180,180], lat ∈ [-90,90]，越界跳过+warning。

### 2.4 `_get_utm_epsg(lon, lat)` — UTM 投影计算

```python
zone = int((lon + 180) / 6) + 1       # UTM zone 1–60
北半球 → EPSG:32601–32660
南半球 → EPSG:32701–32760
极地 → EPSG:4326 fallback
```

**为什么需要**: EPSG:4326 (WGS84 度) 中 scale≈0.00009°/px，cos(lat) 使经度方向拉长。UTM 是米制投影坐标系，scale=10 → 严格 10m/px。

### 2.5 `_create_square_roi(lon, lat, scale, target_pixels)` — 精确正方形 ROI

```python
half = (target_pixels * scale) / 2.0       # e.g. 640m for 128×128@10m
utm_crs = _get_utm_epsg(lon, lat)

# 中心点 → UTM 米坐标
point = ee.Geometry.Point([lon, lat])
utm_pt = point.transform(utm_crs, 1)       # ee API: 坐标投影变换
cx, cy = utm_pt.coordinates().getInfo()    # UTM 米坐标

# NW 角点像素对齐 (关键!)
nw_x = floor((cx - half) / scale) * scale  # 向下取整到 10m 倍数
nw_y = ceil((cy + half) / scale) * scale   # 向上取整到 10m 倍数

# UTM 原生矩形
utm_rect = ee.Geometry.Rectangle(           # ee API: 在指定 CRS 中构造矩形
    [nw_x, nw_y - px * scale, nw_x + px * scale, nw_y],
    proj=utm_crs
)

# WGS84 版本 (仅用于 filterBounds)
wgs84_rect = utm_rect.transform("EPSG:4326", 1)  # ee API: 几何体重投影

return wgs84_rect, utm_rect
```

**像素对齐原理**: GEE 对 region 取 bounding box 后，像素网格起点对齐到 scale 整数倍。如果 region 的四个角点本身已经是 scale 整数倍 → GEE 不需要扩展 → 像素数精确 = target_pixels。

### 2.6 `build_image(roi, ...)` — 影像构建

#### DW 版
```python
collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
collection.filterBounds(roi).filterDate(start, end)
# 波段: label(类别0-8), probs(9概率波段), all
# 合成: first, mosaic, mode(众数), mean, median, collection(逐景)
image.clip(roi)
```

#### SE 版
```python
collection = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
collection.filterBounds(roi)
collection.filter(ee.Filter.calendarRange(y, y, "year"))  # 年份过滤
# 波段: all(64 波段 A00-A63) 或自定义子集
# 合成: first, mean(+ L2 重归一化), median
```

**GEE API 对应**:
- `ee.ImageCollection(id)` — 加载数据集
- `.filterBounds(geometry)` — 空间过滤 (GEE 空间索引)
- `.filterDate(start, end)` — 时间过滤 (DW 逐日数据)
- `.filter(ee.Filter.calendarRange(...))` — 属性过滤 (SE 年度数据)
- `.first()` / `.mean()` / `.median()` — reduce 操作
- `.clip(geometry)` — 像素掩膜裁剪

### 2.7 `_l2_normalize(image)` — L2 重归一化 (仅 SE)

```python
norm = image.pow(2).reduce(ee.Reducer.sum()).sqrt()  # 64 维 L2 范数
return image.divide(norm).where(norm.eq(0), image)    # 除零保护
```

均值合成的多个单位向量不再具有单位长度，需要重新归一化。

### 2.8 `download_image(...)` — 下载执行

```python
params = {
    "scale": scale,      # 10m/px in UTM
    "crs": crs,          # EPSG:326XX
    "format": fmt,       # GEO_TIFF / NPY
    "region": utm_rect,  # UTM 原生 Rectangle
}
url = image.getDownloadURL(params)   # ee API: 获取临时下载链接
requests.get(url, timeout=300)        # HTTP GET + 指数退避重试
```

**GEE getDownloadURL 核心参数**:

| 参数 | 含义 |
|------|------|
| `scale` | 像素分辨率。投影 CRS 中 = 米/像素 |
| `crs` | 输出坐标参考系，像素网格在此 CRS 中构造 |
| `region` | 输出范围。GEE 取 bounding box → 在输出 CRS 中计算像素数 |
| `format` | GEO_TIFF / ZIPPED_GEO_TIFF / NPY |

### 2.9 `download_single_point(point, output_dir, params)` — 顶层流水线

完整的单点下载流水线：
1. 计算 UTM EPSG 码
2. `_create_square_roi()` → `(wgs84_rect, utm_rect)`
3. `build_image(wgs84_rect)` → `image`
4. `download_image(image, region=utm_rect, crs=utm_crs)` → 本地文件

### 2.10 辅助函数

| 函数 | 功能 |
|------|------|
| `setup_logging(output_dir)` | 控制台 + download.log 双写 |
| `write_error_csv(output_dir, errors)` | 失败清单 → download_errors.csv |
| `list_dir_contents(dir)` | 目录 + 文件浏览 (WebUI 用) |
| `get_tif_stats(filepath)` | GeoTIFF 统计 (DW: 类别像素 / probs 数值) |
| `tif_to_preview_png(filepath)` | DW GeoTIFF → PNG 预览图 |
| `se_tif_to_preview_png(filepath)` | SE GeoTIFF → 灰度 PNG 预览 |

---

## 3. cli.py — CLI 模块详解

每个 CLI 模块包含三个函数:

### 3.1 `build_parser()` — 参数解析

使用 Python `argparse` 定义所有命令行参数。每个参数有 `default`、`help`、`choices` 等约束。

### 3.2 `cmd_download(args)` — 下载主流程

```
1. Argparse args → params dict
2. parse_coords() → list[CoordPoint]
3. for point in points:
     download_single_point(point, output_dir, params)
4. 汇总: 成功/失败计数, 总大小/耗时
5. write_error_csv() 如果存在失败
```

### 3.3 `main()` — 入口

```python
if args.list: return cmd_list()
return cmd_download()
```

---

## 4. web.py — WebUI 模块详解

### 4.1 框架基础

基于 [NiceGUI](https://nicegui.io/) 构建。NiceGUI 是 Python Web UI 框架，基于 FastAPI + Vue.js:

| 功能 | 对应 API |
|------|---------|
| 声明式 UI 组件 | `ui.input()`, `ui.button()`, `ui.card()` 等 |
| 异步 IO | `await run.io_bound(fn, *args)` — 防止阻塞 |
| 用户存储 | `app.storage.user` — 浏览器 cookie 持久化 |
| 通知 | `ui.notify(message)` |
| 弹窗 | `ui.dialog()` |
| 文件服务器 | `@app.get(path)` + `FileResponse` |

### 4.2 页面结构

```
┌─ 认证卡片 ──────────────────────────────┐
│  check_gee_auth() → 状态 + 手动认证按钮   │
├─ 坐标卡片 ──────────────────────────────┤
│  文本框 + CSV 上传                        │
├─ 参数卡片 ──────────────────────────────┤
│  输出尺寸(target_pixels) + 分辨率(scale) │
│  波段 + 合成策略 + 格式 + CRS             │
│  数据集专属参数 (日期/年份等)              │
├─ 执行卡片 ──────────────────────────────┤
│  输出目录 + [开始下载]                     │
│  进度条 + 逐点通知                        │
├─ 文件卡片 ──────────────────────────────┤
│  [📂 上一层] [🔄 刷新]                    │
│  📁 子目录  (点击进入)                     │
│  📄 file.tif  [预览]                      │
│  📊 file.npy  [查看数据]                  │
└──────────────────────────────────────────┘
```

### 4.3 关键函数

| 函数 | 作用 |
|------|------|
| `check_gee_auth()` | 检测凭据状态 (不弹浏览器) |
| `build_params()` | 表单 → params dict |
| `on_download()` | 异步下载 + 进度条 + 通知 |
| `show_preview()` | TIFF 预览弹窗 (波段切换 + 统计) |
| `_preview_npy()` | NPY 数据预览 (形状 + dtype + min/max + 矩阵) |
| `refresh_file_list()` | 浏览目录 + 文件列表渲染 |

### 4.4 Cookie 持久化

`app.storage.user` 自动保存/恢复用户输入:
```python
# 保存
mem = app.storage.user
mem["project"] = project_id_input.value
mem["target_pixels"] = target_pixels_input.value

# 恢复 (页面刷新时)
if mem.get("target_pixels"):
    target_pixels_input.set_value(mem["target_pixels"])
```

---

## 5. 完整的 GEE API 调用链

```
ee.Authenticate()                           OAuth2 授权
ee.Initialize(project=...)                  GCP 项目绑定
ee.ImageCollection(catalog_id)              加载数据集
  .filterBounds(geometry)                  空间过滤
  .filterDate("2024-01-01", "2024-12-31")   时间过滤 (DW)
  OR .filter(ee.Filter.calendarRange(...))   年份过滤 (SE)
  .select([bands])                          波段子集
  .first() / .mean() / .median()           合成
  .clip(geometry)                           裁剪
───────────────────────────────────────────────────
  .getDownloadURL({scale, crs, region, format})
     │
     │  GEE 内部:
     │  1. region → output CRS bounding box
     │  2. bbox_size / scale = pixel count
     │  3. pixel origin floor/ceil to scale grid
     │  4. 临时下载 URL (有效期 ~1h)
     │
     ▼
requests.get(url, timeout=300)              HTTP 下载
```

### 5.1 GEE getDownloadURL 像素网格确定

```
输入: region(UTM Rectangle 1280m×1280m), crs(EPSG:32651), scale(10m/px)

GEE 内部:
1. region → output CRS bounding box
2. 如果 NW 角点在 10m 网格上:
     width  = 1280m  → ceil(1280/10) = 128 px ✓
     height = 1280m  → ceil(1280/10) = 128 px ✓
   如果 NW 角点有小数:
     width  = 1280.3m → ceil(1280.3/10) = 129 px ✗
```

**这就是 NW 像素对齐的关键**: 把 UTM Rectangle 的四个角精确对齐到 10m 整数倍网格。

---

## 6. NPY 数据格式

GEE `getDownloadURL(format="NPY")` 输出 channels-first (C order):

| 数据集 | NPY shape | dtype | 值域 |
|-------|----------|-------|------|
| DW label | `(128, 128)` | uint8 | 0–8 |
| DW probs | `(9, 128, 128)` | float32 | 0.0–1.0 |
| SE | `(64, 128, 128)` | float32 | -1.0–1.0 |

与 `rasterio.open().read()` 顺序一致: `(bands, rows, cols)`。

SE 下载 NPY 后自动生成 `.npz` 压缩副本。

---

## 7. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 输出投影 | UTM (自动) | EPSG:4326 的度/像素导致 cos(lat) 拉长 |
| 正方形 ROI | `_create_square_roi()` | UTM 米坐标构造 + NW 角点像素对齐 |
| 输出尺寸控制 | `target_pixels` 参数 | 直接指定 128×128，不需要 buffer 换算 |
| SE filePerBand | False | 64 波段嵌入向量需整体使用 |
| DW filePerBand | True (可配) | label/probs 可独立分析 |
| WebUI 框架 | NiceGUI | 已有代码基础 + 丰富的 UI 组件 |
