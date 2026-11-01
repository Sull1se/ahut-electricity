"""Client for AHUT Electricity Recharge & Balance Inquiry Service."""

import re
from typing import Any, Dict, List, Optional, Union
import requests
from .auth import load_credentials, login_service
from .buildings import BUILDINGS_BY_CAMPUS, normalize_campus, resolve_building

BASE_URL = "https://pay.ahut.edu.cn"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)


class AhutElectricityClient:
    """HTTP Client interacting with AHUT Electricity Recharge system (pay.ahut.edu.cn)."""

    def __init__(
        self,
        cookies: Optional[Union[str, Dict[str, str]]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: str = BASE_URL,
        auto_login: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": f"{self.base_url}/Charge/IMS",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        self.auto_login = auto_login

        # Resolve credentials (priority: explicit args -> env vars -> config.json)
        u, p = username, password
        if not (u and p):
            env_u, env_p = load_credentials()
            u = u or env_u
            p = p or env_p
        self.username = u
        self.password = p

        if cookies:
            self.set_cookies(cookies)
        elif self.username and self.password and self.auto_login:
            self.login()


    def set_cookies(self, cookies: Union[str, Dict[str, str]]) -> None:
        """
        Set session cookies from a cookie header string (e.g. 'EF.WAP.Auth=...; EF.SessionId=...')
        or a dictionary.
        """
        if isinstance(cookies, dict):
            for k, v in cookies.items():
                self.session.cookies.set(k.strip(), v.strip())
        elif isinstance(cookies, str):
            for part in cookies.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    self.session.cookies.set(k.strip(), v.strip())

    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        vcode: str = "",
    ) -> Dict[str, Any]:
        """
        Authenticate against /Account/LoginService and populate session cookies.
        Uses supplied credentials or falls back to self.username/self.password.
        """
        u = username or self.username
        p = password or self.password
        if not (u and p):
            return {
                "success": False,
                "code": -1,
                "msg": "未提供账号或密码（可通过参数、环境变量 AHUT_USERNAME/AHUT_PASSWORD 或 config.json 配置）",
                "cookies": {},
            }

        if username:
            self.username = username
        if password:
            self.password = password

        return login_service(self.session, u, p, base_url=self.base_url, vcode=vcode)

    def get_remote_buildings(self, campus: str) -> List[Dict[str, str]]:
        """
        Fetch dynamic building list from backend (/Charge/GetAHUTLDSelectService).
        Falls back to local cache if network/auth fails.
        """
        norm_campus = normalize_campus(campus)
        url = f"{self.base_url}/Charge/GetAHUTLDSelectService"
        try:
            resp = self.session.post(url, data={"xiaoqu": norm_campus}, timeout=10)
            if resp.status_code == 200:
                res_data = resp.json()
                if res_data.get("Code") == 0 and isinstance(res_data.get("Data"), list):
                    return res_data["Data"]
        except Exception:
            pass
        return BUILDINGS_BY_CAMPUS.get(norm_campus, [])

    def query_balance(
        self,
        campus: str,
        building: str,
        room_no: str,
        elec_type: str = "",
        _retry: bool = False,
    ) -> Dict[str, Any]:
        """
        Query balance for a specific room and power type.
        
        :param campus: Campus code ('NewS' or 'OldS') or alias ('东校区', '本部').
        :param building: Building ID ('26') or name/query ('K1', '东校区K1号学生宿舍楼').
        :param room_no: 3-digit room number string, e.g. '101'.
        :param elec_type: '' for room lighting/sockets, 'K' for air conditioning.
        :return: Dict containing result details.
        """
        norm_campus = normalize_campus(campus) if campus else None
        c_code, b_id, b_name = resolve_building(building, norm_campus)
        room_str = str(room_no).strip()

        if not re.match(r"^[0-9]{3}$", room_str):
            raise ValueError(f"房间号必须为3位数字，当前输入: '{room_no}'")

        if elec_type not in ("", "K", "room", "air"):
            raise ValueError(f"电费类型无效: '{elec_type}'。可选: ''/room (房间), 'K'/air (空调)")

        etype = "K" if elec_type in ("K", "air") else ""
        type_name = "空调" if etype == "K" else "房间"

        url = f"{self.base_url}/Charge/GetIMS_AHUTService"
        payload = {
            "xiaoqu": c_code,
            "ld_Name": b_name,
            "ld_Id": b_id,
            "Room_No": room_str,
            "etype": etype,
        }

        try:
            resp = self.session.post(url, data=payload, timeout=10)
        except requests.RequestException as e:
            return {
                "success": False,
                "code": -1,
                "msg": f"网络请求失败: {e}",
                "campus": c_code,
                "building_id": b_id,
                "building_name": b_name,
                "room_no": room_str,
                "type": type_name,
                "etype": etype,
                "data": None,
            }

        if resp.status_code != 200:
            return {
                "success": False,
                "code": resp.status_code,
                "msg": f"HTTP {resp.status_code}: {resp.text[:200]}",
                "campus": c_code,
                "building_id": b_id,
                "building_name": b_name,
                "room_no": room_str,
                "type": type_name,
                "etype": etype,
                "data": None,
            }

        try:
            res_json = resp.json()
        except ValueError:
            return {
                "success": False,
                "code": -3,
                "msg": f"返回内容非 JSON 格式: {resp.text[:200]}",
                "campus": c_code,
                "building_id": b_id,
                "building_name": b_name,
                "room_no": room_str,
                "type": type_name,
                "etype": etype,
                "data": None,
            }

        code = res_json.get("Code", -1)
        msg = res_json.get("Msg", "")
        raw_data = res_json.get("Data")

        if code == 0 and raw_data:
            return {
                "success": True,
                "code": 0,
                "msg": "查询成功",
                "campus": c_code,
                "building_id": b_id,
                "building_name": b_name,
                "room_no": room_str,
                "type": type_name,
                "etype": etype,
                "data": {
                    "room_id": raw_data.get("room_id"),
                    "all_amp": float(raw_data.get("AllAmp", 0.0)),
                    "used_amp": float(raw_data.get("UsedAmp", 0.0)),
                    "remain_amp": float(raw_data.get("RemainAmp", 0.0)),
                },
            }
        elif code == 10001:
            if self.auto_login and self.username and self.password and not _retry:
                login_res = self.login()
                if login_res.get("success"):
                    return self.query_balance(
                        campus=campus,
                        building=building,
                        room_no=room_no,
                        elec_type=elec_type,
                        _retry=True,
                    )
            return {
                "success": False,
                "code": 10001,
                "msg": "未登录或登录已失效，请更新凭据或调用 login()",
                "campus": c_code,
                "building_id": b_id,
                "building_name": b_name,
                "room_no": room_str,
                "type": type_name,
                "etype": etype,
                "data": None,
            }
        else:
            return {
                "success": False,
                "code": code,
                "msg": msg or f"查询失败 (错误码 {code})",
                "campus": c_code,
                "building_id": b_id,
                "building_name": b_name,
                "room_no": room_str,
                "type": type_name,
                "etype": etype,
                "data": None,
            }

    def query_both(
        self,
        campus: str,
        building: str,
        room_no: str,
    ) -> Dict[str, Any]:
        """
        Query both Room and Air Conditioning balance at the same time.
        """
        room_res = self.query_balance(campus, building, room_no, elec_type="")
        air_res = self.query_balance(campus, building, room_no, elec_type="K")
        return {
            "campus": room_res.get("campus"),
            "building_id": room_res.get("building_id"),
            "building_name": room_res.get("building_name"),
            "room_no": room_no,
            "room": room_res,
            "air": air_res,
            "all_success": room_res["success"] and air_res["success"],
        }
