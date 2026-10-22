# 库房出入库系统

局域网库房出入库管理：出库、到货、日表、借用归还、盘点、报表、手机端等。  
**第一版**（v1.0.0）。仓库内 `data/warehouse.db` 为**测试数据**，便于直接启动试用。

---

## 环境

- Python 3.8+（推荐 3.10 / 3.12）
- 标准库 + 自带 `app/vendor`，一般无需再装依赖
- Windows 可用 `启动.bat`；Linux / macOS 用命令行

---

## 启动

```bash
cd kufang-system
python tools/seed_demo.py --force   # 可选：重建测试数据
python app/server.py
# 或
python app/launcher.py --no-tray --no-browser
```

- 电脑端：`http://127.0.0.1:8080/`
- 手机端：`http://本机局域网IP:8080/m/`

测试账号 PIN（密码即身份）：`1001` 演示管理员，`1002`～`1004` 演示录入。  
正式使用前请在设置里改掉账号与 PIN，并换用自己的数据目录。

Windows：已装 Python 时可双击 `启动.bat`。

数据目录可用环境变量：

```bash
export WH_DATA=/path/to/my-data
export WH_PORT=8080
python app/server.py
```

---

## 目录

| 路径 | 说明 |
|------|------|
| `app/` | 后端（`server.py` 入口） |
| `static/` | 电脑端 / 手机端前端 |
| `templates/` | 报表、日表等 Excel / Word 模板 |
| `data/` | 运行数据（库、照片、日志）；已含测试库 |
| `tests/` | 自动化测试 |
| `tools/` | `seed_demo.py` 等 |
| `启动.bat` 等 | Windows 启停、防火墙、开机自启 |
| `使用说明.md` | 使用说明摘要 |

---

## 测试数据

```bash
python tools/seed_demo.py          # 已有业务数据时不覆盖
python tools/seed_demo.py --force  # 清空业务表后写入测试数据
```

---

## 升级

1. 停服务  
2. 备份整个 `data/`  
3. 用新版本覆盖代码，**不要覆盖**正在用的 `data/`  
4. 再启动（启动时会跑库内升级）

更细的操作说明见 `使用说明.md`。
