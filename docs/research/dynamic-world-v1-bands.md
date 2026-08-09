# Dynamic World V1 数据集调研报告

## 1. 数据集概述

| 属性 | 说明 |
|------|------|
| 全称 | Dynamic World V1 |
| 来源 | Google Earth Engine（数据集 ID: `GOOGLE/DYNAMICWORLD/V1`） |
| 分辨率 | 10m/像素 |
| 时间范围 | 2015-06-27 至今（近实时更新） |
| 数据类型 | 单波段 `label`（地物分类 0-8）+ 9 个 `probs` 波段（各类别概率） |
| 影像格式 | GeoTIFF（单波段为 LZW 压缩） |

## 2. 可用波段

| 编号 | 波段名 | 类型 | 说明 |
|------|--------|------|------|
| 1 | `label` | Byte (0-8) | 预测的地物类别标签（众数合成） |
| 2 | `water` | Float (0-1) | 水体概率（probs 波段 1/9） |
| 3 | `trees` | Float (0-1) | 树木概率（probs 波段 2/9） |
| 4 | `grass` | Float (0-1) | 草地概率（probs 波段 3/9） |
| 5 | `flooded_vegetation` | Float (0-1) | 淹水植被概率（probs 波段 4/9） |
| 6 | `crops` | Float (0-1) | 作物概率（probs 波段 5/9） |
| 7 | `shrub_and_scrub` | Float (0-1) | 灌丛概率（probs 波段 6/9） |
| 8 | `built` | Float (0-1) | 建筑概率（probs 波段 7/9） |
| 9 | `bare` | Float (0-1) | 裸地概率（probs 波段 8/9） |
| 10 | `snow_and_ice` | Float (0-1) | 冰雪概率（probs 波段 9/9） |

共 10 个波段：1 个离散类别波段 (`label`) + 9 个连续概率波段 (`probs`)。

## 3. 地物类别与颜色映射

| 值 | 类别 | 颜色 | Hex |
|----|------|------|-----|
| 0 | 水体 | <span style="display:inline-block;width:16px;height:16px;background:#419BDF;"></span> | `#419BDF` |
| 1 | 树木 | <span style="display:inline-block;width:16px;height:16px;background:#397D49;"></span> | `#397D49` |
| 2 | 草地 | <span style="display:inline-block;width:16px;height:16px;background:#88B053;"></span> | `#88B053` |
| 3 | 淹水植被 | <span style="display:inline-block;width:16px;height:16px;background:#7A87C6;"></span> | `#7A87C6` |
| 4 | 作物 | <span style="display:inline-block;width:16px;height:16px;background:#E49635;"></span> | `#E49635` |
| 5 | 灌丛 | <span style="display:inline-block;width:16px;height:16px;background:#DFC35A;"></span> | `#DFC35A` |
| 6 | 建筑 | <span style="display:inline-block;width:16px;height:16px;background:#C4281B;"></span> | `#C4281B` |
| 7 | 裸地 | <span style="display:inline-block;width:16px;height:16px;background:#A59B8F;"></span> | `#A59B8F` |
| 8 | 冰雪 | <span style="display:inline-block;width:16px;height:16px;background:#B39FE1;"></span> | `#B39FE1` |

颜色来源于 Dynamic World 官方 JS 可视化代码（`DW_COLORS`），RGB 值已在代码中定义。

## 4. 结论

1. Dynamic World V1 数据集不直接提供 RGB 合成图像，仅提供分类标签和各类别概率波段。
2. 如需可视化，需将 `label` 波段按上表颜色映射渲染为 RGB 图像。
3. 如需真彩色影像，应使用 Sentinel-2 L2A（`COPERNICUS/S2_SR_HARMONIZED`）或其他光学影像数据集。
