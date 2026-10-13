# 恒温箱温控项目

## 电脑服务端

电脑服务端程序是 `computer_server.py`，启动端口为 `8098`。

在这台电脑上打开终端，进入本目录并启动：

```bash
cd "/Users/lazyzeal/Desktop/mead/mead-lab"
python3 computer_server.py
```

如果目标电脑是 Windows，在 PowerShell 中执行：

```powershell
py computer_server.py
```

启动后访问：

```text
http://127.0.0.1:8098/
```

同一个 Wi-Fi 下的其他设备访问：

```text
http://192.168.31.113:8098/
```

首次启动时会自动创建 `temperature.db`，用于保存 ESP32 上传的温度和 MOSFET 状态。

### 断线补传

ESP32 每条读数都带序号和时间戳（优先 NTP，否则使用电脑服务返回的时间），并在内存中缓存最近 3600 条（约 10 小时）。电脑服务启动时，或发现收到的序号不连续时，会请求 ESP32 的 `GET /api/samples` 补传缺失的读数；也可以手动调用 `POST /api/sync`。补传的读数按时间戳归入当时进行中的酿造批次。ESP32 断电或重启会清空缓存，这部分数据无法补传。

网页中的“酿造记录”用于计划和管理批次，批次状态为 草稿 → 进行中 → 已结束：

- 草稿：填写标题、类型、开始日期、批次体积、可发酵糖、酵母、实测 OG、预期 FG、配方和备注，可随时保存和修改，不控温也不记录温度。“估算”按钮根据原料含糖率估算 OG 并填入预期 FG；“反算”按钮根据目标 OG 计算补足原料用量。
- 开始酿造：ESP32 启用自动制冷，温度记录关联该批次。之后只能补填实测 FG。
- 结束酿造：关闭 MOSFET 制冷，停止保存温度记录。已结束批次的曲线范围为开始到结束。

数据库表：`brews`（批次）、`brew_fermentables`（可发酵糖），旧版批次表保留为 `brews_legacy`。

## ESP32 工程

ESP32 工程位于 `esp32_ds18b20_test`：

```text
esp32_ds18b20_test/
├── platformio.ini
└── src/
    └── main.cpp
```

当前固件配置：

```text
DS18B20：D4
MOSFET：D13
Wi-Fi：BLUES
电脑服务端：http://192.168.31.113:8098
默认启动温度：19℃
默认停止温度：17℃
默认目标温度：18℃
```

温控逻辑：

```text
温度 > 19℃ → D13 HIGH → MOSFET 接通
温度 < 17℃ → D13 LOW  → MOSFET 断开
17～19℃   → 保持当前状态
```

电脑端服务启动后，ESP32 每 10 秒上传一次温度数据。

如果 Windows 防火墙弹出提示，请允许 Python 在专用网络上接受连接，或放行 TCP `8080` 端口。
