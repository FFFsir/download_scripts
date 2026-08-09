"""SatelliteEmbedding core.py 单元测试。"""
import logging
import os
import sys
import tempfile
import warnings
from unittest.mock import MagicMock, patch

import pytest
import requests
from SatelliteEmbedding.core import (
    CoordPoint,
    DownloadResult,
    _check_size_limit,
    _l2_normalize,
    build_image,
    create_roi,
    download_image,
)


class TestCoordPoint:
    """CoordPoint dataclass 测试。"""

    def test_create_with_name(self):
        p = CoordPoint(lon=108.95, lat=34.25, name="西安")
        assert p.lon == 108.95
        assert p.lat == 34.25
        assert p.name == "西安"

    def test_create_auto_name(self):
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
            filepath="output/西安_all.tif", size_mb=5.2, elapsed_sec=3.1
        )
        assert r.success is True
        assert r.filepath == "output/西安_all.tif"
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


class TestInitGee:
    """init_gee 测试。"""

    @patch("SatelliteEmbedding.core.ee")
    def test_init_gee_success(self, mock_ee):
        from SatelliteEmbedding.core import init_gee
        init_gee("my-project-123")
        mock_ee.Authenticate.assert_called_once()
        mock_ee.Initialize.assert_called_once_with(project="my-project-123")

    @patch("SatelliteEmbedding.core.ee")
    def test_init_gee_ee_exception_exits(self, mock_ee):
        from SatelliteEmbedding.core import init_gee
        mock_ee.EEException = type("EEException", (Exception,), {})
        mock_ee.Initialize.side_effect = mock_ee.EEException("Permission denied")
        with pytest.raises(SystemExit) as exc_info:
            init_gee("bad-project")
        assert exc_info.value.code == 1

    @patch("SatelliteEmbedding.core.ee")
    def test_init_gee_auth_error_exits(self, mock_ee):
        from SatelliteEmbedding.core import init_gee
        mock_ee.EEException = type("EEException", (Exception,), {})
        mock_ee.Authenticate.side_effect = mock_ee.EEException("Authentication failed")
        with pytest.raises(SystemExit) as exc_info:
            init_gee("any-project")
        assert exc_info.value.code == 1


class TestParseCoords:
    """parse_coords 测试。"""

    def test_parse_csv_file(self):
        from SatelliteEmbedding.core import parse_coords
        csv_path = os.path.join(os.path.dirname(__file__), "fixtures", "coords.csv")
        result = parse_coords(csv_path)
        assert len(result) == 3
        assert result[0] == CoordPoint(lon=108.95, lat=34.25, name="西安")
        assert result[1] == CoordPoint(lon=116.40, lat=39.90, name="北京")
        assert result[2] == CoordPoint(lon=121.47, lat=31.23, name="上海")

    def test_parse_csv_auto_name(self):
        from SatelliteEmbedding.core import parse_coords
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
        from SatelliteEmbedding.core import parse_coords
        result = parse_coords("108.95,34.25;116.40,39.90;121.47,31.23")
        assert len(result) == 3
        assert result[0].name == "108.95,34.25"
        assert result[1].name == "116.4,39.9"
        assert result[2].name == "121.47,31.23"

    def test_parse_string_with_spaces(self):
        from SatelliteEmbedding.core import parse_coords
        result = parse_coords("108.95, 34.25 ; 116.40, 39.90")
        assert len(result) == 2
        assert result[0].lat == 34.25

    def test_skip_invalid_lon(self):
        from SatelliteEmbedding.core import parse_coords
        result = parse_coords("108.95,34.25;200.0,30.0;-200.0,30.0")
        assert len(result) == 1
        assert result[0].name == "108.95,34.25"

    def test_skip_invalid_lat(self):
        from SatelliteEmbedding.core import parse_coords
        result = parse_coords("108.95,34.25;110.0,100.0;110.0,-95.0")
        assert len(result) == 1
        assert result[0].name == "108.95,34.25"

    def test_skip_invalid_format(self):
        from SatelliteEmbedding.core import parse_coords
        result = parse_coords("108.95,34.25;abc,def;110.0")
        assert len(result) == 1

    def test_all_invalid_returns_empty(self):
        from SatelliteEmbedding.core import parse_coords
        result = parse_coords("abc,def;200.0,100.0")
        assert result == []

    def test_empty_string_returns_empty(self):
        from SatelliteEmbedding.core import parse_coords
        result = parse_coords("")
        assert result == []


class TestCreateRoi:
    """create_roi 测试。"""

    @patch("SatelliteEmbedding.core.ee")
    def test_create_roi_returns_geometry(self, mock_ee):
        roi = create_roi(108.95, 34.25, buffer_m=640)
        assert isinstance(roi, MagicMock)

    @patch("SatelliteEmbedding.core.ee")
    def test_create_roi_default_buffer_is_640(self, mock_ee):
        """SE 默认 buffer 为 640m，不同于 DW 的 500m。"""
        mock_point = MagicMock()
        mock_ee.Geometry.Point.return_value = mock_point
        create_roi(0, 0)
        mock_point.buffer.assert_called_once_with(640)


class TestL2Normalize:
    """_l2_normalize 单元测试（无需 GEE）。"""

    @patch("SatelliteEmbedding.core.ee")
    def test_unit_vector_unchanged(self, mock_ee):
        """单位向量 L2 归一化后不变。"""
        mock_image = MagicMock()
        mock_norm = MagicMock()
        mock_image.pow.return_value = mock_image
        mock_image.reduce.return_value = mock_norm
        mock_norm.sqrt.return_value = mock_norm
        mock_image.divide.return_value = mock_image
        mock_image.where.return_value = mock_image

        result = _l2_normalize(mock_image)
        mock_image.pow.assert_called_once_with(2)
        mock_image.reduce.assert_called_once()
        mock_image.divide.assert_called_once_with(mock_norm)
        # where(norm.eq(0), image) 保护零向量
        mock_norm.eq.assert_called_once_with(0)
        mock_image.where.assert_called_once()

    @patch("SatelliteEmbedding.core.ee")
    def test_zero_norm_returns_original(self, mock_ee):
        """零向量归一化时返回原始影像（防 NaN）。"""
        mock_image = MagicMock()
        mock_norm = MagicMock()
        mock_image.pow.return_value = mock_image
        mock_image.reduce.return_value = mock_norm
        mock_norm.sqrt.return_value = mock_norm
        mock_divided = MagicMock()
        mock_image.divide.return_value = mock_divided  # NaN 结果
        mock_divided.where.return_value = mock_image  # where 返回原始

        result = _l2_normalize(mock_image)
        # where(norm.eq(0), image) 确保零范数时返回原始 image
        assert result is mock_image


class TestCheckSizeLimit:
    """_check_size_limit 测试。"""

    @patch("SatelliteEmbedding.core.ee")
    def test_within_limit_no_warning(self, mock_ee):
        """像素数在阈值内不触发警告。"""
        mock_roi = MagicMock()
        # 面积约 131072 * 100 = 13,107,200 m2，像素数 = 131072 / 100 * 100 = 13107 < 131072
        mock_roi.area.return_value.getInfo.return_value = 13_107_200
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _check_size_limit(mock_roi, scale=10)
            assert len(w) == 0

    @patch("SatelliteEmbedding.core.ee")
    def test_exceeds_limit_triggers_warning(self, mock_ee):
        """像素数超阈值触发警告。"""
        mock_roi = MagicMock()
        # 面积约 20,000,000 m2，像素数 = 200000，> 131072
        mock_roi.area.return_value.getInfo.return_value = 20_000_000
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _check_size_limit(mock_roi, scale=10)
            assert len(w) == 1
            assert "32MB" in str(w[0].message) or "131072" in str(w[0].message)

    @patch("SatelliteEmbedding.core.ee")
    def test_exact_threshold_no_warning(self, mock_ee):
        """恰好 131072 像素不触发警告。"""
        mock_roi = MagicMock()
        mock_roi.area.return_value.getInfo.return_value = 131072 * 100  # 100 m2 per pixel at 10m
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _check_size_limit(mock_roi, scale=10)
            assert len(w) == 0


class TestBuildImage:
    """build_image 测试。"""

    @patch("SatelliteEmbedding.core.ee")
    def test_single_year_first(self, mock_ee):
        """单年份 + first 合成。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        first_img = MagicMock()
        filtered.filter.return_value.first.return_value = first_img
        from_images_col = MagicMock()
        from_images_col.first.return_value = mock_image
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        image = build_image(roi, year=2024, bands="all", cross_year="first")
        assert image is mock_image

    @patch("SatelliteEmbedding.core.ee")
    def test_years_param_priority(self, mock_ee):
        """years 参数优先级高于 year。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        img_2023 = MagicMock()
        img_2024 = MagicMock()
        filtered.filter.return_value.first.side_effect = [img_2023, img_2024]

        from_images_col = MagicMock()
        from_images_col.first.return_value = mock_image
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        image = build_image(roi, year=2024, years=[2023, 2024], cross_year="first")
        assert mock_ee.Filter.calendarRange.call_count == 2
        assert image is mock_image

    @patch("SatelliteEmbedding.core.ee")
    def test_cross_year_mean_calls_l2_normalize(self, mock_ee):
        """cross_year='mean' 时调用 _l2_normalize。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        first_img = MagicMock()
        filtered.filter.return_value.first.return_value = first_img

        mean_img = MagicMock()
        mean_img.clip.return_value = mock_image
        from_images_col = MagicMock()
        from_images_col.mean.return_value = mean_img
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        with patch("SatelliteEmbedding.core._l2_normalize") as mock_l2:
            mock_l2.return_value = mock_image
            image = build_image(roi, year=2024, cross_year="mean")
            mock_l2.assert_called_once()
            assert image is mock_image

    @patch("SatelliteEmbedding.core.ee")
    def test_cross_year_median(self, mock_ee):
        """cross_year='median' 合成。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        first_img = MagicMock()
        filtered.filter.return_value.first.return_value = first_img

        median_img = MagicMock()
        median_img.clip.return_value = mock_image
        from_images_col = MagicMock()
        from_images_col.median.return_value = median_img
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        image = build_image(roi, year=2024, cross_year="median")
        assert image is mock_image

    @patch("SatelliteEmbedding.core.ee")
    def test_no_image_found_returns_none(self, mock_ee):
        """无可用影像返回 None。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        filtered.filter.return_value.first.return_value = None

        from_images_col = MagicMock()
        from_images_col.first.return_value = None
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        image = build_image(roi, year=2024, cross_year="first")
        assert image is None

    @patch("SatelliteEmbedding.core.ee")
    def test_invalid_cross_year_raises(self, mock_ee):
        """无效 cross_year 抛出 ValueError。"""
        roi = MagicMock()
        mock_ee.ImageCollection.return_value = MagicMock()
        with pytest.raises(ValueError, match="不支持的跨年合成模式"):
            build_image(roi, year=2024, cross_year="unknown")

    @patch("SatelliteEmbedding.core.ee")
    def test_bands_custom_selection(self, mock_ee):
        """自定义波段子集选择。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        first_img = MagicMock()
        filtered.filter.return_value.first.return_value = first_img

        from_images_col = MagicMock()
        from_images_col.first.return_value = mock_image
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        build_image(roi, year=2024, bands="B1,B2,B3", cross_year="first")
        from_images_col.select.assert_called_once_with(["B1", "B2", "B3"])

    @patch("SatelliteEmbedding.core.ee")
    def test_bands_all_does_not_select(self, mock_ee):
        """bands='all' 不调用 select。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        first_img = MagicMock()
        filtered.filter.return_value.first.return_value = first_img

        from_images_col = MagicMock()
        from_images_col.first.return_value = mock_image
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        build_image(roi, year=2024, bands="all", cross_year="first")
        from_images_col.select.assert_not_called()

    @patch("SatelliteEmbedding.core._check_size_limit")
    @patch("SatelliteEmbedding.core.ee")
    def test_scale_passed_to_check_size_limit(self, mock_ee, mock_check):
        """scale 参数正确传递给 _check_size_limit。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        first_img = MagicMock()
        filtered.filter.return_value.first.return_value = first_img

        from_images_col = MagicMock()
        from_images_col.first.return_value = mock_image
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        build_image(roi, year=2024, scale=30)
        mock_check.assert_called_once_with(roi, 30)

    @patch("SatelliteEmbedding.core._check_size_limit")
    @patch("SatelliteEmbedding.core.ee")
    def test_scale_defaults_to_10(self, mock_ee, mock_check):
        """scale 默认值为 10。"""
        roi = MagicMock()
        mock_collection = MagicMock()
        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image

        filtered = MagicMock()
        mock_collection.filterBounds.return_value = filtered
        mock_ee.ImageCollection.return_value = mock_collection
        mock_ee.Filter.calendarRange.return_value = "fake_calendar_filter"

        first_img = MagicMock()
        filtered.filter.return_value.first.return_value = first_img

        from_images_col = MagicMock()
        from_images_col.first.return_value = mock_image
        mock_ee.ImageCollection.fromImages.return_value = from_images_col

        build_image(roi, year=2024)
        mock_check.assert_called_once_with(roi, 10)


class TestDownloadImage:
    """download_image 测试。"""

    @patch("SatelliteEmbedding.core.requests")
    @patch("SatelliteEmbedding.core.ee")
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

    @patch("SatelliteEmbedding.core.requests")
    @patch("SatelliteEmbedding.core.ee")
    def test_download_image_file_per_band_false(self, mock_ee, mock_requests):
        """验证 filePerBand 固定为 False。"""
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.content = b"fake content"
        with tempfile.TemporaryDirectory() as tmpdir:
            download_image(image, tmpdir, "test_point")
            call_args = image.getDownloadURL.call_args
            # filePerBand 必须为 False
            assert call_args[0][0].get("filePerBand") is False

    @patch("SatelliteEmbedding.core.requests")
    @patch("SatelliteEmbedding.core.ee")
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

    @patch("SatelliteEmbedding.core.requests")
    @patch("SatelliteEmbedding.core.ee")
    def test_download_image_all_retries_fail(self, mock_ee, mock_requests):
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.side_effect = requests.exceptions.Timeout("timeout")
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RuntimeError, match="下载失败"):
                download_image(image, tmpdir, "test_point")

    @patch("SatelliteEmbedding.core.requests")
    @patch("SatelliteEmbedding.core.ee")
    def test_download_image_http_error_status(self, mock_ee, mock_requests):
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.return_value.status_code = 500
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RuntimeError, match="下载失败"):
                download_image(image, tmpdir, "test_point")
        assert mock_requests.get.call_count == 3

    @patch("SatelliteEmbedding.core.requests")
    @patch("SatelliteEmbedding.core.ee")
    def test_download_image_custom_params(self, mock_ee, mock_requests):
        """验证 scale/crs/fmt/region 参数正确传递。"""
        image = MagicMock()
        image.getDownloadURL.return_value = "https://storage.googleapis.com/fake/url"
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.content = b"fake"
        mock_region = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            download_image(image, tmpdir, "test", scale=30, crs="EPSG:3857",
                           fmt="ZIPPED_GEO_TIFF", region=mock_region)
            call_args = image.getDownloadURL.call_args
            params = call_args[0][0]
            assert params["scale"] == 30
            assert params["crs"] == "EPSG:3857"
            assert params["format"] == "ZIPPED_GEO_TIFF"
            assert params["region"] is mock_region


# ============================================================
# Task 6: download_single_point / setup_logging / write_error_csv / list_dir_contents
# ============================================================

from SatelliteEmbedding.core import download_single_point, setup_logging, write_error_csv, list_dir_contents


class TestDownloadSinglePoint:
    """download_single_point 测试。"""

    @patch("SatelliteEmbedding.core.download_image")
    @patch("SatelliteEmbedding.core.build_image")
    @patch("SatelliteEmbedding.core._create_square_roi")
    @patch("SatelliteEmbedding.core.create_roi")
    def test_download_single_point_success(
        self, mock_create_roi, mock_square_roi, mock_build_image, mock_download_image
    ):
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.return_value = MagicMock()
        mock_download_image.return_value = ("/fake/path.tif", 5.2)
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "year": 2024, "buffer": 640, "bands": "all",
            "cross_year": "first", "scale": 10, "crs": "EPSG:4326",
            "fmt": "GEO_TIFF",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = download_single_point(point, tmpdir, params)
            assert result.success is True
            assert result.point == point
            assert result.filepath == "/fake/path.tif"
            assert result.size_mb == 5.2
            assert result.elapsed_sec >= 0
            assert result.error is None

    @patch("SatelliteEmbedding.core.download_image")
    @patch("SatelliteEmbedding.core.build_image")
    @patch("SatelliteEmbedding.core._create_square_roi")
    @patch("SatelliteEmbedding.core.create_roi")
    def test_filename_format_includes_bands_and_cross_year(
        self, mock_create_roi, mock_square_roi, mock_build_image, mock_download_image
    ):
        """验证文件名包含 bands、cross_year、坐标、年份。"""
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.return_value = MagicMock()
        mock_download_image.return_value = ("/out/test.tif", 1.0)
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "year": 2024, "buffer": 640, "bands": "B1,B2",
            "cross_year": "mean", "scale": 10, "crs": "EPSG:4326",
            "fmt": "GEO_TIFF",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            download_single_point(point, tmpdir, params)
            call_args = mock_download_image.call_args
            name = call_args[0][2]  # 第三个位置参数是 name
            assert "B1_B2" in name or "B1,B2" in name
            assert "mean" in name
            assert "E108.95" in name
            assert "N34.25" in name
            assert "2024" in name

    @patch("SatelliteEmbedding.core._create_square_roi")
    @patch("SatelliteEmbedding.core.build_image")
    @patch("SatelliteEmbedding.core.create_roi")
    def test_download_single_point_no_image(self, mock_create_roi, mock_build_image, mock_square_roi):
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.return_value = None
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "year": 2024, "buffer": 640, "bands": "all",
            "cross_year": "first", "scale": 10, "crs": "EPSG:4326",
            "fmt": "GEO_TIFF",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = download_single_point(point, tmpdir, params)
            assert result.success is False
            assert "无可用影像" in result.error
            assert point.name in result.error

    @patch("SatelliteEmbedding.core._create_square_roi")
    @patch("SatelliteEmbedding.core.build_image")
    @patch("SatelliteEmbedding.core.create_roi")
    def test_download_single_point_error_handling(self, mock_create_roi, mock_build_image, mock_square_roi):
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.side_effect = RuntimeError("GEE 服务异常")
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "year": 2024, "buffer": 640, "bands": "all",
            "cross_year": "first", "scale": 10, "crs": "EPSG:4326",
            "fmt": "GEO_TIFF",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = download_single_point(point, tmpdir, params)
            assert result.success is False
            assert "GEE 服务异常" in result.error

    @patch("SatelliteEmbedding.core.download_image")
    @patch("SatelliteEmbedding.core.build_image")
    @patch("SatelliteEmbedding.core._create_square_roi")
    @patch("SatelliteEmbedding.core.create_roi")
    def test_years_param_passed_to_build_image(
        self, mock_create_roi, mock_square_roi, mock_build_image, mock_download_image
    ):
        """years 参数正确传递给 build_image。"""
        mock_create_roi.return_value = MagicMock()
        mock_square_roi.return_value = (MagicMock(), MagicMock())
        mock_build_image.return_value = MagicMock()
        mock_download_image.return_value = ("/fake/path.tif", 5.0)
        point = CoordPoint(lon=108.95, lat=34.25, name="西安")
        params = {
            "years": [2022, 2023, 2024], "buffer": 640, "bands": "all",
            "cross_year": "median", "scale": 10, "crs": "EPSG:4326",
            "fmt": "GEO_TIFF",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            download_single_point(point, tmpdir, params)
            call_kwargs = mock_build_image.call_args
            assert call_kwargs[1]["years"] == [2022, 2023, 2024]


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


class TestListDirContents:
    """list_dir_contents 单元测试。"""

    def test_nonexistent_path_returns_empty(self):
        result = list_dir_contents("/nonexistent/path/xyz")
        assert result == []

    def test_empty_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = list_dir_contents(tmpdir)
            assert result == []

    def test_files_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for fname in ["a.tif", "b.zip", "c.npy"]:
                open(os.path.join(tmpdir, fname), "w").close()
            open(os.path.join(tmpdir, "readme.txt"), "w").close()
            result = list_dir_contents(tmpdir)
            assert len(result) == 3
            assert all(item["type"] == "file" for item in result)
            names = [item["name"] for item in result]
            assert names == ["a.tif", "b.zip", "c.npy"]

    def test_dirs_first_then_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "subdir"))
            open(os.path.join(tmpdir, "data.tif"), "w").close()
            result = list_dir_contents(tmpdir)
            assert len(result) == 2
            assert result[0]["type"] == "dir"
            assert result[0]["name"] == "subdir"
            assert result[1]["type"] == "file"
            assert result[1]["name"] == "data.tif"


from SatelliteEmbedding.core import _get_utm_epsg


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
