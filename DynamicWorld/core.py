"""Dynamic World V1 下载工具 -- 核心模块。

提供 GEE 认证、坐标解析、影像构建、下载执行、日志记录等共享功能。
CLI (cli.py) 和 WebUI (web.py) 均调用本模块的函数。
"""

import csv
import logging
import os
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime

import ee
import requests
from requests.exceptions import RequestException


@dataclass
class CoordPoint:
    """单个坐标点。

    Attributes:
        lon: 经度，范围 [-180, 180]。
        lat: 纬度，范围 [-90, 90]。
        name: 点位名称。若用户未提供，自动生成为 "lon,lat" 格式。
    """
    lon: float
    lat: float
    name: str


@dataclass
class DownloadResult:
    """单个点的下载结果。

    Attributes:
        point: 原始坐标点信息。
        success: 下载是否成功。
        filepath: 成功时保存的文件路径，失败时为 None。
        size_mb: 下载文件大小 (MB)，失败时为 0.0。
        elapsed_sec: 下载耗时 (秒)，失败时为 0.0。
        error: 失败时的错误信息，成功时为 None。
    """
    point: CoordPoint
    success: bool
    filepath: str | None = None
    size_mb: float = 0.0
    elapsed_sec: float = 0.0
    error: str | None = None


def init_gee(project_id: str) -> None:
    """执行 GEE 认证与初始化。

    调用 ee.Authenticate() 进行用户认证，
    然后调用 ee.Initialize(project=project_id) 初始化项目。

    Args:
        project_id: Google Cloud Project ID，需已启用 Earth Engine API。

    Raises:
        SystemExit: 当认证或初始化失败时，打印引导信息后退出。
    """
    try:
        ee.Authenticate()
        ee.Initialize(project=project_id)
    except ee.EEException as e:
        print(f"[错误] GEE 认证/初始化失败: {e}")
        print("请检查:")
        print("  1. 是否已安装 earthengine-api: uv add earthengine-api")
        print("  2. 是否已注册 Earth Engine: https://signup.earthengine.google.com")
        print("  3. project_id 是否正确且已启用 Earth Engine API")
        print(f"  4. 如需交互式认证，请先运行: earthengine authenticate")
        sys.exit(1)


def parse_coords(input_str: str) -> list[CoordPoint]:
    """解析坐标输入，自动识别 CSV 文件或坐标字符串。

    识别逻辑:
        1. 若 input_str 指向一个存在的文件 -> 按 CSV 解析。
           列名: lon, lat, name(可选)。无 name 列时自动生成 "lon,lat"。
        2. 否则 -> 视为分号分隔的坐标字符串 "lon1,lat1;lon2,lat2"。

    验证规则:
        - lon ∈ [-180, 180], lat ∈ [-90, 90]。
        - 无效坐标跳过并发出 warning。
        - 跳过以 # 开头的注释行和空行。

    Args:
        input_str: CSV 文件路径或分号分隔的坐标字符串。

    Returns:
        解析成功的 CoordPoint 列表。全部无效时返回空列表。
        不抛异常。
    """
    if os.path.isfile(input_str):
        return _parse_csv(input_str)
    return _parse_string(input_str)


def _parse_csv(filepath: str) -> list[CoordPoint]:
    """从 CSV 文件解析坐标点。"""
    points: list[CoordPoint] = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return points
        has_name = "name" in reader.fieldnames
        for row in reader:
            if not row or all(v.strip() == "" for v in row.values()):
                continue
            first_val = next(iter(row.values()), "").strip()
            if first_val.startswith("#"):
                continue
            try:
                lon = float(row["lon"].strip())
                lat = float(row["lat"].strip())
            except (ValueError, KeyError):
                logging.warning(f"跳过无效行（无法解析数值）: {row}")
                continue
            if not _validate_coord(lon, lat):
                continue
            name = row["name"].strip() if has_name and row.get("name", "").strip() else f"{lon},{lat}"
            points.append(CoordPoint(lon=lon, lat=lat, name=name))
    return points


def _parse_string(coord_str: str) -> list[CoordPoint]:
    """从分号分隔的坐标字符串解析坐标点。"""
    points: list[CoordPoint] = []
    parts = coord_str.strip().split(";")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        values = [v.strip() for v in part.split(",")]
        if len(values) < 2:
            logging.warning(f"跳过无效坐标格式: '{part}'")
            continue
        try:
            lon = float(values[0])
            lat = float(values[1])
        except ValueError:
            logging.warning(f"跳过无法解析的坐标: '{part}'")
            continue
        if not _validate_coord(lon, lat):
            continue
        points.append(CoordPoint(lon=lon, lat=lat, name=f"{lon},{lat}"))
    return points


def _validate_coord(lon: float, lat: float) -> bool:
    """验证坐标范围。"""
    if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
        logging.warning(f"跳过越界坐标: lon={lon}, lat={lat}")
        return False
    return True


def _get_utm_epsg(lon: float, lat: float) -> str:
    """根据经纬度返回 UTM 投影 EPSG 码。

    北半球: EPSG:32601–32660，南半球: EPSG:32701–32760。
    纬度 > 84° 或 < -80° 时超出 UTM 范围，回退到 EPSG:4326。

    Args:
        lon: 经度，-180 到 180。
        lat: 纬度，-90 到 90。

    Returns:
        UTM EPSG 码字符串，如 "EPSG:32650"。
    """
    if lat > 84 or lat < -80:
        return "EPSG:4326"
    zone = int((lon + 180) / 6) + 1
    zone = max(1, min(60, zone))
    if lat >= 0:
        return f"EPSG:326{zone:02d}"
    else:
        return f"EPSG:327{zone:02d}"


def _create_square_roi(
    lon: float, lat: float, scale: int = 10, target_pixels: int = 128,
) -> ee.Geometry:
    """在 UTM 投影中构造精确 N×N 正方形 ROI。

    不经过 WGS84 往返：直接在 UTM 坐标系中创建 Rectangle，
    同时提供 WGS84 版本用于 build_image 的 filterBounds/clip。

    Args:
        lon: 中心点经度。
        lat: 中心点纬度。
        scale: 空间分辨率，单位米/像素，默认 10。
        target_pixels: 目标正方形像素尺寸，默认 128。

    Returns:
        (wgs84_rect, utm_rect) 元组:
        - wgs84_rect: EPSG:4326 下的矩形，用于 build_image
        - utm_rect: UTM 投影下的矩形，用于 getDownloadURL 的 region
    """
    half = (target_pixels * scale) / 2.0  # 半边长 (米)
    utm_crs = _get_utm_epsg(lon, lat)

    # 中心点经纬度 → UTM 坐标 (米)
    point = ee.Geometry.Point([lon, lat])
    utm_point = point.transform(utm_crs, 1)
    utm_coords = ee.List(utm_point.coordinates())
    cx = ee.Number(utm_coords.get(0))
    cy = ee.Number(utm_coords.get(1))

    # NW 角点（地理惯例：左上角，y 向北增加）
    nw_x_raw = cx.subtract(half)
    nw_y_raw = cy.add(half)

    # 对齐到 scale 的整数倍（像素网格起点）
    nw_x = nw_x_raw.divide(scale).floor().multiply(scale)
    nw_y = nw_y_raw.divide(scale).ceil().multiply(scale)

    # SE 角点
    se_x = nw_x.add(target_pixels * scale)
    se_y = nw_y.subtract(target_pixels * scale)

    # UTM 投影下的矩形 — 传给 getDownloadURL 的 region
    # 四个角点恰好落在 scale 的整数倍上 → 像素对齐 → 严格 N×N
    utm_rect = ee.Geometry.Rectangle(
        [nw_x, se_y, se_x, nw_y],
        proj=utm_crs, evenOdd=False,
    )

    # WGS84 版本 — 传给 build_image 做 filterBounds / clip
    wgs84_rect = utm_rect.transform("EPSG:4326", 1)

    return wgs84_rect, utm_rect


def create_roi(lon: float, lat: float, buffer_m: float = 500) -> ee.Geometry:
    """根据中心点坐标和缓冲区半径构造 ROI 几何区域。

    使用 ee.Geometry.Point 创建点，再调用 buffer() 扩展为圆形区域。

    Args:
        lon: 中心点经度。
        lat: 中心点纬度。
        buffer_m: 缓冲区半径，单位米，默认 500。

    Returns:
        缓冲后的 ee.Geometry 对象。
    """
    point = ee.Geometry.Point([lon, lat])
    return point.buffer(buffer_m)


PROBS_BANDS = [
    "water", "trees", "grass", "flooded_vegetation",
    "crops", "shrub_and_scrub", "built", "bare", "snow_and_ice",
]


def build_image(
    roi: ee.Geometry,
    start_date: str,
    end_date: str,
    bands: str = "label",
    composite: str = "first",
) -> ee.Image | None:
    """从 Dynamic World V1 数据集中筛选并合成影像。

    Args:
        roi: 目标区域几何对象。
        start_date: 起始日期，格式 'YYYY-MM-DD'。
        end_date: 结束日期，格式 'YYYY-MM-DD'。
        bands: 波段选择: 'label', 'probs', 'all'。
        composite: 合成策略: 'first', 'mosaic', 'mode', 'mean', 'median', 'collection'。
            'collection' 返回 ImageCollection 而非合成后的单张影像。

    Returns:
        合成后的 ee.Image 或 ee.ImageCollection（collection 模式），
        若无可用影像则返回 None。

    Raises:
        ValueError: 当 composite 参数不在支持列表中时。
    """
    valid_composites = ("first", "mosaic", "mode", "mean", "median", "collection")
    if composite not in valid_composites:
        raise ValueError(f"不支持的合成模式 '{composite}'，可选: {valid_composites}")

    collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
    collection = collection.filterBounds(roi)
    collection = collection.filterDate(start_date, end_date)

    if bands == "probs":
        collection = collection.select(PROBS_BANDS)
    elif bands != "all":
        collection = collection.select(bands)

    if composite == "first":
        image = collection.first()
    elif composite == "mosaic":
        image = collection.mosaic()
    elif composite == "mode":
        image = collection.mode()
    elif composite == "mean":
        image = collection.mean()
    elif composite == "median":
        image = collection.median()
    elif composite == "collection":
        return collection

    if image is None:
        logging.warning("指定时间和区域内无可用 Dynamic World 影像。")
        return None

    image = image.clip(roi)

    try:
        proj = image.projection().getInfo()
        transform = proj.get("transform", [10, 0, 0, 0, -10, 0])
        scale_x = abs(transform[0])
        scale_y = abs(transform[4])
    except Exception:
        scale_x = scale_y = 10

    try:
        area_m2 = roi.area(1).getInfo()
        area_approx = area_m2 / (scale_x * scale_y)
        if area_approx > 10000 * 10000:
            warnings.warn(
                f"输出像素数约 {area_approx:.0f}，超出 GEE 推荐上限 10000x10000。"
                f"建议增大 scale 参数或缩小 ROI 范围。"
            )
    except Exception:
        pass

    return image


def download_image(
    image: ee.Image,
    output_dir: str,
    name: str,
    scale: int = 10,
    crs: str = "EPSG:4326",
    fmt: str = "GEO_TIFF",
    file_per_band: bool = True,
    region: ee.Geometry | None = None,
) -> tuple[str, float]:
    """通过 getDownloadURL() 下载影像到本地文件。

    使用指数退避重试机制: 1s -> 2s -> 4s，最多 3 次。

    Returns:
        (文件路径, 文件大小MB) 元组。

    Raises:
        RuntimeError: 全部重试失败时抛出。
    """
    params = {
        "scale": scale,
        "crs": crs,
        "format": fmt,
        "filePerBand": file_per_band,
    }
    if region is not None:
        params["region"] = region
    url = image.getDownloadURL(params)

    extension = ".tif"
    if fmt == "ZIPPED_GEO_TIFF":
        extension = ".zip"
    elif fmt == "NPY":
        extension = ".npy"

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{name}{extension}")
    max_retries = 3

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=300)
            if resp.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                return filepath, size_mb
            else:
                logging.warning(
                    f"下载 {name} 失败: HTTP {resp.status_code} (尝试 {attempt + 1}/{max_retries})"
                )
        except (RequestException, OSError) as e:
            logging.warning(
                f"下载 {name} 网络错误: {e} (尝试 {attempt + 1}/{max_retries})"
            )
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    raise RuntimeError(f"下载失败: {name}，已重试 {max_retries} 次")


def download_single_point(
    point: CoordPoint,
    output_dir: str,
    params: dict,
) -> DownloadResult:
    """执行单点下载完整流水线: ROI -> 影像构建 -> 下载。

    这是 CLI 和 WebUI 共享的顶层函数。
    内部捕获所有异常，从不抛出，始终返回 DownloadResult。
    """
    start_time = time.time()
    try:
        scale = params.get("scale", 10)
        crs = params.get("crs") or _get_utm_epsg(point.lon, point.lat)
        target_pixels = params.get("target_pixels", 128)
        wgs84_rect, utm_rect = _create_square_roi(point.lon, point.lat, scale, target_pixels)
        roi = create_roi(point.lon, point.lat, params.get("buffer", 500))
        composite = params.get("composite", "first")
        bands = params.get("bands", "label")
        base_name = (
            f"{bands}_{composite}"
            f"_E{point.lon}_N{point.lat}"
            f"_{params['start_date']}_{params['end_date']}"
        )
        result = build_image(
            roi,
            params["start_date"],
            params["end_date"],
            bands=bands,
            composite=composite,
        )

        if result is None:
            elapsed = time.time() - start_time
            return DownloadResult(
                point=point, success=False, elapsed_sec=elapsed,
                error=f"无可用影像: {point.name} 在 {params['start_date']} ~ {params['end_date']} 内无数据",
            )

        # ── collection 模式：逐景下载 ──
        if composite == "collection":
            collection: ee.ImageCollection = result
            # 创建点位专属子文件夹
            point_dir = os.path.join(output_dir, base_name)
            os.makedirs(point_dir, exist_ok=True)

            # 获取每景的时间戳
            try:
                ts_list = collection.aggregate_array("system:time_start").getInfo()
            except Exception:
                ts_list = []

            images = collection.toList(collection.size())
            n = int(collection.size().getInfo())
            total_mb = 0.0
            downloaded = 0
            errors = []
            crs = params.get("crs") or _get_utm_epsg(point.lon, point.lat)

            for i in range(n):
                img = ee.Image(images.get(i))
                # 构造时间戳文件名
                if i < len(ts_list) and ts_list[i]:
                    date_str = datetime.utcfromtimestamp(ts_list[i] / 1000).strftime("%Y%m%d_%H%M%S")
                else:
                    date_str = f"scene_{i:04d}"
                img_name = f"{base_name}_{date_str}"

                try:
                    fpath, smb = download_image(
                        img.clip(wgs84_rect), point_dir, img_name,
                        scale=params.get("scale", 10),
                        crs=crs,
                        fmt=params.get("fmt", "GEO_TIFF"),
                        file_per_band=params.get("file_per_band", True),
                        region=utm_rect,
                    )
                    total_mb += smb
                    downloaded += 1
                except Exception as e:
                    errors.append(f"{img_name}: {e}")
                    logging.warning(f"下载 {img_name} 失败: {e}")

            elapsed = time.time() - start_time
            if downloaded == 0 and errors:
                return DownloadResult(
                    point=point, success=False, elapsed_sec=elapsed,
                    error=f"全部 {len(errors)} 景下载失败: {errors[0]}",
                )
            return DownloadResult(
                point=point, success=True,
                filepath=point_dir,
                size_mb=total_mb,
                elapsed_sec=elapsed,
            )

        # ── 合成模式：单景下载 ──
        image: ee.Image = result
        crs = params.get("crs") or _get_utm_epsg(point.lon, point.lat)
        filepath, size_mb = download_image(
            image, output_dir, base_name,
            scale=params.get("scale", 10),
            crs=crs,
            fmt=params.get("fmt", "GEO_TIFF"),
            file_per_band=params.get("file_per_band", True),
            region=utm_rect,
        )
        elapsed = time.time() - start_time
        return DownloadResult(
            point=point, success=True, filepath=filepath,
            size_mb=size_mb, elapsed_sec=elapsed,
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logging.error(f"下载 {point.name} 异常: {e}")
        return DownloadResult(
            point=point, success=False, elapsed_sec=elapsed, error=str(e),
        )


def setup_logging(output_dir: str) -> None:
    """配置日志系统: 控制台 + download.log 双写。"""
    os.makedirs(output_dir, exist_ok=True)
    log_file = os.path.join(output_dir, "download.log")
    root_logger = logging.getLogger()

    # 避免重复添加同一文件的 handler
    if any(
        isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file)
        for h in root_logger.handlers
    ):
        return

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.DEBUG)


def write_error_csv(output_dir: str, errors: list[DownloadResult]) -> None:
    """将失败项写入 download_errors.csv 文件。仅当 errors 非空时才创建文件。"""
    if not errors:
        return
    csv_path = os.path.join(output_dir, "download_errors.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["lon", "lat", "name", "error"])
        for result in errors:
            writer.writerow([result.point.lon, result.point.lat, result.point.name, result.error])
    logging.info(f"错误清单已写入: {csv_path} ({len(errors)} 条)")


# ── 已下载文件浏览 ─────────────────────────────────────────────

DW_CATEGORIES = {
    0: "水体", 1: "树木", 2: "草地", 3: "淹水植被",
    4: "作物", 5: "灌丛", 6: "建筑", 7: "裸地", 8: "冰雪",
}


def list_tif_files(output_dir: str) -> list[dict]:
    """扫描输出目录，返回所有 tif/zip/npy 文件的元信息列表。

    Returns:
        列表每项包含: name, path, size_mb, modified
    """
    if not os.path.isdir(output_dir):
        return []
    files = []
    for fname in sorted(os.listdir(output_dir)):
        if not fname.endswith((".tif", ".zip", ".npy")):
            continue
        fpath = os.path.join(output_dir, fname)
        try:
            stat = os.stat(fpath)
            files.append({
                "name": fname,
                "path": fpath,
                "size_mb": stat.st_size / (1024 * 1024),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except OSError:
            continue
    # 按修改时间倒序
    files.sort(key=lambda f: f["modified"], reverse=True)
    return files


def list_dir_contents(dir: str) -> list[dict]:
    """扫描目录，返回所有子目录和文件的统一列表。

    每项含 type 字段区分 "dir" 或 "file"。目录排在文件前面，同类按名称排序。
    仅收录 tif/zip/npy 文件（与 list_tif_files 保持一致）。

    Returns:
        列表每项包含:
        - 目录: type, name, path
        - 文件: type, name, path, size_mb, modified
    """
    if not os.path.isdir(dir):
        return []

    dirs = []
    files = []
    for entry in sorted(os.listdir(dir)):
        full_path = os.path.join(dir, entry)
        if os.path.isdir(full_path):
            dirs.append({
                "type": "dir",
                "name": entry,
                "path": full_path + os.sep,
            })
        elif entry.endswith((".tif", ".zip", ".npy")):
            try:
                stat = os.stat(full_path)
                files.append({
                    "type": "file",
                    "name": entry,
                    "path": full_path,
                    "size_mb": stat.st_size / (1024 * 1024),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
            except OSError:
                continue

    # 目录优先，同类按名称排序
    dirs.sort(key=lambda x: x["name"])
    files.sort(key=lambda x: x["name"])
    return dirs + files


def get_tif_stats(filepath: str) -> dict | None:
    """读取 GeoTIFF，返回统计信息。

    对 label 波段（uint8）返回地物类别像素统计；
    对 probs 波段（float）返回数值统计（min/max/mean/std），
    多波段 probs 返回逐波段统计。

    Returns:
        label 文件: {"total": N, "data_type": "label", "categories": {...}}
        probs 单波段: {"total": N, "data_type": "probs", "min": ..., "max": ..., "mean": ..., "std": ...}
        probs 多波段: {"total": N, "data_type": "probs_multiband", "bands": {"name": {...}, ...}}
        读取失败返回 None。
    """
    try:
        import numpy as np
        import rasterio
        with rasterio.open(filepath) as src:
            count = src.count
            dtype = src.dtypes[0]
            total = int(src.width * src.height)

        # probs 波段：浮点概率值 [0,1]
        if "float" in dtype:
            if count >= 9:
                # 多波段 probs → 逐波段统计
                with rasterio.open(filepath) as src:
                    bands_stats = {}
                    for bi, name in enumerate(PROBS_BANDS):
                        band_data = src.read(bi + 1)
                        bands_stats[name] = {
                            "min": round(float(band_data.min()), 4),
                            "max": round(float(band_data.max()), 4),
                            "mean": round(float(band_data.mean()), 4),
                            "std": round(float(band_data.std()), 4),
                        }
                return {
                    "total": total,
                    "data_type": "probs_multiband",
                    "bands": bands_stats,
                }
            else:
                # 单波段 probs
                with rasterio.open(filepath) as src:
                    data = src.read(1)
                return {
                    "total": total,
                    "data_type": "probs",
                    "min": round(float(data.min()), 4),
                    "max": round(float(data.max()), 4),
                    "mean": round(float(data.mean()), 4),
                    "std": round(float(data.std()), 4),
                }

        # label 波段：整数类别 0-8
        with rasterio.open(filepath) as src:
            data = src.read(1)
        values, counts = np.unique(data, return_counts=True)
        categories = {}
        for v, c in zip(values, counts):
            vi = int(v)
            if 0 <= vi <= 8:
                name = DW_CATEGORIES.get(vi, f"未知({vi})")
                categories[vi] = {
                    "name": name,
                    "pixels": int(c),
                    "pct": round(float(c) / total * 100, 1),
                }
        return {"total": total, "data_type": "label", "categories": categories}
    except ImportError:
        return None
    except Exception as e:
        logging.warning(f"读取 {filepath} 失败: {e}")
        return None


# DW 地物类别 RGB 颜色映射
DW_COLORS = {
    0: (65, 155, 223),   # 水体 #419BDF
    1: (57, 125, 73),    # 树木 #397D49
    2: (136, 176, 83),   # 草地 #88B053
    3: (122, 135, 198),  # 淹水植被 #7A87C6
    4: (228, 150, 53),   # 作物 #E49635
    5: (223, 195, 90),   # 灌丛 #DFC35A
    6: (196, 40, 27),    # 建筑 #C4281B
    7: (165, 155, 143),  # 裸地 #A59B8F
    8: (179, 159, 225),  # 冰雪 #B39FE1
}


def tif_to_preview_png(filepath: str, max_size: int = 600, band_index: int | None = None) -> str | None:
    """将 GeoTIFF 渲染为 PNG 预览图，返回临时文件路径。

    对 label 波段（uint8）使用 DW 彩色映射；
    对 probs 波段（float）渲染为灰度图；
    对多波段使用前 3 个波段合成 RGB。

    Returns:
        临时 PNG 文件路径，失败返回 None。
    """
    try:
        import numpy as np
        import rasterio
        from PIL import Image

        with rasterio.open(filepath) as src:
            data = src.read()
            count = src.count
            dtype = src.dtypes[0]

        if count == 1:
            if "float" in dtype:
                # probs 单波段 → 灰度图（0→黑, 1→白）
                arr = data[0].astype(np.float32)
                h, w = arr.shape
                rgb = np.zeros((h, w, 3), dtype=np.uint8)
                # 归一化到 0-255
                vmin, vmax = arr.min(), arr.max()
                if vmax > vmin:
                    gray = ((arr - vmin) / (vmax - vmin) * 255).astype(np.uint8)
                else:
                    gray = np.zeros((h, w), dtype=np.uint8)
                rgb[:, :, 0] = gray
                rgb[:, :, 1] = gray
                rgb[:, :, 2] = gray
            else:
                # label 单波段 → 彩色映射
                arr = data[0].astype(np.uint8)
                h, w = arr.shape
                rgb = np.zeros((h, w, 3), dtype=np.uint8)
                for vi, color in DW_COLORS.items():
                    mask = arr == vi
                    rgb[mask] = color
        elif "float" in dtype and count >= 9 and band_index is not None:
            # probs 多波段，渲染指定波段为灰度图
            arr = data[band_index].astype(np.float32)
            h, w = arr.shape
            rgb = np.zeros((h, w, 3), dtype=np.uint8)
            vmin, vmax = arr.min(), arr.max()
            if vmax > vmin:
                gray = ((arr - vmin) / (vmax - vmin) * 255).astype(np.uint8)
            else:
                gray = np.zeros((h, w), dtype=np.uint8)
            rgb[:, :, 0] = gray
            rgb[:, :, 1] = gray
            rgb[:, :, 2] = gray
        elif "float" in dtype and count >= 9:
            # probs 多波段 → argmax 彩色映射
            arr = data[:9].astype(np.float32)
            label = np.argmax(arr, axis=0).astype(np.uint8)
            h, w = label.shape
            rgb = np.zeros((h, w, 3), dtype=np.uint8)
            for vi, color in DW_COLORS.items():
                mask = label == vi
                rgb[mask] = color
        elif "float" in dtype:
            # 其他 float 多波段 → 仅渲染第一个波段为灰度图
            arr = data[0].astype(np.float32)
            h, w = arr.shape
            rgb = np.zeros((h, w, 3), dtype=np.uint8)
            vmin, vmax = arr.min(), arr.max()
            if vmax > vmin:
                gray = ((arr - vmin) / (vmax - vmin) * 255).astype(np.uint8)
            else:
                gray = np.zeros((h, w), dtype=np.uint8)
            rgb[:, :, 0] = gray
            rgb[:, :, 1] = gray
            rgb[:, :, 2] = gray
        else:
            # label 多波段 → 取前 3 个波段做 RGB
            bands = data[:3].astype(np.float32)
            for bi in range(bands.shape[0]):
                bmin, bmax = bands[bi].min(), bands[bi].max()
                if bmax > bmin:
                    bands[bi] = (bands[bi] - bmin) / (bmax - bmin) * 255
                else:
                    bands[bi] = 0
            rgb = np.dstack(bands).astype(np.uint8)

        img = Image.fromarray(rgb)

        # 缩放
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        # 写入临时文件
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name, "PNG")
        return tmp.name

    except ImportError:
        return None
    except Exception as e:
        logging.warning(f"预览 {filepath} 失败: {e}")
        return None
