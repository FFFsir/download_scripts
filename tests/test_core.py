"""core.py 单元测试。"""
import pytest
from DynamicWorld.core import CoordPoint, DownloadResult


class TestCoordPoint:
    """CoordPoint dataclass 测试。"""

    def test_create_with_name(self):
        p = CoordPoint(lon=108.95, lat=34.25, name="西安")
        assert p.lon == 108.95
        assert p.lat == 34.25
        assert p.name == "西安"

    def test_create_without_name(self):
        p = CoordPoint(lon=108.95, lat=34.25, name="108.95,34.25")
        assert p.name == "108.95,34.25"

    def test_negative_coordinates(self):
        p = CoordPoint(lon=-73.935242, lat=40.730610, name="纽约")
        assert p.lon == -73.935242
        assert p.lat == 40.730610


class TestDownloadResult:
    """DownloadResult dataclass 测试。"""

    def test_success_result(self):
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        r = DownloadResult(
            point=point, success=True,
            filepath="output/西安_label.tif", size_mb=5.2, elapsed_sec=3.1
        )
        assert r.success is True
        assert r.filepath == "output/西安_label.tif"
        assert r.size_mb == 5.2
        assert r.elapsed_sec == 3.1
        assert r.error is None

    def test_failure_result(self):
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        r = DownloadResult(
            point=point, success=False,
            error="认证失败: Invalid credentials"
        )
        assert r.success is False
        assert r.filepath is None
        assert r.size_mb == 0.0
        assert r.elapsed_sec == 0.0
        assert r.error == "认证失败: Invalid credentials"

    def test_default_values(self):
        point = CoordPoint(lon=0, lat=0, name="原点")
        r = DownloadResult(point=point, success=False)
        assert r.filepath is None
        assert r.size_mb == 0.0
        assert r.elapsed_sec == 0.0
        assert r.error is None


import sys
from unittest.mock import patch, MagicMock
from DynamicWorld.core import init_gee


class TestInitGee:
    """init_gee 测试。"""

    @patch("DynamicWorld.core.ee")
    def test_init_gee_success(self, mock_ee):
        init_gee("my-project-123")
        mock_ee.Authenticate.assert_called_once()
        mock_ee.Initialize.assert_called_once_with(project="my-project-123")

    @patch("DynamicWorld.core.ee")
    def test_init_gee_permission_error_exits(self, mock_ee):
        mock_ee.EEException = type("EEException", (Exception,), {})
        mock_ee.Initialize.side_effect = mock_ee.EEException("Permission denied")
        with pytest.raises(SystemExit) as exc_info:
            init_gee("bad-project")
        assert exc_info.value.code == 1

    @patch("DynamicWorld.core.ee")
    def test_init_gee_auth_error_exits(self, mock_ee):
        mock_ee.EEException = type("EEException", (Exception,), {})
        mock_ee.Authenticate.side_effect = mock_ee.EEException("Authentication failed")
        with pytest.raises(SystemExit) as exc_info:
            init_gee("any-project")
        assert exc_info.value.code == 1


import os
import tempfile
from DynamicWorld.core import parse_coords


class TestParseCoords:
    """parse_coords 测试。"""

    def test_parse_csv_file(self):
        csv_path = os.path.join(os.path.dirname(__file__), "fixtures", "coords.csv")
        result = parse_coords(csv_path)
        assert len(result) == 3
        assert result[0] == CoordPoint(lon=108.95, lat=34.25, name="西安")
        assert result[1] == CoordPoint(lon=116.40, lat=39.90, name="北京")
        assert result[2] == CoordPoint(lon=121.47, lat=31.23, name="上海")

    def test_parse_csv_with_comments_and_blanks(self):
        csv_path = os.path.join(os.path.dirname(__file__), "fixtures", "coords_with_comments.csv")
        result = parse_coords(csv_path)
        assert len(result) == 3

    def test_parse_csv_auto_name(self):
        csv_content = "lon,lat\n108.95,34.25\n116.40,39.90\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            tmp_path = f.name
        try:
            result = parse_coords(tmp_path)
            assert len(result) == 2
            assert result[0].name == "108.95,34.25"
            assert result[1].name == "116.4,39.9"
        finally:
            os.unlink(tmp_path)

    def test_parse_string_semicolon_separated(self):
        result = parse_coords("108.95,34.25;116.40,39.90;121.47,31.23")
        assert len(result) == 3
        assert result[0].name == "108.95,34.25"
        assert result[1].name == "116.4,39.9"
        assert result[2].name == "121.47,31.23"

    def test_parse_string_with_spaces(self):
        result = parse_coords("108.95, 34.25 ; 116.40, 39.90")
        assert len(result) == 2
        assert result[0].lat == 34.25

    def test_skip_invalid_lon(self):
        result = parse_coords("108.95,34.25;200.0,30.0;-200.0,30.0")
        assert len(result) == 1
        assert result[0].name == "108.95,34.25"

    def test_skip_invalid_lat(self):
        result = parse_coords("108.95,34.25;110.0,100.0;110.0,-95.0")
        assert len(result) == 1
        assert result[0].name == "108.95,34.25"

    def test_skip_invalid_format(self):
        result = parse_coords("108.95,34.25;abc,def;110.0")
        assert len(result) == 1

    def test_all_invalid_returns_empty(self):
        result = parse_coords("abc,def;200.0,100.0")
        assert result == []

    def test_empty_string_returns_empty(self):
        result = parse_coords("")
        assert result == []

    def test_file_not_found_treated_as_string(self):
        result = parse_coords("108.95,34.25;116.40,39.90")
        assert len(result) == 2


from DynamicWorld.core import create_roi, build_image


class TestCreateRoi:
    """create_roi 测试。"""

    @patch("DynamicWorld.core.ee")
    def test_create_roi_returns_geometry(self, mock_ee):
        roi = create_roi(108.95, 34.25, buffer_m=500)
        assert isinstance(roi, MagicMock)

    @patch("DynamicWorld.core.ee")
    def test_create_roi_default_buffer(self, mock_ee):
        roi = create_roi(0, 0)
        assert isinstance(roi, MagicMock)


class TestBuildImage:
    """build_image 测试。"""

    @patch("DynamicWorld.core.ee")
    def test_build_image_returns_image(self, mock_ee):
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.first.return_value = mock_image
        mock_ee.ImageCollection.return_value = mock_collection
        image = build_image(roi, "2024-01-01", "2024-12-31", bands="label", composite="first")
        assert image is mock_image

    @patch("DynamicWorld.core.ee")
    def test_build_image_all_bands_select_none(self, mock_ee):
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.first.return_value = mock_image
        mock_ee.ImageCollection.return_value = mock_collection
        image = build_image(roi, "2024-01-01", "2024-12-31", bands="all", composite="first")
        assert image is mock_image
        mock_collection.select.assert_not_called()

    @patch("DynamicWorld.core.ee")
    def test_build_image_composite_median(self, mock_ee):
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.median.return_value = mock_image
        mock_ee.ImageCollection.return_value = mock_collection
        build_image(roi, "2024-01-01", "2024-12-31", bands="label", composite="median")
        mock_collection.median.assert_called_once()

    @patch("DynamicWorld.core.ee")
    def test_build_image_composite_mode(self, mock_ee):
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.mode.return_value = mock_image
        mock_ee.ImageCollection.return_value = mock_collection
        build_image(roi, "2024-01-01", "2024-12-31", bands="label", composite="mode")
        mock_collection.mode.assert_called_once()

    @patch("DynamicWorld.core.ee")
    def test_build_image_composite_mean(self, mock_ee):
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.mean.return_value = mock_image
        mock_ee.ImageCollection.return_value = mock_collection
        build_image(roi, "2024-01-01", "2024-12-31", bands="label", composite="mean")
        mock_collection.mean.assert_called_once()

    @patch("DynamicWorld.core.ee")
    def test_build_image_composite_mosaic(self, mock_ee):
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.mosaic.return_value = mock_image
        mock_ee.ImageCollection.return_value = mock_collection
        build_image(roi, "2024-01-01", "2024-12-31", bands="label", composite="mosaic")
        mock_collection.mosaic.assert_called_once()

    @patch("DynamicWorld.core.ee")
    def test_build_image_no_image_found_returns_none(self, mock_ee):
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.first.return_value = None
        mock_ee.ImageCollection.return_value = mock_collection
        image = build_image(roi, "2024-01-01", "2024-12-31", bands="label", composite="first")
        assert image is None

    @patch("DynamicWorld.core.ee")
    def test_build_image_invalid_composite_raises(self, mock_ee):
        roi = MagicMock()
        with pytest.raises(ValueError, match="不支持的合成模式"):
            build_image(roi, "2024-01-01", "2024-12-31", composite="unknown")


import time
import requests
from DynamicWorld.core import download_image, download_single_point


class TestDownloadImage:
    """download_image 测试。"""

    @patch("DynamicWorld.core.requests")
    @patch("DynamicWorld.core.ee")
    def test_download_image_success(self, mock_ee, mock_requests):
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.content = b"fake tiff content"
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath, size = download_image(image, tmpdir, "test_point")
            assert os.path.exists(filepath)
            assert size > 0
            call_kwargs = mock_requests.get.call_args
            assert call_kwargs[1]["timeout"] == 300

    @patch("DynamicWorld.core.requests")
    @patch("DynamicWorld.core.ee")
    def test_download_image_retry_on_failure(self, mock_ee, mock_requests):
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.side_effect = [
            requests.exceptions.Timeout("timeout"),
            requests.exceptions.ConnectionError("conn"),
            type("Response", (), {"status_code": 200, "content": b"data"})(),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath, size = download_image(image, tmpdir, "test_point")
            assert os.path.exists(filepath)
            assert mock_requests.get.call_count == 3

    @patch("DynamicWorld.core.requests")
    @patch("DynamicWorld.core.ee")
    def test_download_image_all_retries_fail(self, mock_ee, mock_requests):
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.side_effect = requests.exceptions.Timeout("timeout")
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RuntimeError, match="下载失败"):
                download_image(image, tmpdir, "test_point")

    @patch("DynamicWorld.core.requests")
    @patch("DynamicWorld.core.ee")
    def test_download_image_http_error_status(self, mock_ee, mock_requests):
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.return_value.status_code = 500
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RuntimeError, match="下载失败"):
                download_image(image, tmpdir, "test_point")
        assert mock_requests.get.call_count == 3


class TestDownloadSinglePoint:
    """download_single_point 测试。"""

    @patch("DynamicWorld.core.download_image")
    @patch("DynamicWorld.core.build_image")
    @patch("DynamicWorld.core._create_square_roi")
    @patch("DynamicWorld.core.create_roi")
    def test_download_single_point_success(
        self, mock_create_roi, mock_square_roi, mock_build_image, mock_download_image
    ):
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.return_value = MagicMock()
        mock_download_image.return_value = ("/fake/path.tif", 5.2)
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "start_date": "2024-01-01", "end_date": "2024-12-31",
            "buffer": 500, "bands": "label", "composite": "first",
            "scale": 10, "crs": "EPSG:4326", "fmt": "GEO_TIFF",
            "file_per_band": True, "merge": False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = download_single_point(point, tmpdir, params)
            assert result.success is True
            assert result.point == point
            assert result.filepath == "/fake/path.tif"
            assert result.size_mb == 5.2
            assert result.elapsed_sec >= 0
            assert result.error is None

    @patch("DynamicWorld.core._create_square_roi")
    @patch("DynamicWorld.core.build_image")
    @patch("DynamicWorld.core.create_roi")
    def test_download_single_point_no_image(self, mock_create_roi, mock_build_image, mock_square_roi):
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.return_value = None
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "start_date": "2024-01-01", "end_date": "2024-12-31",
            "buffer": 500, "bands": "label", "composite": "first",
            "scale": 10, "crs": "EPSG:4326", "fmt": "GEO_TIFF",
            "file_per_band": True, "merge": False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = download_single_point(point, tmpdir, params)
            assert result.success is False
            assert "无可用影像" in result.error

    @patch("DynamicWorld.core._create_square_roi")
    @patch("DynamicWorld.core.build_image")
    @patch("DynamicWorld.core.create_roi")
    def test_download_single_point_error_handling(self, mock_create_roi, mock_build_image, mock_square_roi):
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.side_effect = RuntimeError("GEE 服务异常")
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "start_date": "2024-01-01", "end_date": "2024-12-31",
            "buffer": 500, "bands": "label", "composite": "first",
            "scale": 10, "crs": "EPSG:4326", "fmt": "GEO_TIFF",
            "file_per_band": True, "merge": False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = download_single_point(point, tmpdir, params)
            assert result.success is False
            assert "GEE 服务异常" in result.error


import logging
from DynamicWorld.core import setup_logging, write_error_csv


class TestSetupLogging:
    """setup_logging 测试。"""

    def test_setup_logging(self):
        root = logging.getLogger()
        before = len([h for h in root.handlers if isinstance(h, logging.FileHandler)])
        tmpdir = tempfile.mkdtemp()
        try:
            setup_logging(tmpdir)
            after = len([h for h in root.handlers if isinstance(h, logging.FileHandler)])
            assert after > before
            assert os.path.exists(os.path.join(tmpdir, "download.log"))
        finally:
            for h in list(root.handlers):
                if isinstance(h, (logging.FileHandler, logging.StreamHandler)):
                    h.close()
                    root.removeHandler(h)
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestWriteErrorCsv:
    """write_error_csv 测试。"""

    def test_write_error_csv_creates_file(self):
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        error_result = DownloadResult(point=point, success=False, error="认证失败")
        with tempfile.TemporaryDirectory() as tmpdir:
            write_error_csv(tmpdir, [error_result])
            csv_path = os.path.join(tmpdir, "download_errors.csv")
            assert os.path.exists(csv_path)

    def test_write_error_csv_content(self):
        p1 = CoordPoint(lon=108.95, lat=34.25, name="西安")
        p2 = CoordPoint(lon=116.40, lat=39.90, name="北京")
        errors = [
            DownloadResult(point=p1, success=False, error="认证失败"),
            DownloadResult(point=p2, success=False, error="无可用影像"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            write_error_csv(tmpdir, errors)
            csv_path = os.path.join(tmpdir, "download_errors.csv")
            with open(csv_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "lon,lat,name,error" in content
            assert "108.95,34.25,西安,认证失败" in content
            assert "116.4,39.9,北京,无可用影像" in content

    def test_write_error_csv_empty_errors_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            write_error_csv(tmpdir, [])
            csv_path = os.path.join(tmpdir, "download_errors.csv")
            assert not os.path.exists(csv_path)


from DynamicWorld.core import list_dir_contents


class TestListDirContents:
    """list_dir_contents 单元测试。"""

    def test_nonexistent_path_returns_empty(self):
        """不存在的路径返回空列表。"""
        result = list_dir_contents("/nonexistent/path/xyz")
        assert result == []

    def test_empty_dir_returns_empty(self):
        """空目录返回空列表。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = list_dir_contents(tmpdir)
            assert result == []

    def test_files_only(self):
        """仅含 tif/zip/npy 文件的目录返回文件列表。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            for fname in ["a.tif", "b.zip", "c.npy"]:
                open(os.path.join(tmpdir, fname), "w").close()
            open(os.path.join(tmpdir, "readme.txt"), "w").close()

            result = list_dir_contents(tmpdir)
            assert len(result) == 3
            assert all(item["type"] == "file" for item in result)
            names = [item["name"] for item in result]
            assert names == ["a.tif", "b.zip", "c.npy"]

    def test_dirs_only(self):
        """仅含子目录的目录返回目录列表（排前面）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "北京"))
            os.makedirs(os.path.join(tmpdir, "上海"))

            result = list_dir_contents(tmpdir)
            assert len(result) == 2
            assert all(item["type"] == "dir" for item in result)
            names = [item["name"] for item in result]
            assert names == ["上海", "北京"]  # 按名称字母序

    def test_mixed_content_dirs_first(self):
        """混合内容：目录排在文件前面。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "subdir"))
            open(os.path.join(tmpdir, "data.tif"), "w").close()

            result = list_dir_contents(tmpdir)
            assert len(result) == 2
            assert result[0]["type"] == "dir"
            assert result[0]["name"] == "subdir"
            assert result[1]["type"] == "file"
            assert result[1]["name"] == "data.tif"

    def test_dir_item_has_path_with_sep(self):
        """目录项的 path 以分隔符结尾。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "mydir"))

            result = list_dir_contents(tmpdir)
            assert len(result) == 1
            assert result[0]["type"] == "dir"
            assert result[0]["path"].endswith(os.sep)

    def test_file_item_has_size_and_modified(self):
        """文件项包含 size_mb 和 modified 字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "test.tif")
            with open(fpath, "w") as f:
                f.write("x" * 100)

            result = list_dir_contents(tmpdir)
            assert len(result) == 1
            assert result[0]["type"] == "file"
            assert "size_mb" in result[0]
            assert result[0]["size_mb"] > 0
            assert "modified" in result[0]
            assert isinstance(result[0]["modified"], str)


from DynamicWorld.core import _get_utm_epsg


class TestGetUtmEpsg:
    """_get_utm_epsg 单元测试。"""

    def test_northern_hemisphere(self):
        """西安 (108.95, 34.25) -> UTM zone 49 北半球。"""
        assert _get_utm_epsg(108.95, 34.25) == "EPSG:32649"

    def test_southern_hemisphere(self):
        """悉尼 (151.21, -33.86) -> UTM zone 56 南半球。"""
        assert _get_utm_epsg(151.21, -33.86) == "EPSG:32756"

    def test_eastern_hemisphere(self):
        """北京 (116.40, 39.90) -> UTM zone 50。"""
        assert _get_utm_epsg(116.40, 39.90) == "EPSG:32650"

    def test_western_hemisphere(self):
        """纽约 (-73.93, 40.73) -> UTM zone 18。"""
        assert _get_utm_epsg(-73.93, 40.73) == "EPSG:32618"

    def test_far_north_fallback(self):
        """纬度 > 84° 回退到 EPSG:4326。"""
        assert _get_utm_epsg(0, 85) == "EPSG:4326"

    def test_far_south_fallback(self):
        """纬度 < -80° 回退到 EPSG:4326。"""
        assert _get_utm_epsg(0, -85) == "EPSG:4326"

    def test_zone_boundary_minus_180(self):
        """经度 -180 -> zone 1。"""
        assert _get_utm_epsg(-180, 0) == "EPSG:32601"

    def test_zone_boundary_plus_180(self):
        """经度 180 -> zone 60。"""
        assert _get_utm_epsg(180, 0) == "EPSG:32660"
