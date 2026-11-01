"""Unit tests for ahut_electricity client and building resolution."""

import unittest
from unittest.mock import MagicMock, patch

from ahut_electricity.buildings import (
    BUILDINGS_BY_CAMPUS,
    normalize_campus,
    resolve_building,
)
from ahut_electricity.client import AhutElectricityClient


class TestBuildingResolution(unittest.TestCase):
    def test_normalize_campus(self):
        self.assertEqual(normalize_campus("NewS"), "NewS")
        self.assertEqual(normalize_campus("news"), "NewS")
        self.assertEqual(normalize_campus("东校区"), "NewS")
        self.assertEqual(normalize_campus("OldS"), "OldS")
        self.assertEqual(normalize_campus("本部"), "OldS")
        with self.assertRaises(ValueError):
            normalize_campus("UnknownCampus")

    def test_resolve_building_exact_id(self):
        campus, b_id, b_name = resolve_building("26", "NewS")
        self.assertEqual(campus, "NewS")
        self.assertEqual(b_id, "26")
        self.assertEqual(b_name, "东校区K1号学生宿舍楼")

    def test_resolve_building_short_code(self):
        campus, b_id, b_name = resolve_building("K1", "NewS")
        self.assertEqual(b_id, "26")
        self.assertEqual(b_name, "东校区K1号学生宿舍楼")

    def test_resolve_building_auto_campus(self):
        # K1 is unique to NewS, should resolve even if campus is omitted
        campus, b_id, b_name = resolve_building("K1")
        self.assertEqual(campus, "NewS")
        self.assertEqual(b_id, "26")

    def test_resolve_building_not_found(self):
        with self.assertRaises(ValueError):
            resolve_building("不存在的楼栋号XYZ", "NewS")


class TestAhutElectricityClient(unittest.TestCase):
    def setUp(self):
        self.client = AhutElectricityClient()

    def test_set_cookies_string(self):
        cookie_str = "EF.SessionId=abc123; EF.TerminalId=term456; EF.WAP.Auth=auth789"
        self.client.set_cookies(cookie_str)
        cookies = self.client.session.cookies.get_dict()
        self.assertEqual(cookies.get("EF.SessionId"), "abc123")
        self.assertEqual(cookies.get("EF.TerminalId"), "term456")
        self.assertEqual(cookies.get("EF.WAP.Auth"), "auth789")

    def test_invalid_room_number(self):
        with self.assertRaises(ValueError):
            self.client.query_balance("NewS", "26", "10")  # only 2 digits
        with self.assertRaises(ValueError):
            self.client.query_balance("NewS", "26", "1011")  # 4 digits
        with self.assertRaises(ValueError):
            self.client.query_balance("NewS", "26", "abc")  # not digits

    @patch("requests.Session.post")
    def test_query_balance_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Code": 0,
            "Msg": "",
            "Data": {
                "room_id": "12345",
                "AllAmp": 1000.00,
                "UsedAmp": 900.00,
                "RemainAmp": 100.00,
            },
        }
        mock_post.return_value = mock_resp

        res = self.client.query_balance("NewS", "26", "101", elec_type="")
        self.assertTrue(res["success"])
        self.assertEqual(res["code"], 0)
        self.assertEqual(res["data"]["remain_amp"], 100.00)
        self.assertEqual(res["data"]["room_id"], "12345")

    @patch("requests.Session.post")
    def test_query_balance_unauthorized(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Code": 10001,
            "Msg": "用户未授权或授权已经过期，请先登录",
            "Data": None,
        }
        mock_post.return_value = mock_resp

        res = self.client.query_balance("NewS", "26", "101", elec_type="")
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], 10001)
        self.assertIn("未登录", res["msg"])

    @patch("requests.Session.post")
    def test_query_both(self, mock_post):
        mock_resp_room = MagicMock()
        mock_resp_room.status_code = 200
        mock_resp_room.json.return_value = {
            "Code": 0,
            "Msg": "",
            "Data": {
                "room_id": "12345",
                "AllAmp": 1000.00,
                "UsedAmp": 900.00,
                "RemainAmp": 100.00,
            },
        }

        mock_resp_air = MagicMock()
        mock_resp_air.status_code = 200
        mock_resp_air.json.return_value = {
            "Code": 0,
            "Msg": "",
            "Data": {
                "room_id": "23456",
                "AllAmp": 2000.00,
                "UsedAmp": 1850.00,
                "RemainAmp": 150.00,
            },
        }

        mock_post.side_effect = [mock_resp_room, mock_resp_air]

        res = self.client.query_both("NewS", "26", "101")
        self.assertTrue(res["all_success"])
        self.assertEqual(res["room"]["data"]["remain_amp"], 100.00)
        self.assertEqual(res["air"]["data"]["remain_amp"], 150.00)


if __name__ == "__main__":
    unittest.main()
