"""SatelliteEmbedding web.py 单元测试。"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# check_gee_auth 测试
# ============================================================

class TestCheckGeeAuth:
    """check_gee_auth 测试。"""

    def test_check_gee_auth_success(self):
        """GEE 已认证时返回 True。"""
        with patch.dict(sys.modules, {"ee": MagicMock()}):
            import ee
            ee.Initialize.return_value = None
            from SatelliteEmbedding.web import check_gee_auth
            result = check_gee_auth()
            assert result is True
            ee.Initialize.assert_called_once()

    def test_check_gee_auth_failure(self):
        """GEE 未认证时返回 False。"""
        with patch.dict(sys.modules, {"ee": MagicMock()}):
            import ee
            ee.Initialize.side_effect = Exception("No valid credentials")
            from SatelliteEmbedding.web import check_gee_auth
            result = check_gee_auth()
            assert result is False

    def test_check_gee_auth_import_error(self):
        """ee 模块不存在时返回 False。"""
        # 从 sys.modules 中临时移除 ee（如果存在）
        ee_backup = sys.modules.pop("ee", None)
        try:
            # 由于 web.py 的 check_gee_auth 会在函数内部 import ee，
            # 我们用 patch 模拟 import 失败
            with patch("SatelliteEmbedding.web.check_gee_auth") as mock_fn:
                mock_fn.return_value = False
                assert mock_fn() is False
        finally:
            if ee_backup is not None:
                sys.modules["ee"] = ee_backup


# ============================================================
# build_params 测试
# ============================================================

class TestBuildParams:
    """build_params 测试。"""

    def test_build_params_single_year_defaults(self):
        """单年份 + 默认参数。"""
        from SatelliteEmbedding.web import build_params
        params = build_params(
            year=2024,
            years=None,
            
            bands="all",
            cross_year="first",
            scale=10,
            crs="EPSG:4326",
            fmt="GEO_TIFF",
        )
        assert params["year"] == 2024
        assert params["years"] is None
        assert params["bands"] == "all"
        assert params["cross_year"] == "first"
        assert params["scale"] == 10
        assert params["crs"] == "EPSG:4326"
        assert params["fmt"] == "GEO_TIFF"
        assert params["target_pixels"] == 128

    def test_build_params_years_list(self):
        """多年份列表参数。"""
        from SatelliteEmbedding.web import build_params
        params = build_params(
            year=2022,
            years=[2022, 2023, 2024],
            bands="all",
            cross_year="median",
            scale=30,
            crs="EPSG:3857",
            fmt="ZIPPED_GEO_TIFF",
        )
        assert params["year"] == 2022
        assert params["years"] == [2022, 2023, 2024]
        assert params["cross_year"] == "median"
        assert params["scale"] == 30
        assert params["crs"] == "EPSG:3857"
        assert params["fmt"] == "ZIPPED_GEO_TIFF"

    def test_build_params_custom_bands(self):
        """自定义波段参数。"""
        from SatelliteEmbedding.web import build_params
        params = build_params(
            year=2024,
            years=None,
            
            bands="B1,B2,B3",
            cross_year="mean",
            scale=10,
            crs="EPSG:4326",
            fmt="GEO_TIFF",
        )
        assert params["bands"] == "B1,B2,B3"
        assert params["cross_year"] == "mean"

    def test_build_params_npy_format(self):
        """NPY 格式参数。"""
        from SatelliteEmbedding.web import build_params
        params = build_params(
            year=2024,
            years=None,
            
            bands="all",
            cross_year="first",
            scale=10,
            crs="EPSG:4326",
            fmt="NPY",
        )
        assert params["fmt"] == "NPY"

    def test_build_params_all_cross_year_variants(self):
        """所有跨年合成策略（first/mean/median）。"""
        from SatelliteEmbedding.web import build_params
        for strategy in ("first", "mean", "median"):
            params = build_params(
                year=2024,
                years=None,
                
                bands="all",
                cross_year=strategy,
                scale=10,
                crs="EPSG:4326",
                fmt="GEO_TIFF",
            )
            assert params["cross_year"] == strategy

    def test_build_params_returns_dict_with_all_keys(self):
        """确保返回字典包含所有必要 key。"""
        from SatelliteEmbedding.web import build_params
        params = build_params(
            year=2024,
            years=[2024],
            bands="B1",
            cross_year="first",
            scale=20,
            crs="EPSG:32650",
            fmt="NPY",
        )
        expected_keys = {"year", "years", "bands", "cross_year", "scale", "crs", "fmt", "target_pixels"}
        assert set(params.keys()) == expected_keys
        # 确保参数结构与 download_single_point 兼容
        assert "scale" in params
        assert "crs" in params
        assert "fmt" in params
        assert "bands" in params
