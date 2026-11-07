# 系统架构与接口说明

本文记录安徽工业大学校园支付平台（`pay.ahut.edu.cn`）电量查询相关接口的分析结果，以及本库的实现方式。接口为非官方、通过前端页面分析得到，学校可能随时调整，请以实际返回为准。

示例中的学号、房间号、`room_id` 与电量读数均为虚构值。

---

## 1. 背景

在校园支付平台（`https://pay.ahut.edu.cn/Charge/IMS`）中，如果只想“查看当前剩余电量”，需要走完整个充值准备流程：

1. 选择校区（东校区 / 本部校区）；
2. 选择楼栋；
3. 输入 3 位房间号；
4. 选择用电类型（房间 / 空调）；
5. 选择或输入充值金额；
6. 点击「确认充值」；
7. 前端弹窗展示购电总量、用电总量与剩余电量，并询问是否创建支付订单。

### 1.1 页面分析

页面 `#app` 上的 Vue 实例（`window.vm`）的 `submit` 方法在点击「确认充值」时，第一步并不是创建订单，而是先调用一个查询接口获取电表信息，再在回调里用 `$.confirm` 展示。直接调用这个查询接口即可只读地获取余额，不会创建订单。

---

## 2. 接口说明

### 2.1 楼栋字典：`/Charge/GetAHUTLDSelectService`

- **URL**: `https://pay.ahut.edu.cn/Charge/GetAHUTLDSelectService`
- **Method**: `POST`
- **Content-Type**: `application/x-www-form-urlencoded; charset=UTF-8`
- **请求参数**:
  | 参数名 | 类型 | 说明 | 取值范围 |
  | :--- | :--- | :--- | :--- |
  | `xiaoqu` | string | 校区代码 | `"NewS"` (东校区) 或 `"OldS"` (本部校区) |

- **响应格式 (JSON)**:
  ```json
  {
    "Code": 0,
    "Msg": "",
    "Data": [
      { "Id": "01", "Name": "东校区1号学生宿舍楼" },
      { "Id": "26", "Name": "东校区K1号学生宿舍楼" }
    ]
  }
  ```

本库在 `ahut_electricity/buildings.py` 中内置了一份楼栋字典，并支持按编号、全称或简称（如 `K1`、`研1`）模糊匹配。

### 2.2 电量余额查询：`/Charge/GetIMS_AHUTService`

- **URL**: `https://pay.ahut.edu.cn/Charge/GetIMS_AHUTService`
- **Method**: `POST`
- **Content-Type**: `application/x-www-form-urlencoded; charset=UTF-8`
- **请求参数**:
  | 参数名 | 类型 | 必填 | 说明 | 示例 |
  | :--- | :--- | :--- | :--- | :--- |
  | `xiaoqu` | string | 是 | 校区代号 | `"NewS"` |
  | `ld_Name` | string | 是 | 楼栋全称（必须与字典接口一致） | `"东校区K1号学生宿舍楼"` |
  | `ld_Id` | string | 是 | 楼栋两位编号 | `"26"` |
  | `Room_No` | string | 是 | 3 位房间号 | `"101"` |
  | `etype` | string | 否 | 用电类型代码 | `""` (房间照明/插座), `"K"` (空调) |

- **成功响应示例** (`Code: 0`，数值为虚构):
  ```json
  {
    "Code": 0,
    "Msg": "",
    "Data": {
      "room_id": "12345",
      "AllAmp": 1000.00,
      "UsedAmp": 900.00,
      "RemainAmp": 100.00
    }
  }
  ```
- **字段含义**:
  - `Data.room_id`: 房间 / 电表在后台系统中的记录 ID；
  - `Data.AllAmp`: 累计购电总量（度 / kWh）；
  - `Data.UsedAmp`: 累计已用电量（度 / kWh）；
  - `Data.RemainAmp`: **当前剩余电量**（度 / kWh）；
  - 数值关系：`AllAmp - UsedAmp ≈ RemainAmp`。

- **常见异常响应**:
  - 未登录或凭据失效：
    ```json
    { "Code": 10001, "Msg": "用户未授权或授权已经过期，请先登录", "Data": null }
    ```
  - 房间不存在：
    ```json
    { "Code": -2, "Msg": "读取房间电量信息失败：房间电费信息不存在", "Data": null }
    ```
  - 服务端临时故障（约 15 秒后才返回，稍后重试即可恢复）：
    ```json
    { "Code": -2, "Msg": "读取房间电量信息失败：数据操作异常,请稍后重试或联系管理员.", "Data": null }
    ```
  - 两种情况的 `Code` 相同，只能通过 `Msg` 区分。

#### 数据刷新与临时故障

- 房间电量约每 62.5 分钟刷新一次，刷新时刻不对齐整点，每小时后移约 2.5 分钟。两次刷新之间接口返回同一读数，读数最多比实际滞后约 1 小时；比每小时一次更频繁的查询拿不到新数据。
- 每次刷新前后约 2 分钟内，查询会在约 15 秒后返回 `Code: -2`“数据操作异常”，刷新后的首次查询可能耗时数秒。
- 服务端另有一个约 61.6 分钟周期的后台任务，与刷新无关，执行期间查询同样会返回“数据操作异常”或耗时数秒。
- 上述故障白天与夜间都会出现；其余时间查询耗时通常为几十毫秒。
- 登录会话可连续使用十几个小时，无需每次查询前重新登录。

调用方应把“数据操作异常”和超时视为临时故障，等待 2–3 分钟后重试；本库目前不会自动重试。

### 2.3 登录认证：`/Account/LoginService`

- **URL**: `https://pay.ahut.edu.cn/Account/LoginService`
- **Method**: `POST`
- **Content-Type**: `application/x-www-form-urlencoded; charset=UTF-8`
- **请求头**: `X-Requested-With: XMLHttpRequest`, `Referer: https://pay.ahut.edu.cn/Account/Login`
- **请求参数**:
  | 参数名 | 类型 | 必填 | 说明 | 示例 |
  | :--- | :--- | :--- | :--- | :--- |
  | `username` | string | 是 | 学号或工号 | `"20260000"`（虚构） |
  | `pwd` | string | 是 | 加密后的密码（见下文，Base64 后约 344 字符） | `"L8o9...=="` |
  | `vcode` | string | 否 | 验证码，默认不需要，连续失败后才会要求 | `""` |

- **密码加密**（复现登录页 `JSEncrypt` 逻辑）:
  1. 原始密码先做 UTF-8 Base64 编码：`b64_pwd = base64.b64encode(password.encode("utf-8"))`；
  2. 用下方 2048 位 RSA 公钥、PKCS#1 v1.5 填充加密 `b64_pwd`；
  3. 密文再做 Base64 编码，作为 `pwd` 字段发送。

- **RSA 公钥 (PEM)**，即登录页 `encrypt.setPublicKey(...)` 传入的公钥（页面中另有一行被注释掉的旧 1024 位公钥，未使用）:
  ```text
  -----BEGIN PUBLIC KEY-----
  MIIBITANBgkqhkiG9w0BAQEFAAOCAQ4AMIIBCQKCAQBwpjFh5e65q6X/L3aRYGLs
  D2+jvGlzcQ/gwyeZSx/vvbLKf/OcqoUxWst6I8FVfChflFKrWpz2K9GWTeE+be1F
  SD83abG0TXE6xL7UX6+gbkU+1KfcbZjI8KOx4NJkY2+NG8CQ0g/MrEnYs1lA2j5b
  84byjPrLycoDg5Ia6yIpad5xFmRLJkwCZB4HdhvpPxDvrR6QtIhz5Q0qM2dSdXeM
  O11FidTZ9C3bARZ+CqysBTr77Z2NaOhUwSBvvZt/jpbkErSe9Fbv5efH7mVK+w9q
  PU/zYkUHKFzd1LVlbm1UQMeKCLwHtMyxMHugiOORT7J1hCFeVfU1/UlmSdEFNFK/
  AgMBAAE=
  -----END PUBLIC KEY-----
  ```
  SPKI DER 的 SHA-256 指纹：`bd3f025b73e2b84ce42b86cebcdb3e8e65c5340b8aa91434060c3c5135957995`。

- **响应格式 (JSON)**:
  - 成功 (`Code: 0`): `{"Code": 0, "Msg": "", "Data": null}`，响应头通过 `Set-Cookie` 下发 `EF.WAP.Auth` 与 `EF.SessionId`；
  - 失败 (`Code: 2` / `-3` / `-4`): 例如 `{"Code": 2, "Msg": "用户名或密码错误", "Data": null}`。

#### 公钥的固定与校验

`auth.py` 不手写模数，而是保存上面的 base64 DER（`RSA_PUBLIC_KEY_B64`），导入时先校验其 SHA-256 等于固定指纹（`RSA_PUBLIC_KEY_SHA256`），再用纯 Python 的 DER 解析得到模数与指数。测试 `test_public_key_matches_pinned_fingerprint` 会从实际用于加密的 `RSA_MODULUS` / `RSA_EXPONENT` 重新构造 SPKI 并核对指纹，离线即可发现公钥被改错。

`login_service()` 默认（`verify_key=True`）在登录前先 GET `/Account/Login`，提取页面中未被注释的最后一次 `setPublicKey(...)` 调用的公钥并核对指纹；不一致或找不到时直接返回 `Code: -5` 拒绝登录，不发送密码，以便在学校更换公钥时给出明确错误。

---

## 3. 会话与认证

1. **核心凭据**：服务端主要依赖 Cookie 中的 `EF.WAP.Auth` 与 `EF.SessionId` 校验身份；`EF.TerminalId` 为终端随机识别串。
2. **凭据特性**：`EF.WAP.Auth` 为 HttpOnly Cookie，未登录或过期时业务接口返回 `Code: 10001`。
3. **自动登录与重试**：`AhutElectricityClient` 可用学号和密码调用 `login()` 获取 Cookie；查询返回 `Code: 10001` 时，若已配置账号密码，会自动重新登录并重试一次。
4. **也可以不登录**：从浏览器复制 `EF.WAP.Auth` / `EF.SessionId` Cookie 传给客户端（`cookies=` 参数或命令行 `--cookie`）。
5. **凭据配置**：不要把账号密码写进源码。支持：
   - 环境变量 `AHUT_USERNAME` 与 `AHUT_PASSWORD`；
   - 本地 `config.json`（已在 `.gitignore` 中忽略），模板见 `config.example.json`。

---

## 4. 代码结构

```text
ahut-electricity/
├── pyproject.toml              # 包元数据与命令行入口（依赖仅 requests）
├── config.example.json         # 账号密码配置模板（实际 config.json 被忽略）
├── .env.example                # 环境变量模板
├── ahut_electricity/
│   ├── __init__.py             # 包导出
│   ├── __main__.py             # python -m ahut_electricity
│   ├── auth.py                 # 公钥固定与解析、RSA PKCS#1 v1.5 加密、凭据载入、登录
│   ├── buildings.py            # 校区楼栋字典与模糊匹配
│   ├── cli.py                  # 命令行入口
│   └── client.py               # HTTP 客户端：查询、登录注入与失效重登
├── tests/                      # 离线单元测试（unittest，全部使用 mock，不访问网络）
│   ├── test_auth.py
│   ├── test_cli.py
│   └── test_client.py
└── docs/
    └── architecture.md         # 本文
```
