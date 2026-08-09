"""Dynamic World V1 下载工具 -- WebUI 入口。

基于 NiceGUI 构建，提供参数配置、坐标输入（文本框 / CSV 上传）、
逐点进度反馈等交互功能。

启动方式:
    uv run dw-web
    浏览器访问 http://127.0.0.1:8000
"""

import csv
import io
import logging
import os
import time

from DynamicWorld.core import (
    CoordPoint,
    init_gee,
    parse_coords,
    download_single_point,
    list_dir_contents,
    get_tif_stats,
    tif_to_preview_png,
    DW_CATEGORIES,
    DW_COLORS,
    PROBS_BANDS,
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
            # 小尺寸数据可展示完整矩阵
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
    start_date: str,
    end_date: str,
    bands: str,
    composite: str,
    scale: int,
    crs: str,
    fmt: str,
    file_per_band: bool,
    target_pixels: int = 128,
) -> dict:
    """将 WebUI 表单值组装为 download_single_point 所需的参数字典。"""
    return {
        "start_date": start_date,
        "end_date": end_date,
        "bands": bands,
        "composite": composite,
        "scale": scale,
        "crs": crs,
        "fmt": fmt,
        "file_per_band": file_per_band,
        "target_pixels": target_pixels,
    }


# ── NiceGUI 页面定义 ─────────────────────────────────────────────

def create_ui():
    """创建 NiceGUI 页面结构。"""
    from nicegui import ui, run, app
    from fastapi.responses import FileResponse
    from urllib.parse import quote

    @app.get("/preview-tif")
    async def preview_tif(filepath: str = ""):
        """直接返回 TIFF 的 PNG 预览图片，供新标签页打开。"""
        if not filepath:
            return {"error": "缺少 filepath 参数"}
        png_path = tif_to_preview_png(filepath, max_size=1200)
        if png_path is None:
            return {"error": "无法生成预览（需要 rasterio + Pillow）"}
        return FileResponse(png_path, media_type="image/png")

    @ui.page("/")
    def index():
        # 页面容器：居中、最大宽 900px
        with ui.column().classes("w-full max-w-3xl mx-auto px-4 py-4"):

            # ── 标题 ──
            ui.markdown("# Dynamic World V1 下载工具").classes("text-2xl font-bold mb-1")
            ui.markdown("基于 Google Earth Engine，按坐标下载土地利用分类数据").classes("text-sm text-gray-500 mb-6")

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
                    reader = csv.DictReader(io.StringIO(content))
                    points = []
                    for row in reader:
                        if not row or any(v is None for v in row.values()):
                            continue
                        first_val = next(iter(row.values()), "").strip() if row else ""
                        if not first_val or first_val.startswith("#"):
                            continue
                        try:
                            lon = float(row.get("lon", "").strip())
                            lat = float(row.get("lat", "").strip())
                        except (ValueError, KeyError, AttributeError):
                            continue
                        if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                            continue
                        name = row.get("name", "").strip() or f"{lon},{lat}"
                        points.append(CoordPoint(lon=lon, lat=lat, name=name))
                    # 将解析出的坐标填入文本框
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

                ui.upload(
                    label="上传 CSV",
                    auto_upload=True,
                    max_file_size=10 * 1024 * 1024,
                    on_upload=on_upload,
                ).classes("w-full")

            # ── 下载参数 ──
            with ui.card().classes("w-full p-4 mb-4"):
                ui.markdown("### 下载参数").classes("text-base font-semibold mb-3")

                # 日期行
                with ui.row().classes("gap-4 flex-wrap"):
                    start_date = ui.input(value="2024-01-01", label="起始日期").props("type=date").style("min-width:180px")
                    end_date = ui.input(value="2024-12-31", label="结束日期").props("type=date").style("min-width:180px")

                # 波段 + 合成策略
                with ui.row().classes("gap-4 flex-wrap mt-4"):
                    bands_select = ui.select(
                        options=["label", "probs", "all"],
                        value="label",
                        label="波段选择",
                    ).style("min-width:180px")
                    composite_select = ui.select(
                        options=["first", "mosaic", "mode", "mean", "median", "collection"],
                        value="first",
                        label="合成策略",
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

                # 开关
                with ui.row().classes("gap-6 flex-wrap mt-4"):
                    file_per_band_switch = ui.switch("每波段单独文件", value=True)

                # ── 恢复上次输入 ──
                mem = app.storage.user
                if mem.get("project"):
                    project_id_input.set_value(mem["project"])
                if mem.get("coords"):
                    coords_textarea.set_value(mem["coords"])
                if mem.get("start_date"):
                    start_date.set_value(mem["start_date"])
                if mem.get("end_date"):
                    end_date.set_value(mem["end_date"])
                if mem.get("bands"):
                    bands_select.set_value(mem["bands"])
                if mem.get("composite"):
                    composite_select.set_value(mem["composite"])
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
                if "file_per_band" in mem:
                    file_per_band_switch.set_value(mem["file_per_band"])

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
                    mem["start_date"] = start_date.value
                    mem["end_date"] = end_date.value
                    mem["bands"] = bands_select.value
                    mem["composite"] = composite_select.value
                    mem["scale"] = scale_input.value
                    mem["target_pixels"] = target_pixels_input.value
                    mem["format"] = format_select.value
                    mem["crs"] = crs_input.value
                    mem["file_per_band"] = file_per_band_switch.value
                    mem["output"] = output_input.value

                    try:
                        if not coords_textarea.value:
                            ui.notify("请输入坐标或上传 CSV 文件", type="warning")
                            return
                        points = parse_coords(coords_textarea.value)

                        if not points:
                            ui.notify("请输入坐标或上传 CSV 文件", type="warning")
                            return

                        params = build_params(
                            start_date=start_date.value or "2024-01-01",
                            end_date=end_date.value or "2024-12-31",
                            bands=bands_select.value or "label",
                            composite=composite_select.value or "first",
                            scale=scale_input.value or 10,
                            crs=crs_input.value or None,
                            fmt=format_select.value or "GEO_TIFF",
                            file_per_band=file_per_band_switch.value,
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

                def _render_color_legend(stats: dict):
                    """渲染比色卡 HTML 表格图例。

                    遍历 DW_CATEGORIES 中全部 9 个类别（0-8），
                    对 stats 中不存在的类别显示 "-"。
                    当 stats 无 categories 时（probs 文件）显示纯参考比色卡。
                    """
                    rows_html_parts = []
                    categories = stats.get("categories", {})
                    for vi in range(9):
                        name = DW_CATEGORIES[vi]
                        r, g, b = DW_COLORS[vi]
                        if vi in categories:
                            cat = categories[vi]
                            pixels_str = f"{cat['pixels']:,}"
                            pct_str = f"{cat['pct']}%"
                        else:
                            pixels_str = "-"
                            pct_str = "-"
                        rows_html_parts.append(
                            f'<tr>'
                            f'<td style="padding:4px 8px;">{name}</td>'
                            f'<td style="padding:4px 8px; text-align:center;">'
                            f'<span style="display:inline-block; width:20px; height:20px; '
                            f'background-color:rgb({r},{g},{b}); border:1px solid #999;"></span>'
                            f'</td>'
                            f'<td style="padding:4px 8px; text-align:right;">{pixels_str}</td>'
                            f'<td style="padding:4px 8px; text-align:right;">{pct_str}</td>'
                            f'</tr>'
                        )
                    rows_html = "".join(rows_html_parts)
                    total = stats.get("total", 0)
                    html = (
                        f'<table style="border-collapse:collapse; width:100%; font-size:13px; margin-top:12px;">'
                        f'<thead>'
                        f'<tr style="border-bottom:2px solid #ddd;">'
                        f'<th style="padding:4px 8px; text-align:left;">类别</th>'
                        f'<th style="padding:4px 8px; text-align:center;">颜色</th>'
                        f'<th style="padding:4px 8px; text-align:right;">像素数</th>'
                        f'<th style="padding:4px 8px; text-align:right;">占比</th>'
                        f'</tr>'
                        f'</thead>'
                        f'<tbody>{rows_html}</tbody>'
                        f'<tfoot>'
                        f'<tr style="border-top:2px solid #ddd; font-weight:bold;">'
                        f'<td colspan="2" style="padding:6px 8px;">合计</td>'
                        f'<td style="padding:6px 8px; text-align:right;">{total:,}</td>'
                        f'<td style="padding:6px 8px; text-align:right;">100%</td>'
                        f'</tr>'
                        f'</tfoot>'
                        f'</table>'
                    )
                    ui.html(html)

                def _render_gradient_bar(vmin: float, vmax: float):
                    """渲染灰度-概率对照条。从左(黑=低概率)到右(白=高概率)。"""
                    html = (
                        f'<div style="margin-top:8px; font-size:12px;">'
                        f'<div style="display:flex; justify-content:space-between; margin-bottom:2px;">'
                        f'<span>{vmin:.2f}</span><span style="color:#888;">概率</span><span>{vmax:.2f}</span>'
                        f'</div>'
                        f'<div style="height:20px; background:linear-gradient(to right, #000, #fff); '
                        f'border:1px solid #ccc; border-radius:2px;"></div>'
                        f'<div style="display:flex; justify-content:space-between; margin-top:2px; color:#888;">'
                        f'<span>低</span><span>高</span>'
                        f'</div>'
                        f'</div>'
                    )
                    ui.html(html)

                def show_preview(filepath: str):
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

                    stats = get_tif_stats(filepath)
                    is_multiband = stats and stats.get("data_type") == "probs_multiband"

                    def make_png(band_idx=None):
                        return tif_to_preview_png(filepath, max_size=900, band_index=band_idx)

                    png_path = make_png()
                    if png_path is None:
                        ui.notify("无法生成预览（需要 rasterio + Pillow）", type="warning")
                        return
                    with ui.dialog() as dialog, ui.card().classes("p-4").style("width:90vw; max-width:90vw"):
                        ui.markdown(f"### {os.path.basename(filepath)}")
                        if is_multiband:
                            band_labels = list(PROBS_BANDS) + ["彩色映射 (argmax)"]
                            ui.select(
                                options=band_labels,
                                value="彩色映射 (argmax)",
                                label="波段选择",
                                on_change=lambda e: refresh_image(make_png(
                                    None if e.value == "彩色映射 (argmax)" else band_labels.index(e.value)
                                )),
                            ).style("width:260px").classes("mb-2")
                        with ui.row().style("display:flex; gap:20px; width:100%"):
                            with ui.column().style("flex:0 0 62%") as image_col:
                                ui.image(png_path).style("width:100%; object-fit:contain")
                            with ui.column().style("width:35%; min-width:260px") as stats_col:
                                if stats:
                                    if stats.get("data_type") == "probs":
                                        _render_color_legend(stats)
                                        ui.html("<div style='height:8px'></div>")
                                        _render_gradient_bar(stats["min"], stats["max"])
                                        ui.label(f"总像素: {stats['total']:,}").classes("text-sm mt-2")
                                        ui.label(f"最小值: {stats['min']}").classes("text-xs")
                                        ui.label(f"最大值: {stats['max']}").classes("text-xs")
                                        ui.label(f"均值: {stats['mean']}").classes("text-xs")
                                        ui.label(f"标准差: {stats['std']}").classes("text-xs")
                                    elif stats.get("data_type") == "probs_multiband":
                                        _render_color_legend(stats)
                                        ui.html("<div style='height:8px'></div>")
                                        _render_gradient_bar(0.0, 1.0)
                                        ui.label(f"总像素: {stats['total']:,}").classes("text-sm mt-2")
                                        for name, bs in stats["bands"].items():
                                            ui.label(
                                                f"{name}: μ={bs['mean']:.3f} σ={bs['std']:.3f}"
                                            ).classes("text-xs")
                                    else:
                                        _render_color_legend(stats)
                                        ui.label(f"总像素: {stats['total']:,}").classes("text-sm mt-2")
                                        for vi in sorted(stats["categories"].keys()):
                                            cat = stats["categories"][vi]
                                            ui.label(f"{cat['name']}: {cat['pixels']:,} ({cat['pct']}%)").classes("text-xs")

                        def refresh_image(new_path):
                            image_col.clear()
                            with image_col:
                                ui.image(new_path).style("width:100%; object-fit:contain")
                    dialog.open()

                # 浏览状态变量（在闭包之前定义，供 nonlocal 使用）
                current_browse_path = None

                def navigate_to(path: str):
                    """导航到指定目录并刷新文件列表。"""
                    nonlocal current_browse_path
                    current_browse_path = path
                    browse_dir_input.value = path
                    refresh_file_list()

                def refresh_file_list():
                    """刷新文件列表：使用 list_dir_contents 展示目录和文件。"""
                    nonlocal current_browse_path
                    files_container.clear()
                    browse_dir = browse_dir_input.value or "./output"
                    current_browse_path = browse_dir
                    items = list_dir_contents(browse_dir)
                    with files_container:
                        # "上一层"按钮：根目录时隐藏（放在空目录判断之前，确保空目录也能返回）
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
                                with ui.row().classes("gap-2 items-center w-full py-0.5"):
                                    ui.button(
                                        f"📄 {item['name']}  ({item['size_mb']:.1f} MB)",
                                        on_click=lambda _, fp=item['path']: ui.navigate.to(
                                            f"/preview-tif?filepath={quote(fp, safe='')}", new_tab=True
                                        ),
                                    ).props("flat size=sm")
                                    ui.button(
                                        "📊",
                                        on_click=lambda _, fp=item['path']: show_preview(fp),
                                    ).props("flat size=sm dense").tooltip("查看统计信息与比色卡")
                                    ui.label(item["modified"]).classes("text-xs text-gray-400")

                with ui.row().classes("items-end gap-2 w-full mb-3"):
                    browse_dir_input = ui.input(label="浏览目录", value="./output").classes("grow")
                    ui.button("查看", on_click=refresh_file_list, icon="folder_open").props("flat size=sm")
                    ui.button("", on_click=refresh_file_list, icon="refresh").props("flat round size=sm")

                refresh_file_list()

            # ── 页脚 ──
            ui.markdown("*Powered by Google Earth Engine + Dynamic World V1 + NiceGUI*").classes("text-xs text-gray-400 text-center mt-2")

    return ui


def main():
    """启动 NiceGUI Web 服务器。"""
    create_ui()
    from nicegui import ui
    ui.run(title="Dynamic World Downloader", host="127.0.0.1", port=8000, reload=False, show=False, storage_secret="dw-downloader-2026")


if __name__ == "__main__":
    main()
if __name__ == "__mp_main__":
    main()
