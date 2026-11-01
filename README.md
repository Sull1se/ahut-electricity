# 安徽工业大学宿舍电量查询

查询安徽工业大学（AHUT）学生宿舍**房间电量**与**空调电量**余额的 Python 库和命令行工具。

校园支付平台只在“确认充值”的弹窗里显示剩余电量；本库直接调用该弹窗背后的只读查询接口，不会创建充值订单。

> **免责声明**
>
> - 本项目与安徽工业大学及其支付平台无关，**不是官方接口**。接口来自前端页面分析，学校可能随时修改或关闭，届时本库会失效。
> - 请遵循校方规定，合理使用。
> - 账号密码只在本地用于登录学校系统，本库不会发送到其他地方；请妥善保管自己的凭据。
> - 本项目采用 MIT 许可证，使用风险由使用者自行承担。

## 功能

- 查询房间 / 空调剩余电量、累计购电与累计用电；
- 用学号和密码自动登录（纯 Python 实现登录页的 RSA-2048 PKCS#1 v1.5 密码加密），凭据过期时自动重登并重试；
- 登录前核对登录页下发的 RSA 公钥指纹，学校更换公钥时明确报错，而不是悄悄登录失败；
- 也可以直接使用浏览器里复制的 Cookie，无需提供密码；
- 内置楼栋字典，楼栋可用编号（`26`）、全称或简称（`K1`、`研1`）指定；
- 唯一依赖是 `requests`。

## 配置账号

任选一种（优先级从高到低）：

1. 环境变量：

   ```bash
   export AHUT_USERNAME=你的学号
   export AHUT_PASSWORD=你的校园支付平台密码
   ```

2. 在当前目录创建 `config.json`（参考 `config.example.json`，该文件已被 `.gitignore` 忽略）：

   ```json
   { "username": "你的学号", "password": "你的校园支付平台密码" }
   ```

3. 不提供密码，改用浏览器 Cookie：登录 `https://pay.ahut.edu.cn` 后，从开发者工具复制 `EF.WAP.Auth` 与 `EF.SessionId`。

## 命令行用法

```bash
# 同时查询房间和空调（楼栋 K1，房间 101）
ahut-electricity K1 101

# 只查空调，指定校区，输出 JSON
ahut-electricity 26 101 --campus NewS --type air --json

# 使用浏览器 Cookie，不登录
ahut-electricity K1 101 --cookie "EF.WAP.Auth=...; EF.SessionId=..."

# 也可以这样运行
python -m ahut_electricity K1 101
```

示例输出（数值为虚构）：

```text
东校区K1号学生宿舍楼 101
房间电量: 剩余 100.00 度（累计购电 1000.00，累计用电 900.00）
空调电量: 剩余 150.00 度（累计购电 2000.00，累计用电 1850.00）
```

退出码：`0` 全部成功，`1` 登录或查询失败，`2` 参数或配置错误。

## Python 用法

```python
from ahut_electricity import AhutElectricityClient

# 从环境变量或 config.json 读取账号并自动登录
client = AhutElectricityClient()

# 或：client = AhutElectricityClient(cookies="EF.WAP.Auth=...; EF.SessionId=...")

res = client.query_balance("东校区", "K1", "101", elec_type="room")  # "air" 为空调
if res["success"]:
    print(res["data"]["remain_amp"])
else:
    print(res["code"], res["msg"])

both = client.query_both("NewS", "K1", "101")
print(both["room"]["data"], both["air"]["data"])
```

返回值都是字典，包含 `success`、`code`、`msg` 和 `data`（`room_id`、`all_amp`、`used_amp`、`remain_amp`）。常见 `code`：

| code | 含义 |
| :--- | :--- |
| `0` | 成功 |
| `10001` | 未登录或登录已失效 |
| `-2` | 房间电费信息不存在（楼栋或房间号有误） |
| `2` / `-3` / `-4` | 登录失败（账号密码错误等，可能触发验证码） |
| `-5` | 登录页公钥与内置指纹不一致或无法获取，已拒绝登录 |
| `-1` | 网络请求失败 |

## 注意事项

- 接口非官方，学校改版后可能失效；
- 连续登录失败后学校会要求验证码，本库不处理验证码；
- 房间号只支持 3 位数字；内置楼栋字典可能与学校最新数据不同，可用 `client.get_remote_buildings(campus)` 获取在线列表；
- 只做查询，不支持充值；
- 仅在校园支付平台当前版本上验证过。

## 开发

```bash
pip install -e .
python -m unittest discover -s tests -t .
```

测试全部离线运行（使用 mock，不访问学校服务器）。接口细节见 [docs/architecture.md](docs/architecture.md)。

## 许可证

[MIT](LICENSE)
