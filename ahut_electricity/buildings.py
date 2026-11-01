"""AHUT Dormitory Campus and Building mapping and resolution utilities."""

from typing import Dict, List, Optional, Tuple

CAMPUS_MAP = {
    "NewS": "东校区",
    "OldS": "本部校区",
}

CAMPUS_ALIASES = {
    "news": "NewS",
    "east": "NewS",
    "东": "NewS",
    "东校区": "NewS",
    "olds": "OldS",
    "main": "OldS",
    "本部": "OldS",
    "本部校区": "OldS",
    "老校区": "OldS",
}

BUILDINGS_BY_CAMPUS: Dict[str, List[Dict[str, str]]] = {
    "NewS": [
        {"Id": "01", "Name": "东校区1号学生宿舍楼"},
        {"Id": "02", "Name": "东校区2号学生宿舍楼"},
        {"Id": "03", "Name": "东校区3号学生宿舍楼"},
        {"Id": "04", "Name": "东校区4号学生宿舍楼"},
        {"Id": "05", "Name": "东校区5号学生宿舍楼"},
        {"Id": "06", "Name": "东校区6号学生宿舍楼"},
        {"Id": "07", "Name": "东校区7号学生宿舍楼"},
        {"Id": "08", "Name": "东校区8号学生宿舍楼"},
        {"Id": "09", "Name": "东校区9号学生宿舍楼"},
        {"Id": "10", "Name": "东校区A号学生宿舍楼"},
        {"Id": "11", "Name": "东校区B号学生宿舍楼"},
        {"Id": "13", "Name": "东校区C号学生宿舍楼"},
        {"Id": "14", "Name": "东校区D号学生宿舍楼"},
        {"Id": "15", "Name": "东校区E号学生宿舍楼"},
        {"Id": "16", "Name": "东校区F号学生宿舍楼"},
        {"Id": "17", "Name": "东校区H1号学生宿舍楼"},
        {"Id": "18", "Name": "东校区H2号学生宿舍楼"},
        {"Id": "19", "Name": "东校区H3号学生宿舍楼"},
        {"Id": "20", "Name": "东校区G1号学生宿舍楼"},
        {"Id": "21", "Name": "东校区G2号学生宿舍楼"},
        {"Id": "22", "Name": "东校区G3号学生宿舍楼"},
        {"Id": "23", "Name": "东校区J1号学生宿舍楼"},
        {"Id": "24", "Name": "东校区J2号学生宿舍楼"},
        {"Id": "25", "Name": "东校区J3号学生宿舍楼"},
        {"Id": "26", "Name": "东校区K1号学生宿舍楼"},
        {"Id": "27", "Name": "东校区K2号学生宿舍楼"},
        {"Id": "28", "Name": "东校区K3号学生宿舍楼"},
        {"Id": "29", "Name": "东校区L1号学生宿舍楼"},
        {"Id": "30", "Name": "东校区L2号学生宿舍楼"},
        {"Id": "31", "Name": "东校区G4号学生宿舍楼"},
        {"Id": "32", "Name": "东校区研5号学生宿舍楼"},
        {"Id": "33", "Name": "东校区研6号学生宿舍楼"},
        {"Id": "34", "Name": "东校区研7号学生宿舍楼"},
        {"Id": "35", "Name": "东校区研8号学生宿舍楼"},
        {"Id": "36", "Name": "东校区研1号学生宿舍楼"},
        {"Id": "37", "Name": "东校区研2号学生宿舍楼"},
        {"Id": "38", "Name": "东校区研3号学生宿舍楼"},
        {"Id": "39", "Name": "东校区研4号学生宿舍楼"},
        {"Id": "40", "Name": "东校区M栋南楼宿舍"},
        {"Id": "41", "Name": "东校区M栋北楼宿舍"},
        {"Id": "42", "Name": "东校区N栋南楼宿舍"},
        {"Id": "43", "Name": "东校区N栋北楼宿舍"},
    ],
    "OldS": [
        {"Id": "01", "Name": "本部校区01栋学生宿舍"},
        {"Id": "02", "Name": "本部校区02栋学生宿舍"},
        {"Id": "03", "Name": "本部校区03栋学生宿舍"},
        {"Id": "04", "Name": "本部校区04栋学生宿舍"},
        {"Id": "05", "Name": "本部校区05A栋学生宿舍"},
        {"Id": "06", "Name": "本部校区05B栋学生宿舍"},
        {"Id": "07", "Name": "本部校区矿东栋学生宿舍"},
        {"Id": "08", "Name": "本部校区矿西栋学生宿舍"},
        {"Id": "09", "Name": "本部校区研A栋学生宿舍"},
        {"Id": "10", "Name": "本部校区研B栋学生宿舍"},
        {"Id": "11", "Name": "本部校区8号公寓"},
        {"Id": "12", "Name": "本部校区7号公寓"},
    ],
}


def normalize_campus(campus: str) -> str:
    """Normalize campus string to 'NewS' or 'OldS'."""
    key = campus.strip().lower()
    if key in CAMPUS_ALIASES:
        return CAMPUS_ALIASES[key]
    if campus in CAMPUS_MAP:
        return campus
    raise ValueError(f"未知校区: {campus}。可用校区: NewS (东校区), OldS (本部校区)")


def resolve_building(building_query: str, campus: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Resolve a building query to (campus, building_id, building_name).
    Supports exact ID ('26'), full name, or short code ('K1', '研1', '7号公寓').
    If campus is None, attempts to find a unique match across both campuses.
    """
    query = building_query.strip()
    norm_campus = normalize_campus(campus) if campus else None

    search_campuses = [norm_campus] if norm_campus else ["NewS", "OldS"]
    matches = []

    for c in search_campuses:
        buildings = BUILDINGS_BY_CAMPUS[c]
        # 1. Exact ID match
        for b in buildings:
            if b["Id"] == query or b["Id"].lstrip("0") == query.lstrip("0"):
                matches.append((c, b["Id"], b["Name"]))

        # 2. Exact Name match
        for b in buildings:
            if b["Name"] == query and (c, b["Id"], b["Name"]) not in matches:
                matches.append((c, b["Id"], b["Name"]))

        # 3. Short substring match (e.g. "K1", "05A", "研1")
        clean_q = query.upper().replace("号", "").replace("学生", "").replace("宿舍", "").replace("楼", "").replace("栋", "").replace("公寓", "")
        for b in buildings:
            name_upper = b["Name"].upper()
            if clean_q and clean_q in name_upper and (c, b["Id"], b["Name"]) not in matches:
                matches.append((c, b["Id"], b["Name"]))

    if not matches:
        raise ValueError(f"未找到与 '{building_query}' 匹配的楼栋。")
    if len(matches) > 1:
        # Check if one of them is an exact ID or exact name match
        exact_id = [m for m in matches if m[1] == query or m[1].zfill(2) == query.zfill(2)]
        if len(exact_id) == 1:
            return exact_id[0]
        exact_name = [m for m in matches if m[2] == query]
        if len(exact_name) == 1:
            return exact_name[0]
        
        # Format candidate list for disambiguation
        candidates = ", ".join([f"{m[0]}:{m[1]} ({m[2]})" for m in matches[:5]])
        raise ValueError(f"匹配到多个候选楼栋: {candidates}，请指定校区或更精确的名称/编号。")

    return matches[0]
