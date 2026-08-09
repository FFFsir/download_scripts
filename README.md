# download_scripts — 遥感数据批量下载工具集

基于 **Google Earth Engine (GEE)** 的遥感数据批量下载工具，包含两个独立模块：

| 模块 | 数据集 | 内容 |
|------|--------|------|
| **DynamicWorld** | `GOOGLE/DYNAMICWORLD/V1` | 逐日地物分类影像（label 硬分类 0–8 / probs 概率 9 类） |
| **SatelliteEmbedding** | `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` | 年度 64 维遥感嵌入向量（A00–A63） |

两个模块架构镜像（core / cli / web 三层），相互独立、不共享代码；仅通过 **WebUI** 提供使用入口。

> ⚠️ **CLI 已弃用**：`dw-cli` / `se-cli` 命令行入口不再作为使用方式，统一通过
> **WebUI** 使用（DW 下载 `:8000`、SE 下载 `:8001`）。`cli.py` 文件保留仅作代码参考。

---

## 📚 文档导航

> **使用方法以以下两份教程为准**，分别覆盖项目结构分析、工作流程、WebUI 操作、输出文件结构与常见问题：

- **[《DynamicWorld 下载教程》](./docs/DynamicWorld_download教程.md)** —— DW 地物分类数据下载
- **[《SatelliteEmbedding 下载教程》](./docs/SatelliteEmbedding_download教程.md)** —— SE 遥感嵌入向量下载

深度技术细节（像素对齐原理、GEE API 调用链、UTM 投影设计）见 [《DW/SE 架构指南》](./docs/2026-07-29-dw-se-architecture-guide.md)。

---

## 模块速览

| 特性 | DynamicWorld | SatelliteEmbedding |
|------|--------------|--------------------|
| 波段 | `label`(1) / `probs`(9) / `all`(10) | 64（`A00`–`A63`）整体使用 |
| 时间维度 | 2016 年起逐日 | 2017–2024 年度合成 |
| 合成策略 | first / mosaic / mode / mean / median / collection | first / mean / median（mean 自动 L2 归一化） |
| 尺寸控制（WebUI） | 「输出尺寸（像素）」+「分辨率（米/像素）」，默认 128 / 10；**无缓冲半径参数** | 同左，默认 128 / 10 |
| WebUI 端口 | 8000 | 8001 |
| WebUI 入口 | `dw-web` | `se-web` |

---

## 环境要求

- **Python ≥ 3.12.12**（`.python-version` 锁定）
- **[uv](https://docs.astral.sh/uv/)**：依赖与运行管理
- 依赖（`pyproject.toml`）：`earthengine-api`、`nicegui`、`pillow`、`rasterio`、`requests`
  （rasterio + numpy 提供文件统计与预览，缺失时自动降级）；测试依赖 `pytest` 在 dev 组

```bash
# 安装依赖
uv sync
```

### GEE 认证（首次使用，仅需一次）

```bash
earthengine authenticate
```

浏览器会弹出 Google 登录页面，按提示授权即可。需先获取 **Google Cloud Project ID**
（Cloud Console 创建项目并启用 Earth Engine API），详见各教程的对应章节。

---

## 快速上手

```bash
# 启动 DW WebUI → http://127.0.0.1:8000（下载地物分类图）
uv run dw-web

# 启动 SE WebUI → http://127.0.0.1:8001（下载年度嵌入向量）
uv run se-web
```

完整操作步骤见上方教程。

---

## 目录结构

```
download_scripts/
├── DynamicWorld/            # DW 模块（core / cli(已弃用) / web）
├── SatelliteEmbedding/      # SE 模块（core / cli(已弃用) / web）
├── docs/                    # 教程与架构文档
│   ├── DynamicWorld_download教程.md
│   ├── SatelliteEmbedding_download教程.md
│   └── 2026-07-29-dw-se-architecture-guide.md
├── tests/                   # 单元测试（DW 与 SE 各自 core/cli/web 测试）
├── output/                  # 默认输出目录
├── pyproject.toml           # 依赖与入口脚本注册
└── uv.lock
```

---

## 测试

```bash
uv run pytest
```

- tests/ 下 6 个测试文件：`test_core.py` / `test_cli.py` / `test_web.py`（DW），
  `test_se_core.py` / `test_se_cli.py` / `test_se_web.py`（SE）。
- 所有 GEE / 网络调用均被 mock 替换，无需真实认证与网络。

---

## 输出说明

- 默认输出目录 `./output`。
- **合成模式**：单点单文件输出；DW 默认开启「每波段单独文件」（GEO_TIFF 格式时每波段一个独立文件）。
- **collection 模式（仅 DW）**：按点位子目录逐景输出，每景文件名追加 `_{YYYYMMDD_HHMMSS}` 时间戳。
- **文件名格式**：
  - DW：`{波段}_{合成}_E{经度}_N{纬度}_{起始日期}_{结束日期}.tif`
    （如 `label_mode_E108.95_N34.25_2024-01-01_2024-12-31.tif`）；
  - SE：`{波段}_{合成}_E{经度}_N{纬度}_{年份列表}.tif`
    （如 `all_mean_E121.4025_N25.1947_2020_2021_2022_2023_2024.tif`）。
- 支持格式：`GEO_TIFF` / `ZIPPED_GEO_TIFF` / `NPY`（扩展名随格式为 `.tif` / `.zip` / `.npy`；
  SE 的 NPY 下载后自动生成同名 `.npz` 压缩副本）。

---

## 版本说明

本 README 为 2026-08-09 重写的项目总览入口（按 8 节骨架与 evaluation_scripts 侧 README 统一排版），
替代旧版总览文档。详细使用说明一律以 [教程文档](#文档导航) 为准。

**后续变更（同日期）**：CLI 已弃用，使用方式统一为 WebUI（详见各模块教程第 3 章）。
