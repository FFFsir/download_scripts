"""Satellite Embedding V1 下载工具 -- WebUI 入口。

基于 NiceGUI 构建，提供参数配置、坐标输入（文本框 / CSV 上传）、
逐点进度反馈等交互功能。

启动方式:
    uv run se-web
    浏览器访问 http://127.0.0.1:8001
"""

import csv
import io
import logging
import os
import tempfile

from SatelliteEmbedding.core import (
    init_gee,
    parse_coords,
    download_single_point,
    list_dir_contents,
    se_tif_to_preview_png,
    SE_BAND_NAMES,
)


def _preview_npy(filepath: str) -> str | None:
    """读取 .npy 文件，返回数据形状和统计摘要 HTML。"""
    try:
        import numpy as np
        data = np.load(filepath)
        shape = data.shape
        dtype = data.dtype
        ndim = data.ndim
        lines = [
            f"<b>形状:</b> {shape}",
            f"<b>维度:</b> {ndim}",
            f"<b>数据类型:</b> {dtype}",
        ]
        if ndim <= 2 and data.size <= 16384:
            lines.append("<br><b>数据预览:</b>")
            lines.append(f"<pre style='font-size:11px; max-height:300px; overflow:auto;'>{np.array2string(data, threshold=data.size)}</pre>")
        elif ndim > 0:
            lines.append(f"<b>min:</b> {data.min()}")
            lines.append(f"<b>max:</b> {data.max()}")
            lines.append(f"<b>mean:</b> {data.mean():.4f}")
        return "<br>".join(lines)
    except ImportError:
        return "<span style='color:red;'>预览 NPY 需要 numpy</span>"
    except Exception as e:
        return f"<span style='color:red;'>读取失败: {e}</span>"


def check_gee_auth() -> bool:
    """检测 GEE 认证状态（不强制认证）。"""
    try:
        import ee
        ee.Initialize()
        return True
    except Exception:
        return False


def build_params(
    year: int,
    years: list[int] | None,
    bands: str,
    cross_year: str,
    scale: int,
    crs: str,
    fmt: str,
    target_pixels: int = 128,
) -> dict:
    """将 WebUI 表单值组装为 download_single_point 所需的参数字典。"""
    return {
        "year": year,
        "years": years,
        "bands": bands,
        "cross_year": cross_year,
        "scale": scale,
        "crs": crs,
        "fmt": fmt,
        "target_pixels": target_pixels,
    }


# ── NiceGUI 页面定义 ─────────────────────────────────────────────

def create_ui():
    """创建 NiceGUI 页面结构。"""
    from nicegui import ui, run, app

    @ui.page("/")
    def index():
        # 页面容器：居中、最大宽 900px
        with ui.column().classes("w-full max-w-3xl mx-auto px-4 py-4"):

            # ── 标题 ──
            ui.markdown("# Satellite Embedding V1 下载工具").classes("text-2xl font-bold mb-1")
            ui.markdown("基于 Google Earth Engine，按坐标下载遥感嵌入向量数据").classes("text-sm text-gray-500 mb-6")

            # ── 认证 ──
            with ui.card().classes("w-full p-4 mb-4"):
                ui.markdown("### 认证").classes("text-base font-semibold mb-3")

                auth_status = check_gee_auth()
                if not auth_status:
                    with ui.element("div").classes("bg-red-50 border border-red-200 rounded p-3 mb-3"):
                        ui.markdown(
                            "**⚠ 未检测到 GEE 认证**  \n"
                            "请在终端运行 `earthengine authenticate` 完成认证后刷新页面。"
                        )

                with ui.row().classes("items-end gap-4"):
                    project_id_input = ui.input(
                        label="Google Cloud Project ID",
                        placeholder="my-earth-engine-project",
                    ).classes("grow")
                    ui.button("初始化认证", on_click=lambda: do_init_gee(), icon="login")

                async def do_init_gee():
                    if not project_id_input.value:
                        ui.notify("请输入 Project ID", type="warning")
                        return
                    try:
                        await run.io_bound(init_gee, project_id_input.value)
                        ui.notify("GEE 认证初始化成功！", type="positive")
                    except SystemExit:
                        ui.notify("认证初始化失败", type="negative")

            # ── 坐标输入 ──
            with ui.card().classes("w-full p-4 mb-4"):
                ui.markdown("### 坐标输入").classes("text-base font-semibold mb-3")

                coords_textarea = ui.textarea(
                    label="粘贴坐标（分号分隔）",
                    placeholder="108.95,34.25;116.40,39.90;121.47,31.23",
                ).classes("w-full").props("rows=3")

                ui.markdown("或上传 CSV 文件（列: lon, lat, name）").classes("text-xs text-gray-400 mt-1 mb-2")

                csv_preview = ui.markdown("")

                async def on_upload(e):
                    file_obj = getattr(e, "file", None)
                    if file_obj is None:
                        return
                    data = await file_obj.read()
                    content = data.decode("utf-8") if isinstance(data, bytes) else str(data)

                    # Write to temp file and use shared parse_coords for consistent validation
                    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(content)

                        # Count total data rows before parsing (for skip notification)
                        reader = csv.DictReader(io.StringIO(content))
                        total_rows = 0
                        for row in reader:
                            if not row or all(v.strip() == "" for v in row.values()):
                                continue
                            first_val = next(iter(row.values()), "").strip()
                            if not first_val or first_val.startswith("#"):
                                continue
                            total_rows += 1

                        points = parse_coords(tmp_path)

                        if total_rows > len(points):
                            skipped = total_rows - len(points)
                            ui.notify(
                                f"已跳过 {skipped} 行无效坐标（越界或格式错误）",
                                type="warning",
                            )

                        if points:
                            coords_textarea.set_value(
                                ";".join(f"{p.lon},{p.lat}" for p in points)
                            )
                            csv_preview.set_content(
                                f"**已识别 {len(points)} 个坐标点并填入坐标栏**\n\n"
                                + "\n".join(f"- {p.name} ({p.lon},{p.lat})" for p in points[:20])
                                + ("\n\n... 仅显示前 20 个" if len(points) > 20 else "")
                            )
                        else:
                            csv_preview.set_content("**未能解析到有效坐标**，请确认 CSV 含 lon,lat 列")
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

                ui.upload(
                    label="上传 CSV",
                    auto_upload=True,
                    max_file_size=10 * 1024 * 1024,
                    on_upload=on_upload,
                ).classes("w-full")

            # ── 下载参数 ──
            with ui.card().classes("w-full p-4 mb-4"):
                ui.markdown("### 下载参数").classes("text-base font-semibold mb-3")

                # 年份选择（多选，2017-2024）
                with ui.row().classes("gap-4 flex-wrap"):
                    year_select = ui.select(
                        options={2017: "2017", 2018: "2018", 2019: "2019",
                                 2020: "2020", 2021: "2021", 2022: "2022",
                                 2023: "2023", 2024: "2024"},
                        value=2024,
                        label="单年份",
                    ).style("min-width:150px")
                    years_input = ui.input(
                        label="多年份（逗号分隔，如 2022,2023,2024）",
                        placeholder="留空则使用单年份",
                    ).style("min-width:280px")

                # 波段 + 合成策略
                with ui.row().classes("gap-4 flex-wrap mt-4"):
                    bands_input = ui.input(
                        value="all",
                        label="波段选择 (all 或逗号分隔如 B1,B2,B3)",
                    ).style("min-width:280px")
                    cross_year_select = ui.select(
                        options=["first", "mean", "median"],
                        value="first",
                        label="跨年合成策略",
                    ).style("min-width:180px")

                # 输出尺寸 + 分辨率
                with ui.row().classes("gap-4 flex-wrap mt-4"):
                    target_pixels_input = ui.number(value=128, min=1, label="输出尺寸 (像素，宽=高)").style("min-width:180px")
                    scale_input = ui.number(value=10, min=1, label="空间分辨率 (米/像素)").style("min-width:180px")

                # 输出格式 + CRS
                with ui.row().classes("gap-4 flex-wrap mt-4"):
                    format_select = ui.select(
                        options=["GEO_TIFF", "ZIPPED_GEO_TIFF", "NPY"],
                        value="GEO_TIFF",
                        label="输出格式",
                    ).style("min-width:180px")
                    crs_input = ui.input(value="", label="坐标参考系 (CRS) — 留空自动选择 UTM 投影").style("min-width:200px")

                # ── 恢复上次输入 ──
                mem = app.storage.user
                if mem.get("project"):
                    project_id_input.set_value(mem["project"])
                if mem.get("coords"):
                    coords_textarea.set_value(mem["coords"])
                if mem.get("year"):
                    year_select.set_value(mem["year"])
                if mem.get("years"):
                    years_input.set_value(mem["years"])
                if mem.get("bands"):
                    bands_input.set_value(mem["bands"])
                if mem.get("cross_year"):
                    cross_year_select.set_value(mem["cross_year"])
                if mem.get("buffer"):
                    buffer_input.set_value(mem["buffer"])
                if mem.get("scale"):
                    scale_input.set_value(mem["scale"])
                if mem.get("target_pixels"):
                    target_pixels_input.set_value(mem["target_pixels"])
                if mem.get("format"):
                    format_select.set_value(mem["format"])
                if mem.get("crs"):
                    crs_input.set_value(mem["crs"])

            # ── 执行 ──
            with ui.card().classes("w-full p-4 mb-4"):
                ui.markdown("### 下载执行").classes("text-base font-semibold mb-3")

                output_input = ui.input(label="输出目录", value="./output").classes("w-full")

                if mem.get("output"):
                    output_input.set_value(mem["output"])

                progress_bar = ui.linear_progress(value=0).classes("w-full mt-4")
                progress_label = ui.label("就绪").classes("text-sm text-gray-500 mt-1")
                status_container = ui.element("div").classes("w-full mt-2")

                async def on_download():
                    # 保存当前输入以便下次恢复
                    mem = app.storage.user
                    mem["project"] = project_id_input.value
                    mem["coords"] = coords_textarea.value
                    mem["year"] = year_select.value
                    mem["years"] = years_input.value
                    mem["bands"] = bands_input.value
                    mem["cross_year"] = cross_year_select.value
                    mem["scale"] = scale_input.value
                    mem["target_pixels"] = target_pixels_input.value
                    mem["format"] = format_select.value
                    mem["crs"] = crs_input.value
                    mem["output"] = output_input.value

                    try:
                        if not coords_textarea.value:
                            ui.notify("请输入坐标或上传 CSV 文件", type="warning")
                            return
                        points = parse_coords(coords_textarea.value)
                        if not points:
                            ui.notify("未解析到有效坐标点", type="warning")
                            return

                        # 解析 years
                        years = None
                        if years_input.value:
                            try:
                                years = [int(y.strip()) for y in years_input.value.split(",")]
                            except ValueError:
                                ui.notify("年份格式错误，请使用逗号分隔的整数", type="warning")
                                return

                        params = build_params(
                            year=year_select.value or 2024,
                            years=years,
                            bands=bands_input.value or "all",
                            cross_year=cross_year_select.value or "first",
                            scale=scale_input.value or 10,
                            crs=crs_input.value or None,
                            fmt=format_select.value or "GEO_TIFF",
                            target_pixels=target_pixels_input.value or 128,
                        )

                        output_dir = output_input.value or "./output"
                        os.makedirs(output_dir, exist_ok=True)
                        total = len(points)
                        status_container.clear()
                        successes = 0
                        failures = 0

                        for i, point in enumerate(points, 1):
                            progress_label.set_text(f"下载中: {point.name} ({i}/{total})")
                            progress_bar.set_value(i / total)
                            result = await run.io_bound(download_single_point, point, output_dir, params)
                            if result.success:
                                successes += 1
                                with status_container:
                                    ui.markdown(f"- {point.name}: 完成 ({result.size_mb:.1f}MB, {result.elapsed_sec:.1f}s)")
                                ui.notify(f"{point.name} 下载完成", type="positive")
                            else:
                                failures += 1
                                with status_container:
                                    ui.markdown(f"- {point.name}: **失败** -- {result.error}")
                                ui.notify(f"{point.name} 失败: {result.error}", type="negative")

                        progress_label.set_text(f"完成! 成功 {successes}/{total}，失败 {failures}/{total}")
                        progress_bar.set_value(1.0)
                        refresh_file_list()
                    except Exception as e:
                        ui.notify(f"下载异常: {e}", type="negative")
                        logging.exception(f"下载异常: {e}")

                ui.button("开始下载", on_click=on_download, icon="download").props("color=primary size=lg").classes("mt-3")

            # ── 已下载文件 ──
            with ui.card().classes("w-full p-4 mb-4"):

                files_container = ui.element("div").classes("w-full")

                current_browse_path = None

                def navigate_to(path: str):
                    nonlocal current_browse_path
                    current_browse_path = path
                    browse_dir_input.value = path
                    refresh_file_list()

                def show_preview(filepath: str):
                    """弹出弹窗，支持切换波段查看灰度预览图；NPY 文件直接显示数据和形状。"""

                    # NPY 文件预览
                    if filepath.lower().endswith(".npy"):
                        with ui.dialog() as dialog, ui.card().classes("p-4").style("width:90vw; max-width:90vw"):
                            ui.markdown(f"### {os.path.basename(filepath)}")
                            npy_html = _preview_npy(filepath)
                            ui.html(f'<div style="font-size:14px; line-height:1.8;">{npy_html}</div>')
                            import datetime as _dt
                            sz_mb = os.path.getsize(filepath) / (1024 * 1024)
                            mt = _dt.datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
                            ui.label(f"文件大小: {sz_mb:.1f} MB | 修改时间: {mt}").classes("text-xs text-gray-500 mt-2")
                        dialog.open()
                        return

                    def make_png(band_idx: int = 0):
                        return se_tif_to_preview_png(filepath, max_size=900, band_index=band_idx)

                    png_path = make_png()
                    if png_path is None:
                        ui.notify("无法生成预览（需要 rasterio + Pillow）", type="warning")
                        return

                    with ui.dialog() as dialog, ui.card().classes("p-4").style("width:90vw; max-width:90vw"):
                        ui.markdown(f"### {os.path.basename(filepath)}")
                        ui.markdown("单波段灰度预览（值域 [-1, 1] → 黑白灰度）").classes("text-xs text-gray-500 mb-2")
                        band_options = {i: name for i, name in enumerate(SE_BAND_NAMES)}
                        band_select = ui.select(
                            options=band_options,
                            value=0,
                            label="波段选择",
                            on_change=lambda e: refresh_image(make_png(int(e.value) if e.value is not None else 0)),
                        ).style("width:200px").classes("mb-3")

                        with ui.row().style("display:flex; gap:20px; width:100%"):
                            with ui.column().style("flex:0 0 62%"):
                                preview_image = ui.image(png_path).style("width:100%; object-fit:contain")
                            with ui.column().style("width:35%; min-width:200px"):
                                from datetime import datetime
                                stat = os.stat(filepath)
                                ui.label(f"文件大小: {stat.st_size / 1024 / 1024:.1f} MB").classes("text-sm")
                                ui.label(f"修改时间: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}").classes("text-xs text-gray-500")
                                ui.label(f"波段数: 64 (A00–A63)").classes("text-xs text-gray-500")
                                ui.label(f"值域: [-1, 1] float32").classes("text-xs text-gray-500")
                                ui.html(
                                    '<div style="margin-top:12px; font-size:12px;">'
                                    '<div style="display:flex; justify-content:space-between; margin-bottom:2px;">'
                                    '<span>-1</span><span style="color:#888;">值域 [-1, 1]</span><span>+1</span>'
                                    '</div>'
                                    '<div style="height:20px; background:linear-gradient(to right, #000, #fff); '
                                    'border:1px solid #ccc; border-radius:2px;"></div>'
                                    '<div style="display:flex; justify-content:space-between; margin-top:2px; color:#888;">'
                                    '<span>黑</span><span>白</span>'
                                    '</div>'
                                    '</div>'
                                )

                        def refresh_image(png_path_new: str | None):
                            if png_path_new:
                                preview_image.set_source(png_path_new)

                    dialog.open()

                def refresh_file_list():
                    nonlocal current_browse_path
                    files_container.clear()
                    browse_dir = browse_dir_input.value or "./output"
                    current_browse_path = browse_dir
                    items = list_dir_contents(browse_dir)
                    with files_container:
                        parent = os.path.dirname(current_browse_path)
                        is_root = (parent == current_browse_path)
                        if not is_root:
                            ui.button(
                                "📂 上一层",
                                on_click=lambda: navigate_to(parent),
                            ).props("flat size=sm").classes("mb-2")
                        if not items:
                            ui.label("当前目录暂无文件或子目录").classes("text-gray-400 text-sm")
                            return
                        for item in items:
                            if item["type"] == "dir":
                                ui.button(
                                    f"📁 {item['name']}",
                                    on_click=lambda _, p=item["path"]: navigate_to(p),
                                ).props("flat size=sm")
                            else:
                                name_lower = item["name"].lower()
                                is_tif = any(name_lower.endswith(ext) for ext in (".tif", ".tiff"))
                                is_npy = name_lower.endswith(".npy")
                                if is_tif:
                                    with ui.row().classes("gap-2 items-center w-full py-0.5"):
                                        ui.label(f"📄 {item['name']}").classes("text-sm")
                                        ui.label(f"{item['size_mb']:.1f} MB").classes("text-xs text-gray-500")
                                        ui.label(item["modified"]).classes("text-xs text-gray-400")
                                        ui.button("预览", on_click=lambda _, p=item["path"]: show_preview(p)).props("flat size=sm")
                                elif is_npy:
                                    with ui.row().classes("gap-2 items-center w-full py-0.5"):
                                        ui.label(f"📊 {item['name']}").classes("text-sm")
                                        ui.label(f"{item['size_mb']:.1f} MB").classes("text-xs text-gray-500")
                                        ui.label(item["modified"]).classes("text-xs text-gray-400")
                                        ui.button("查看数据", on_click=lambda _, p=item["path"]: show_preview(p)).props("flat size=sm")
                                else:
                                    with ui.row().classes("gap-2 items-center w-full py-0.5"):
                                        ui.label(f"📄 {item['name']}").classes("text-sm")
                                        ui.label(f"{item['size_mb']:.1f} MB").classes("text-xs text-gray-500")
                                        ui.label(item["modified"]).classes("text-xs text-gray-400")

                with ui.row().classes("items-end gap-2 w-full mb-3"):
                    browse_dir_input = ui.input(label="浏览目录", value="./output").classes("grow")
                    ui.button("查看", on_click=refresh_file_list, icon="folder_open").props("flat size=sm")
                    ui.button("", on_click=refresh_file_list, icon="refresh").props("flat round size=sm")

                refresh_file_list()

            # ── 页脚 ──
            ui.markdown("*Powered by Google Earth Engine + Satellite Embedding V1 + NiceGUI*").classes("text-xs text-gray-400 text-center mt-2")

    return ui


def main():
    """启动 NiceGUI Web 服务器。"""
    create_ui()
    from nicegui import ui
    ui.run(title="Satellite Embedding Downloader", host="127.0.0.1", port=8001, reload=False, show=False, storage_secret="se-downloader-2026")


if __name__ == "__main__":
    main()
if __name__ == "__mp_main__":
    main()
