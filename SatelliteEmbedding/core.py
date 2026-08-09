"""Satellite Embedding V1 核心模块 -- GEE 操作、坐标解析、下载执行。

CLI 和 WebUI 共享此模块。
"""

import csv
import logging
import os
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass

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


def parse_coords(input_str: str) -> list:
    """解析坐标输入，自动识别 CSV 文件或坐标字符串。

    识别逻辑:
        1. 若 input_str 指向一个存在的文件 -> 按 CSV 解析。
           列名: lon, lat, name(可选)。无 name 列时自动生成 "lon,lat"。
        2. 否则 -> 视为分号分隔的坐标字符串 "lon1,lat1;lon2,lat2"。

    验证规则:
        - lon in [-180, 180], lat in [-90, 90]。
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


def _parse_csv(filepath: str) -> list:
    """从 CSV 文件解析坐标点。"""
    points: list = []
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


def _parse_string(coord_str: str) -> list:
    """从分号分隔的坐标字符串解析坐标点。"""
    points: list = []
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


def create_roi(lon: float, lat: float, buffer_m: float = 640) -> ee.Geometry:
    """根据中心点坐标和缓冲区半径构造 ROI 几何区域。

    使用 ee.Geometry.Point 创建点，再调用 buffer() 扩展为圆形区域。

    Args:
        lon: 中心点经度。
        lat: 中心点纬度。
        buffer_m: 缓冲区半径，单位米，默认 640。

    Returns:
        缓冲后的 ee.Geometry 对象。
    """
    point = ee.Geometry.Point([lon, lat])
    return point.buffer(buffer_m)


def _l2_normalize(image):
    """对 64 维嵌入向量逐像素 L2 归一化，恢复单位向量。

    仅在 cross_year == "mean" 时调用。first 和 median 不改变向量方向，
    无需归一化。

    边界条件:
        - 零向量（norm=0）-> 通过 .where() 保持为零，不产生 NaN
        - 极小值（1e-10）-> 除法放大，但嵌入值域 [-1,1] 不会出现此情况
    """
    norm = image.pow(2).reduce(ee.Reducer.sum()).sqrt()
    return image.divide(norm).where(norm.eq(0), image)


def _check_size_limit(roi: ee.Geometry, scale: int) -> None:
    """估算下载数据量，超出 GEE 32MB 限制时发出警告。

    警告阈值 131,072 像素（~32MB = 131072 * 64 bands * 4 bytes）。

    Args:
        roi: 目标区域几何对象。
        scale: 空间分辨率（米/像素）。
    """
    try:
        area_m2 = roi.area(1).getInfo()
        pixels = int(area_m2 / (scale * scale))
        if pixels > 131072:
            size_mb = pixels * 64 * 4 / (1024 * 1024)
            warnings.warn(
                f"预计像素数 {pixels:,}（约 {size_mb:.0f}MB）超出 GEE 32MB 限制。"
                f"建议减小缓冲区半径或增大 scale 参数。"
            )
    except Exception:
        pass


def build_image(
    roi: ee.Geometry,
    year: int | None = None,
    years: list[int] | None = None,
    bands: str = "all",
    cross_year: str = "first",
    scale: int = 10,
) -> ee.Image | None:
    """从 Satellite Embedding V1 数据集中筛选并合成影像。

    数据集: GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL

    Args:
        roi: 目标区域几何对象。
        year: 单年份（与 years 互斥，years 优先级更高）。
        years: 多年份列表。
        bands: 波段选择: 'all' 或逗号分隔的波段名如 "B1,B2,B3"。
        cross_year: 跨年合成策略: 'first', 'mean', 'median'。
            'mean' 后自动 L2 重归一化。
        scale: 空间分辨率（米/像素），用于尺寸限制检查，默认 10。

    Returns:
        合成后的 ee.Image，若无可用影像则返回 None。

    Raises:
        ValueError: 当 cross_year 参数不在支持列表中时。
    """
    valid_cross_years = ("first", "mean", "median")
    if cross_year not in valid_cross_years:
        raise ValueError(
            f"不支持的跨年合成模式 '{cross_year}'，可选: {valid_cross_years}"
        )

    collection = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
    collection = collection.filterBounds(roi)

    # 确定目标年份列表
    if years:
        target_years = years
    elif year is not None:
        target_years = [year]
    else:
        target_years = [2024]

    # 对每个目标年份取第一景
    images = []
    for y in target_years:
        img = collection.filter(ee.Filter.calendarRange(y, y, "year")).first()
        if img is not None:
            images.append(img)

    if not images:
        logging.warning(f"指定区域在年份 {target_years} 内无可用 Satellite Embedding 影像。")
        return None

    multi_year = ee.ImageCollection.fromImages(images)

    # 波段子集选择
    if bands != "all":
        bands_list = [b.strip() for b in bands.split(",")]
        multi_year = multi_year.select(bands_list)

    # 跨年合成
    if cross_year == "first":
        image = multi_year.first()
    elif cross_year == "mean":
        image = multi_year.mean()
        image = _l2_normalize(image)
    elif cross_year == "median":
        image = multi_year.median()
    else:
        raise ValueError(f"Unsupported cross_year: {cross_year}")

    image = image.clip(roi)

    # 检查数据量是否可能超出 GEE 下载限制
    _check_size_limit(roi, scale)

    return image


def _convert_npy_to_npz(npy_filepath: str) -> str | None:
    """将 .npy 文件转换为 .npz 压缩格式，保留原始 .npy 文件。

    Args:
        npy_filepath: 已下载的 .npy 文件完整路径。

    Returns:
        .npz 文件路径，转换失败时返回 None。
    """
    npz_path = os.path.splitext(npy_filepath)[0] + ".npz"
    try:
        import numpy as np
        data = np.load(npy_filepath)
        np.savez_compressed(npz_path, embedding=data)
        return npz_path
    except Exception as e:
        logging.warning(f"NPY 转 NPZ 失败 ({npy_filepath}): {e}")
        return None


def download_image(
    image: ee.Image,
    output_dir: str,
    name: str,
    scale: int = 10,
    crs: str = "EPSG:4326",
    fmt: str = "GEO_TIFF",
    region: ee.Geometry | None = None,
) -> tuple[str, float]:
    """通过 getDownloadURL() 下载影像到本地文件。

    使用指数退避重试机制: 1s -> 2s -> 4s，最多 3 次。
    filePerBand 固定为 False（64 波段单一 GeoTIFF）。

    Returns:
        (文件路径, 文件大小MB) 元组。

    Raises:
        RuntimeError: 全部重试失败时抛出。
    """
    params = {
        "scale": scale,
        "crs": crs,
        "format": fmt,
        "filePerBand": False,
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
                if fmt == "NPY":
                    npz_path = _convert_npy_to_npz(filepath)
                    if npz_path:
                        logging.info(f"已生成 NPZ 文件: {npz_path}")
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

    Args:
        point: 坐标点信息。
        output_dir: 输出目录。
        params: 参数字典，支持的 key:
            year, years, buffer, bands, cross_year, scale, crs, fmt

    Returns:
        DownloadResult，包含成功/失败状态和文件信息。
    """
    start_time = time.time()
    try:
        buffer = params.get("buffer", 640)
        scale = params.get("scale", 10)
        target_pixels = params.get("target_pixels", 128)
        wgs84_rect, utm_rect = _create_square_roi(point.lon, point.lat, scale, target_pixels)
        roi = create_roi(point.lon, point.lat, buffer)

        bands = params.get("bands", "all")
        cross_year = params.get("cross_year", "first")

        # 文件名：bands_cross-year_E经度_N纬度_年份
        bands_safe = bands.replace(",", "_").replace(" ", "")
        # 年份显示
        if "years" in params and params["years"]:
            year_str = "_".join(str(y) for y in params["years"])
        else:
            year_str = str(params.get("year", 2024))
        base_name = (
            f"{bands_safe}_{cross_year}"
            f"_E{point.lon}_N{point.lat}"
            f"_{year_str}"
        )

        image = build_image(
            roi,
            year=params.get("year"),
            years=params.get("years"),
            bands=bands,
            cross_year=cross_year,
            scale=params.get("scale", 10),
        )

        if image is None:
            elapsed = time.time() - start_time
            return DownloadResult(
                point=point, success=False, elapsed_sec=elapsed,
                error=f"无可用影像: {point.name} 在指定年份内无数据",
            )

        crs = params.get("crs") or _get_utm_epsg(point.lon, point.lat)
        filepath, size_mb = download_image(
            image, output_dir, base_name,
            scale=params.get("scale", 10),
            crs=crs,
            fmt=params.get("fmt", "GEO_TIFF"),
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
    """配置日志系统: 控制台 + download.log 双写。

    Args:
        output_dir: 输出目录，日志文件将写入该目录下的 download.log。
    """
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
    """将失败项写入 download_errors.csv 文件。仅当 errors 非空时才创建文件。

    Args:
        output_dir: 输出目录。
        errors: 失败的 DownloadResult 列表。
    """
    if not errors:
        return
    csv_path = os.path.join(output_dir, "download_errors.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["lon", "lat", "name", "error"])
        for result in errors:
            writer.writerow([result.point.lon, result.point.lat, result.point.name, result.error])
    logging.info(f"错误清单已写入: {csv_path} ({len(errors)} 条)")


def list_dir_contents(directory: str) -> list[dict]:
    """列出目录中的子目录和可下载文件（tif/zip/npy）。

    目录项排在文件项之前。

    Args:
        directory: 要浏览的目录路径。

    Returns:
        字典列表，每项包含:
        - type: "dir" 或 "file"
        - name: 项名称
        - path: 完整路径（dir 以 os.sep 结尾）
        - size_mb: 文件大小 (MB)，仅 file
        - modified: 修改时间字符串，仅 file
    """
    if not os.path.isdir(directory):
        return []

    items: list[dict] = []
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return []

    # 目录在前
    for name in entries:
        full = os.path.join(directory, name)
        if os.path.isdir(full):
            items.append({
                "type": "dir",
                "name": name,
                "path": full + os.sep,
            })

    # 文件在后
    for name in entries:
        full = os.path.join(directory, name)
        if os.path.isfile(full):
            ext = os.path.splitext(name)[1].lower()
            if ext in (".tif", ".zip", ".npy"):
                size_mb = os.path.getsize(full) / (1024 * 1024)
                mtime = os.path.getmtime(full)
                modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
                items.append({
                    "type": "file",
                    "name": name,
                    "path": full,
                    "size_mb": size_mb,
                    "modified": modified,
                })

    return items


# SE 64 波段名称: A00–A63
SE_BAND_NAMES = tuple(f"A{i:02d}" for i in range(64))


def se_tif_to_preview_png(filepath: str, max_size: int = 600, band_index: int = 0) -> str | None:
    """将 SE GeoTIFF 指定波段渲染为灰度 PNG 预览图。

    取 64 波段中指定 `band_index` 的 float32 波段，
    将值域 [-1, 1] 线性映射到 0–255 灰度，生成 PNG 临时文件。

    Args:
        filepath: GeoTIFF 文件路径。
        max_size: 预览图长边最大像素数，默认 600。
        band_index: 波段索引，0= A00, 63= A63。

    Returns:
        临时 PNG 文件路径，失败返回 None。
    """
    try:
        import numpy as np
        import rasterio
        from PIL import Image

        with rasterio.open(filepath) as src:
            count = src.count
            if count < 64:
                # 非完整 64 波段文件（可能是波段子集），取第一个波段
                pass
            idx = min(band_index, count - 1) if count > 0 else 0
            arr = src.read(idx + 1).astype(np.float32)

        h, w = arr.shape

        # [-1, 1] → [0, 255] 线性映射
        gray = ((arr + 1.0) / 2.0 * 255.0).clip(0, 255).astype(np.uint8)

        # 缩放到 max_size
        max_dim = max(h, w)
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = Image.fromarray(gray, mode="L").resize((new_w, new_h), Image.LANCZOS)
        else:
            img = Image.fromarray(gray, mode="L")

        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img.save(tmp_path, "PNG")
        return tmp_path
    except ImportError:
        logging.warning("预览功能需要 rasterio + Pillow，请先安装: uv add rasterio Pillow")
        return None
    except Exception as e:
        logging.warning(f"生成预览图失败 ({filepath}): {e}")
        return None
