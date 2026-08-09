"""Dynamic World V1 下载工具 -- CLI 命令行入口。

使用方式:
    uv run dw-cli -c "108.95,34.25;116.40,39.90" -p my-project
    uv run dw-cli -c coords.csv -p my-project --bands probs --composite mean
    uv run dw-cli --list -o ./output
    uv run dw-cli --info output/121.4025,25.1947.tif
"""

import argparse
import logging
import sys

from DynamicWorld.core import (
    init_gee,
    parse_coords,
    setup_logging,
    download_single_point,
    write_error_csv,
    list_tif_files,
    get_tif_stats,
)


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="gee-dw-downloader",
        description="Dynamic World V1 遥感影像批量下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  uv run dw-cli -c "108.95,34.25" -p my-project
  uv run dw-cli -c coords.csv -p my-project --bands probs --composite mean
  uv run dw-cli --list -o ./output
  uv run dw-cli --info output/108.95,34.25.tif
        """,
    )
    parser.add_argument("-c", "--coords", default=None, help="坐标输入: CSV 文件路径或分号分隔的坐标字符串")
    parser.add_argument("-p", "--project", default=None, help="Google Cloud Project ID")
    parser.add_argument("-o", "--output", default="./output", help="输出目录 (默认: ./output)")
    parser.add_argument("--start-date", default="2024-01-01", help="起始日期 YYYY-MM-DD (默认: 2024-01-01)")
    parser.add_argument("--end-date", default="2024-12-31", help="结束日期 YYYY-MM-DD (默认: 2024-12-31)")
    parser.add_argument("-b", "--buffer", type=int, default=500, help="ROI 缓冲区半径(米) (默认: 500)")
    parser.add_argument("--bands", choices=["label", "probs", "all"], default="label", help="下载波段 (默认: label)")
    parser.add_argument("-s", "--scale", type=int, default=10, help="输出分辨率(米/像素) (默认: 10)")
    parser.add_argument("--crs", default=None, help="输出坐标参考系 (默认: 自动根据坐标选择 UTM 投影，极地区域回退到 EPSG:4326)")
    parser.add_argument("-f", "--format", choices=["GEO_TIFF", "ZIPPED_GEO_TIFF", "NPY"], default="GEO_TIFF", help="输出格式 (默认: GEO_TIFF)")
    parser.add_argument("--file-per-band", default=True, action=argparse.BooleanOptionalAction, help="每个波段单独文件")
    parser.add_argument("--composite", choices=["first", "mosaic", "mode", "mean", "median", "collection"], default="first", help="影像合成策略 (默认: first; collection=逐景下载)")
    parser.add_argument("--list", action="store_true", help="列出输出目录中已下载的文件")
    parser.add_argument("--info", default=None, metavar="FILE", help="查看指定 tif 文件的地物类别统计")
    return parser


def cmd_list(output_dir: str) -> int:
    """列出已下载文件。"""
    files = list_tif_files(output_dir)
    if not files:
        print(f"目录 '{output_dir}' 中没有已下载的文件。")
        return 0
    print(f"\n已下载文件 ({output_dir}):")
    print(f"{'文件':<40} {'大小':>10} {'修改时间':>20}")
    print("-" * 72)
    for f in files:
        print(f"{f['name']:<40} {f['size_mb']:>8.1f}MB {f['modified']:>20}")
    total_mb = sum(f["size_mb"] for f in files)
    print("-" * 72)
    print(f"共 {len(files)} 个文件, 总计 {total_mb:.1f} MB")
    return 0


def cmd_info(filepath: str) -> int:
    """查看单个文件的地物统计。"""
    stats = get_tif_stats(filepath)
    if stats is None:
        print("无法读取文件。请确认文件为 label 波段 GeoTIFF，且已安装 rasterio/numpy。")
        return 1
    print(f"\n文件: {filepath}")
    print(f"总像素: {stats['total']:,}")
    print(f"\n{'值':>3} {'类别':<10} {'像素数':>12} {'占比':>8}")
    print("-" * 40)
    for vi in sorted(stats["categories"].keys()):
        cat = stats["categories"][vi]
        print(f"{vi:>3} {cat['name']:<10} {cat['pixels']:>12,} {cat['pct']:>7.1f}%")
    return 0


def cmd_download(args) -> int:
    """CLI 下载主流程。"""
    if not args.coords:
        print("[错误] 下载模式需要 --coords / -c 参数")
        return 2
    if not args.project:
        print("[错误] 下载模式需要 --project / -p 参数")
        return 2

    logging.info(f"正在初始化 GEE (project={args.project})...")
    init_gee(args.project)

    points = parse_coords(args.coords)
    if not points:
        logging.error("未解析到任何有效坐标点，退出。")
        sys.exit(2)

    logging.info(f"成功解析 {len(points)} 个坐标点。")
    setup_logging(args.output)

    params = {
        "start_date": args.start_date, "end_date": args.end_date,
        "buffer": args.buffer, "bands": args.bands, "composite": args.composite,
        "scale": args.scale, "crs": args.crs, "fmt": args.format,
        "file_per_band": args.file_per_band,
    }

    results = []
    total = len(points)
    for i, point in enumerate(points, 1):
        logging.info(f"下载中: [{i}/{total}] {point.name} ({point.lon},{point.lat})")
        result = download_single_point(point, args.output, params)
        results.append(result)
        if result.success:
            logging.info(f"  完成: {result.filepath} ({result.size_mb:.1f}MB, {result.elapsed_sec:.1f}s)")
        else:
            logging.warning(f"  失败: {result.error}")

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]

    print(f"\n========== 下载汇总 ==========")
    print(f"  总计: {len(results)} 点")
    print(f"  成功: {len(successes)} 点")
    print(f"  失败: {len(failures)} 点")
    total_mb = sum(r.size_mb for r in successes)
    total_sec = sum(r.elapsed_sec for r in successes)
    print(f"  下载总量: {total_mb:.1f} MB")
    print(f"  总耗时: {total_sec:.1f} s")
    print("================================")

    if failures:
        write_error_csv(args.output, failures)
        return 1
    return 0


def main() -> int:
    """CLI 入口：根据参数分发到下载/列表/查看模式。"""
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        return cmd_list(args.output)
    if args.info:
        return cmd_info(args.info)
    return cmd_download(args)


if __name__ == "__main__":
    sys.exit(main())
