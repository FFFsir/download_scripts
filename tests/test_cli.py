"""cli.py 单元测试。"""
import argparse
import tempfile
import os
from unittest.mock import patch, MagicMock
import pytest
from DynamicWorld.cli import build_parser


class TestBuildParser:
    """argparse 参数解析测试。"""

    def test_no_args_ok(self):
        """无参数时不再报错（支持 --list / --info 模式）。"""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.coords is None
        assert args.project is None

    def test_list_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--list", "-o", "./out"])
        assert args.list is True
        assert args.output == "./out"

    def test_info_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--info", "test.tif"])
        assert args.info == "test.tif"

    def test_default_values(self):
        parser = build_parser()
        args = parser.parse_args(["-c", "108.95,34.25", "-p", "test-proj"])
        assert args.output == "./output"
        assert args.start_date == "2024-01-01"
        assert args.end_date == "2024-12-31"
        assert args.buffer == 500
        assert args.bands == "label"
        assert args.scale == 10
        assert args.crs is None
        assert args.format == "GEO_TIFF"
        assert args.file_per_band is True
        assert args.composite == "first"

    def test_custom_values(self):
        parser = build_parser()
        args = parser.parse_args([
            "-c", "coords.csv", "-p", "my-proj", "-o", "/tmp/out",
            "--start-date", "2024-06-01", "--end-date", "2024-06-30",
            "-b", "1000", "--bands", "probs", "-s", "30",
            "--crs", "EPSG:3857", "-f", "ZIPPED_GEO_TIFF",
            "--no-file-per-band", "--composite", "median",
        ])
        assert args.coords == "coords.csv"
        assert args.project == "my-proj"
        assert args.output == "/tmp/out"
        assert args.start_date == "2024-06-01"
        assert args.buffer == 1000
        assert args.bands == "probs"
        assert args.scale == 30
        assert args.crs == "EPSG:3857"
        assert args.format == "ZIPPED_GEO_TIFF"
        assert args.file_per_band is False
        assert args.composite == "median"

    def test_short_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "-c", "108.95,34.25", "-p", "proj", "-o", "./out",
            "-b", "200", "-s", "20", "-f", "NPY",
        ])
        assert args.coords == "108.95,34.25"
        assert args.project == "proj"
        assert args.output == "./out"
        assert args.buffer == 200
        assert args.scale == 20
        assert args.format == "NPY"


class TestMain:
    """main() 函数集成测试。"""

    @patch("DynamicWorld.cli.download_single_point")
    @patch("DynamicWorld.cli.setup_logging")
    @patch("DynamicWorld.cli.init_gee")
    def test_main_success_flow(self, mock_init, mock_setup_logging, mock_download):
        from DynamicWorld.cli import main
        from DynamicWorld.core import DownloadResult, CoordPoint

        mock_download.side_effect = [
            DownloadResult(point=CoordPoint(lon=108.95, lat=34.25, name="西安"),
                           success=True, filepath="out/西安.tif", size_mb=5.0, elapsed_sec=3.0),
            DownloadResult(point=CoordPoint(lon=116.40, lat=39.90, name="北京"),
                           success=True, filepath="out/北京.tif", size_mb=4.5, elapsed_sec=2.8),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["cli.py", "-c", "108.95,34.25;116.40,39.90", "-p", "test-proj", "-o", tmpdir]):
                result = main()
                assert result == 0

    @patch("DynamicWorld.cli.download_single_point")
    @patch("DynamicWorld.cli.setup_logging")
    @patch("DynamicWorld.cli.init_gee")
    def test_main_partial_failure(self, mock_init, mock_setup_logging, mock_download):
        from DynamicWorld.cli import main
        from DynamicWorld.core import DownloadResult, CoordPoint

        mock_download.side_effect = [
            DownloadResult(point=CoordPoint(lon=108.95, lat=34.25, name="西安"),
                           success=True, filepath="out/西安.tif", size_mb=5.0, elapsed_sec=3.0),
            DownloadResult(point=CoordPoint(lon=116.40, lat=39.90, name="北京"),
                           success=False, error="无可用影像"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["cli.py", "-c", "108.95,34.25;116.40,39.90", "-p", "test-proj", "-o", tmpdir]):
                result = main()
                assert result == 1
                assert os.path.exists(os.path.join(tmpdir, "download_errors.csv"))

    @patch("DynamicWorld.cli.init_gee")
    def test_main_no_valid_coords(self, mock_init):
        from DynamicWorld.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["cli.py", "-c", "200,100;300,200", "-p", "test-proj", "-o", tmpdir]):
                with pytest.raises(SystemExit):
                    main()
