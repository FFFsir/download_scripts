# DynamicWorld / SatelliteEmbedding 下载参数逻辑与 GEE API 分析报告

> 日期: 2026-07-29
> 问题: 设定 target_pixels=128, scale=10, 实际下载的 GeoTIFF 为 129×129 而非 128×128

---

## 1. 当前下载参数链路

### 1.1 整体调用链

```
WebUI / CLI
  └→ download_single_point(point, output_dir, params)
       ├→ _create_square_roi(lon, lat, scale, target_pixels)  ← 构造 region
       ├→ create_roi(lon, lat, buffer_m)                       ← 构造 roi (圆形)
       ├→ build_image(roi, ...)                                ← filterBounds + clip
       └→ download_image(image, ..., scale, crs, fmt, region)  ← getDownloadURL
            └→ image.getDownloadURL({scale, crs, format, filePerBand, region})
                 └→ requests.get(url) → 写入本地 .tif/.npy
```

### 1.2 各函数职责

| 函数 | 职责 | 传给下一层 |
|------|------|-----------|
| `_create_square_roi()` | 在 UTM 中计算 N×N 正方形，transform 回 WGS84 | `region` — getDownloadURL 的输出裁剪区域 |
| `create_roi()` | point.buffer(buffer_m) → 圆形 | `roi` — build_image 的 filterBounds + clip |
| `build_image()` | filterBounds(roi) → 合成 → clip(roi) | `image` |
| `download_image()` | getDownloadURL + HTTP 下载 | 本地 .tif/.npy 文件 |

### 1.3 传给 GEE getDownloadURL 的实际参数

```python
{
    "scale": 10,
    "crs": "EPSG:32651",    # 自动 UTM EPSG
    "format": "GEO_TIFF",
    "filePerBand": False,
    "region": <EPSG:4326 Rectangle>  # ← 已经从 UTM transform 回 WGS84
}
```

---

## 2. GEE `getDownloadURL` 核心行为

### 2.1 `region` 参数的像素网格语义

根据 GEE 官方文档 `ee.Image.getDownloadURL`:

> **region** (Geometry, optional): The output will be clipped to the region's **bounding box**, and **the pixel grid will be arranged so that the region's bounding box defines the pixel grid extent and alignment in the output CRS**.

这意味着:
1. GEE 对 region **取外接矩形 (bounding box)**
2. 像素网格的**起点对齐到 bounding box 的左上角**
3. 像素数 = `ceil(bbox_size_in_crs_units / scale)` — **向上取整**

### 2.2 `scale` + `crs` 的参数语义

> **scale** (Float, optional): Scale in **meters per pixel** when crs is a projected coordinate system. When crs is 'EPSG:4326', scale is in **degrees per pixel**.

> **crs** (String, optional): The coordinate reference system for the output image. Defaults to the projection of the image's first band. **The pixel grid is constructed in this CRS**.

---

## 3. 129×129 的根因分析

### 3.1 关键代码路径

```python
def _create_square_roi(lon, lat, scale=10, target_pixels=128):
    half = (128 * 10) / 2.0 = 640.0  # 米
    crs = "EPSG:32651"
    
    # Step 1: 中心点投影到 UTM → 得到 UTM 坐标 (cx, cy)
    utm_point = ee.Geometry.Point([lon, lat]).transform("EPSG:32651", 1)
    cx, cy = utm_point.coordinates()  # 如 (350000, 2780000)
    
    # Step 2: 在 UTM 中构造 1280m × 1280m 的精确正方形
    rect_utm = ee.Geometry.Rectangle(
        [cx-640, cy-640, cx+640, cy+640],  # 1280 × 1280 米
        proj="EPSG:32651"
    )
    
    # Step 3: ❌ 变换回 WGS84
    return rect_utm.transform("EPSG:4326", 1)
```

### 3.2 双重投影导致的 1 像素膨胀

```
UTM 坐标系 (米)                  WGS84 (度)                     GEE 输出 (UTM)
┌──────────────────────┐       ╭──────────────────╮          ┌──────────────────────────┐
│ (350000, 2780000)    │ trans │ 弯曲四边形        │  GEE     │ bounding box 在 UTM 中:   │
│ 1280m × 1280m       │ ────→ │ (非严格矩形)      │ ──────→ │ ≈ 1281m × 1281m           │
│ 精确 128×128 像素    │       ╰──────────────────╯          │ ceil(1281/10) = 129 像素   │
└──────────────────────┘                                     └──────────────────────────┘
```

**第一步变换 (WGS84→UTM) 保持精度**: 中心点投影到 UTM，坐标精确到亚米级。构造的 Rectangle 在 UTM 中是完美的 1280m×1280m。

**第二步变换 (UTM→WGS84) 产生畸变**: UTM 矩形通过 `.transform("EPSG:4326", 1)` 变换到 WGS84。UTM 是共形投影（保角不保距），矩形的四条边在 WGS84 中会发生微小弯曲。四个角点会在经纬度空间中形成一个**不再是矩形**的四边形。

**第三步 GEE 内部再投影回 UTM**: GEE 拿到 WGS84 下的弯曲四边形，取其 bounding box（在 WGS84 中），然后将这个 bounding box 重新投影到**输出 CRS (UTM)**。由于 UTM↔WGS84 不是线性变换，这个重投影过程使得 bounding box 在 UTM 中的宽度/高度**略大于原来的 1280m**。具体来说，重投影后的 bounding box 可能是 1280.5m 或 1281m。GEE 按 `ceil(bbox_size / scale)` 计算像素数 → **129 像素**。

### 3.3 误差的几何来源

在 EPSG:4326 中取 bounding box (min_lon, min_lat, max_lon, max_lat) 后，这四个角点再变换回 UTM:

```
WGS84 bounding box 角点 → UTM:
  (min_lon, min_lat) → UTM 坐标有微小偏移
  (max_lon, max_lat) → UTM 坐标有微小偏移
  两者在 UTM 中的差值 ≈ 1280 + ε (epsilon ≈ 0.5~1m)
```

这个 ε 来源于:
1. **共形投影的尺度因子变化**: UTM 在不同纬度的 scale factor 不同 (0.9996 到 1.0010)，WGS84 bounding box 的四个角可能落入不同的 scale factor 区域
2. **GEE 的 bounding box 算法**: GEE 的 `Geometry.bounds()` 在 WGS84 中计算后，可能引入额外的浮点精度损失

### 3.4 为什么之前 EPSG:4326 输出也会出错

之前的方案中，输出 CRS 是 EPSG:4326，但 scale=10 在 EPSG:4326 中是**度/像素**而非米/像素。GEE 内部换算: `10m ≈ 0.00008983°` (在赤道)。在纬度 25°N，经度方向的度/米因子是 `cos(25°) ≈ 0.906`，导致经度方向需要更多像素才能覆盖同样的地面距离 → 141×129。

---

## 4. 缺陷汇总

### 缺陷 A (CRITICAL): UTM→WGS84→UTM 双重投影导致 bounding box 膨胀

**_create_square_roi() 第 233 行的 `.transform("EPSG:4326", 1)` 是根本原因。**

UTM 中的精确正方形经过 WGS84 往返后不再精确。应该**直接保持 UTM 几何体**，不经过 WGS84 往返。

### 缺陷 B (IMPORTANT): image.clip(圆形) 与 region(正方形) 不一致

`build_image()` 调用 `image.clip(roi)` 使用**圆形** ROI，但 `download_image()` 的 `region` 参数使用**正方形** Rectangle。两者的边界不重合，clip 边缘附近的像素值不可预测（圆形外、正方形内的像素可能是 0 或 nodata）。

### 缺陷 C (IMPORTANT): buffer 参数残留

WebUI 已经移除了 buffer 输入，但 `download_single_point()` 仍然调用 `create_roi(point.lon, point.lat, params.get("buffer", 500))`。此时 buffer 默认 500m — 而 target_pixels=128, scale=10 要求的正方形边长是 1280m (half=640m)。500m 半径的圆形无法覆盖 1280m 的正方形区域。

### 缺陷 D (MINOR): try/except 静默回退

`_create_square_roi` 的 except 分支使用度数近似 (111320 m/°)，与 UTM 主路径的精度不一致。当 transform() 成功但几何体有精度问题时，用户无法察觉。

---

## 5. 正确的修复方案

### 5.1 核心思路: 全程保持 UTM 几何体

```
download_single_point():
  1. utm_crs = _get_utm_epsg(lon, lat)                     # EPSG:32651
  
  2. utm_rect = 在 UTM 中构造 1280m×1280m 的精确 Rectangle
     → proj=utm_crs, 不 transform
  
  3. wgs84_rect = utm_rect.transform("EPSG:4326", 1)
     → 仅用于 build_image 的 filterBounds (粗略筛选即可)
  
  4. build_image(wgs84_rect, ...)  # filterBounds + clip 用 WGS84
     → image
  
  5. download_image(image, region=utm_rect, crs=utm_crs)
     → region 在 UTM 中，crs 也是 UTM
     → GEE 在 UTM 中计算像素网格: 1280m / 10m = 128px
     → ✅ 严格 128×128
```

### 5.2 关键改动点

**`_create_square_roi()`**: 返回 `(wgs84_rect, utm_rect)` 两个几何体 — WGS84 用于 filterBounds/clip，UTM 用于 getDownloadURL 的 region。

**`build_image()`**: 第一个参数从 `roi`（圆形）改为 `wgs84_rect`（矩形），确保 clip 的区域和 download 的 region 一致。

**`download_image()`**: region 参数接收 UTM 坐标系下的 Rectangle，与 crs 参数一致。GEE 在 UTM 中做像素网格对齐 — scale=10 就是严格的 10m/像素。

### 5.3 备选: 使用 GEE 的 `dimensions` 参数

GEE `getDownloadURL` 支持 `dimensions` 参数:

```python
params = {
    "scale": 10,
    "crs": "EPSG:32651",
    "region": utm_rect,
    "dimensions": "128x128",   # ← 强制输出 128×128
}
```

但这引入了隐式重采样，不如方案 5.1 直观可控。

---

## 6. 总结

| 问题 | 根因 | 优先级 |
|------|------|--------|
| 129×129 | UTM rect → WGS84 transform → GEE bbox → 重投影膨胀 | CRITICAL |
| clip 区域与下载区域不一致 | roi (圆形) vs region (正方形) | IMPORTANT |
| buffer 参数残留在 core.py | WebUI 已移除但 core.py 未同步 | IMPORTANT |
| 静默回退掩盖精度问题 | except 度数近似无日志 | MINOR |

**推荐行动**: 按照 5.1 方案重构 — 保持 UTM 几何体不经过 WGS84 往返，直接传给 getDownloadURL 的 region 参数。
