"""web.py 单元测试。"""
import sys
import pytest
from unittest.mock import patch, MagicMock
from DynamicWorld.web import build_params


class TestCheckGeeAuth:
    """GEE 认证状态检测测试。"""

    def test_auth_success(self):
        mock_ee = MagicMock()
        with patch.dict(sys.modules, {"ee": mock_ee}):
            from DynamicWorld.web import check_gee_auth
            assert check_gee_auth() is True

    def test_auth_failure(self):
        mock_ee = MagicMock()
        mock_ee.Initialize.side_effect = Exception("auth error")
        with patch.dict(sys.modules, {"ee": mock_ee}):
            from DynamicWorld.web import check_gee_auth
            assert check_gee_auth() is False


class TestBuildParams:
    """参数构建测试。"""

    def test_build_params_defaults(self):
        params = build_params(
            start_date="2024-01-01", end_date="2024-12-31",
             bands="label", composite="first",
            scale=10, crs="EPSG:4326", fmt="GEO_TIFF",
            file_per_band=True,
        )
        assert params == {
            "start_date": "2024-01-01", "end_date": "2024-12-31",
            "bands": "label", "composite": "first",
            "scale": 10, "crs": "EPSG:4326", "fmt": "GEO_TIFF",
            "file_per_band": True, "target_pixels": 128,
        }
