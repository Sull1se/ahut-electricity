"""Unit tests for the ahut-electricity command-line entry point."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

from ahut_electricity.cli import main


def _balance_response(remain: float) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "Code": 0,
        "Msg": "",
        "Data": {"room_id": "12345", "AllAmp": 1000.00, "UsedAmp": 1000.00 - remain, "RemainAmp": remain},
    }
    return resp


class TestCli(unittest.TestCase):
    @patch("ahut_electricity.cli.load_credentials", return_value=(None, None))
    def test_missing_credentials(self, _mock_creds):
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["K1", "101"])
        self.assertEqual(code, 2)
        self.assertIn("AHUT_USERNAME", err.getvalue())

    @patch("requests.Session.post")
    def test_cookie_query_both(self, mock_post):
        mock_post.side_effect = [_balance_response(100.00), _balance_response(150.00)]
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["K1", "101", "--cookie", "EF.WAP.Auth=x; EF.SessionId=y"])
        self.assertEqual(code, 0)
        self.assertIn("东校区K1号学生宿舍楼 101", out.getvalue())
        self.assertIn("房间电量: 剩余 100.00 度", out.getvalue())
        self.assertIn("空调电量: 剩余 150.00 度", out.getvalue())

    @patch("requests.Session.post")
    def test_cookie_query_air_json(self, mock_post):
        mock_post.return_value = _balance_response(150.00)
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["26", "101", "--campus", "NewS", "--type", "air", "--cookie", "EF.WAP.Auth=x", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["data"]["remain_amp"], 150.00)
        self.assertEqual(mock_post.call_args.kwargs["data"]["etype"], "K")


if __name__ == "__main__":
    unittest.main()
