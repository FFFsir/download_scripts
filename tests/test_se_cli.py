"""SatelliteEmbedding cli.py 单元测试。"""
import argparse
import tempfile
import os
from unittest.mock import patch, MagicMock
import pytest
from SatelliteEmbedding.cli import build_parser


class TestBuildParser:
    """argparse 参数解析测试。"""

    def test_no_args_ok(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.coords is None
        assert args.project is None

    def test_list_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--list", "-o", "./out"])
        assert args.list is True
        assert args.output == "./out"

    def test_default_values(self):
        parser = build_parser()
        args = parser.parse_args(["-c", "108.95,34.25", "-p", "test-proj"])
        assert args.output == "./output"
        assert args.year == 2024
        assert args.years is None
        assert args.buffer == 640
        assert args.bands == "all"
        assert args.scale == 10
        assert args.crs is None
        assert args.format == "GEO_TIFF"
        assert args.cross_year == "first"

    def test_custom_values(self):
        parser = build_parser()
        args = parser.parse_args([
            "-c", "coords.csv", "-p", "my-proj", "-o", "/tmp/out",
            "-y", "2023", "--years", "2022,2023,2024",
            "-b", "1000", "--bands", "B1,B2,B3", "-s", "30",
            "--crs", "EPSG:3857", "-f", "ZIPPED_GEO_TIFF",
            "--cross-year", "median",
        ])
        assert args.coords == "coords.csv"
        assert args.project == "my-proj"
        assert args.year == 2023
        assert args.years == "2022,2023,2024"
        assert args.buffer == 1000
        assert args.bands == "B1,B2,B3"
        assert args.scale == 30
        assert args.crs == "EPSG:3857"
        assert args.format == "ZIPPED_GEO_TIFF"
        assert args.cross_year == "median"

    def test_short_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "-c", "108.95,34.25", "-p", "proj", "-o", "./out",
            "-y", "2022", "-b", "200", "-s", "20", "-f", "NPY",
        ])
        assert args.coords == "108.95,34.25"
        assert args.project == "proj"
        assert args.year == 2022
        assert args.buffer == 200
        assert args.scale == 20
        assert args.format == "NPY"

    def test_cross_year_choices(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["-c", "108,34", "-p", "proj", "--cross-year", "invalid"])

    def test_format_choices(self):
        parser = build_parser()
        args = parser.parse_args(["-c", "108,34", "-p", "proj", "-f", "GEO_TIFF"])
        assert args.format == "GEO_TIFF"


class TestMain:
    """main() 函数集成测试。"""

    @patch("SatelliteEmbedding.cli.download_single_point")
    @patch("SatelliteEmbedding.cli.setup_logging")
    @patch("SatelliteEmbedding.cli.init_gee")
    def test_main_success_flow(self, mock_init, mock_setup_logging, mock_download):
        from SatelliteEmbedding.cli import main
        from SatelliteEmbedding.core import DownloadResult, CoordPoint

        mock_download.side_effect = [
            DownloadResult(point=CoordPoint(lon=108.95, lat=34.25, name="西安"),
                           success=True, filepath="out/西安.tif", size_mb=5.0, elapsed_sec=3.0),
            DownloadResult(point=CoordPoint(lon=116.40, lat=39.90, name="北京"),
                           success=True, filepath="out/北京.tif", size_mb=4.5, elapsed_sec=2.8),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["se-cli", "-c", "108.95,34.25;116.40,39.90", "-p", "test-proj", "-o", tmpdir]):
                result = main()
                assert result == 0

    @patch("SatelliteEmbedding.cli.download_single_point")
    @patch("SatelliteEmbedding.cli.setup_logging")
    @patch("SatelliteEmbedding.cli.init_gee")
    def test_main_partial_failure(self, mock_init, mock_setup_logging, mock_download):
        from SatelliteEmbedding.cli import main
        from SatelliteEmbedding.core import DownloadResult, CoordPoint

        mock_download.side_effect = [
            DownloadResult(point=CoordPoint(lon=108.95, lat=34.25, name="西安"),
                           success=True, filepath="out/西安.tif", size_mb=5.0, elapsed_sec=3.0),
            DownloadResult(point=CoordPoint(lon=116.40, lat=39.90, name="北京"),
                           success=False, error="无可用影像"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["se-cli", "-c", "108.95,34.25;116.40,39.90", "-p", "test-proj", "-o", tmpdir]):
                result = main()
                assert result == 1
                assert os.path.exists(os.path.join(tmpdir, "download_errors.csv"))

    @patch("SatelliteEmbedding.cli.init_gee")
    def test_main_no_valid_coords(self, mock_init):
        from SatelliteEmbedding.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["se-cli", "-c", "200,100;300,200", "-p", "test-proj", "-o", tmpdir]):
                with pytest.raises(SystemExit):
                    main()

    @patch("SatelliteEmbedding.cli.init_gee")
    def test_main_missing_coords(self, mock_init):
        from SatelliteEmbedding.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["se-cli", "-p", "test-proj", "-o", tmpdir]):
                result = main()
                assert result == 2

    @patch("SatelliteEmbedding.cli.init_gee")
    def test_main_missing_project(self, mock_init):
        from SatelliteEmbedding.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["se-cli", "-c", "108,34", "-o", tmpdir]):
                result = main()
                assert result == 2

    @patch("SatelliteEmbedding.cli.list_dir_contents")
    def test_main_list_mode(self, mock_list):
        from SatelliteEmbedding.cli import main
        mock_list.return_value = []
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["se-cli", "--list", "-o", tmpdir]):
                result = main()
                assert result == 0
