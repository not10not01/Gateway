# Matrix-800 現場操作手冊

本文件整理目前已在實機驗證的 Windows、Matrix-800、ULTEST 三軸振動 Sensor、
網頁、ISO 20816 與輕量 Edge AI 操作流程。

## 1. 已驗證的接線與位址

```text
Windows 電腦 192.168.2.100/24
        │ Ethernet
        ▼
Matrix-800 LAN2 192.168.2.127/24
        │ P1 D+ / D-（RS-485）
        ▼
ULTEST Sensor：5 VDC 獨立供電、Modbus RTU slave 1、3 Mbps、8N1
```

- LAN2：`192.168.2.127`
- Windows 有線網卡：`192.168.2.100`、遮罩 `255.255.255.0`，Gateway/DNS 留白。
- P1：`/dev/ttyUSB0`。
- SSH：`guest@192.168.2.127`；密碼由設備管理者保管，不寫入本文件或 Git。
- Web：`http://192.168.2.127:8080`。

## 2. 每次開機後的檢查順序

在 Windows PowerShell 執行：

```powershell
ping 192.168.2.127
Test-NetConnection 192.168.2.127 -Port 22
Test-NetConnection 192.168.2.127 -Port 8080
```

判讀：

| Ping | TCP 22 | TCP 8080 | 意義 |
|---|---|---|---|
| 失敗 | 失敗 | 失敗 | 檢查電源、LAN2、網線及 Windows 靜態 IP |
| 成功 | 失敗 | 失敗 | Gateway 網路已起來，但 Linux/SSH 尚未完成開機或 SSH 異常 |
| 成功 | 成功 | 失敗 | 可 SSH，Web app 尚未啟動 |
| 成功 | 成功 | 成功 | 可直接開網頁 |

若剛上電，先等待 2～3 分鐘。Ping 通但 SSH 長時間不通時，無法從網路端啟動
Web app，需以本機 Console 檢查 SSH/Linux 開機狀態。

## 3. 手動啟動實機服務

從 Windows 登入：

```powershell
ssh guest@192.168.2.127
```

在 Gateway 執行目前實機部署：

```bash
cd /home/guest/matrix800-iso20816-gateway.new
MATRIX800_SENSOR_PORTS=/dev/ttyUSB0 \
MATRIX800_HTTP_PORT=8080 \
PYTHONUNBUFFERED=1 \
nohup python3 app.py > /home/guest/matrix800-real-sensor.log 2>&1 &
```

確認：

```bash
ps -ef | grep "[p]ython3 app.py"
tail -f /home/guest/matrix800-real-sensor.log
curl -I http://127.0.0.1:8080
```

記錄中應出現 `/dev/ttyUSB0`、`ChipID: 0x97, 0x97, 0x97`。`Ctrl+C` 只會離開
`tail -f`，不會停止背景 app。不要重複啟動多份 app，否則多個 reader 會搶同一個
RS-485 埠。正式部署應使用本專案的 systemd service，避免重開後需手動啟動。

PowerShell 的 `Invoke-WebRequest` 不能在 Gateway 的 Bash 內使用；Gateway 端使用
`curl`，Windows 端才使用：

```powershell
Invoke-WebRequest http://192.168.2.127:8080 -UseBasicParsing
```

## 4. 網頁入口

| 頁面 | 網址 | 用途 |
|---|---|---|
| Live waveform | `http://192.168.2.127:8080/` | 原始三軸波形與 FFT |
| Metrics data | `http://192.168.2.127:8080/metrics` | 溫度、加速度、速度 RMS、ISO Zone |
| Edge AI | `http://192.168.2.127:8080/edge-ai` | Gateway 本機輕量模型展示 |
| Settings | `http://192.168.2.127:8080/settings` | Sensor 名稱與 ISO 機器設定檔 |
| Recording | `http://192.168.2.127:8080/record` | 保存原始 XYZ 訊號 |

## 5. Sensor 是否正常

進入 Metrics data，等待 10～20 秒，應看到：

- Temperature 有合理數值。
- Gravity RMS/Peak/Crest 有 X、Y、Z 三軸。
- Velocity RMS 有 X、Y、Z 三軸，單位為 mm/s RMS。
- 輕敲或振動安裝位置時，數值/波形有反應。

已實測 Sensor 可回傳 Chip ID `0x97/0x97/0x97`、約 33～34 °C，以及三軸
Velocity RMS。感測器完整暫存器與供電資料見
[`sensor-ultest.zh-TW.md`](sensor-ultest.zh-TW.md)。

## 6. 用網頁做 ISO 20816-3 Zone 評估

### 6.1 先準備真實機器資料

- 銘牌額定功率（kW），不能用瞬時功率代替。
- 正常運轉轉速（RPM）。
- Rigid/Flexible 支撐型式，依機器/OEM/基礎設計確認，不要猜。
- 選填的軸高（mm）。

目前實作的 ISO 20816-3 適用條件為額定功率大於 15 kW、轉速至少 120 RPM。
低於這個範圍需使用其他適用標準或 OEM 門檻。

### 6.2 Settings 操作

開啟 `/settings`，在 `/dev/ttyUSB0` 卡片：

1. 勾選 **Enable ISO evaluation**。
2. `Display name` 填測點名稱，例如「馬達驅動端」。
3. `Rated power (kW)` 填銘牌值。
4. `Speed (RPM)` 填正常運轉轉速。
5. `Shaft height` 不確定可留空。
6. `Support type` 選 Rigid 或 Flexible。
7. `Machine group` 建議選 Auto；只有工程確認後才手動覆寫。
8. `Confirmation time` 保持 10 s。
9. `Recovery hysteresis` 保持 0.2 mm/s。
10. 按 **Save settings**，確認出現 `saved`。

### 6.3 Metrics 判讀

回到 `/metrics` 等待至少 10～20 秒。程式取三軸 Velocity RMS 的最大值判定：

| 設定檔 | A/B | B/C | C/D |
|---|---:|---:|---:|
| G1-Rigid | 2.3 | 4.5 | 7.1 |
| G1-Flexible | 3.5 | 7.1 | 11.0 |
| G2-Rigid | 1.4 | 2.8 | 4.5 |
| G2-Flexible | 2.3 | 4.5 | 7.1 |

單位均為 mm/s RMS：

- Zone A：新機/良好狀態。
- Zone B：一般可長期運轉。
- Zone C：不適合長期運轉，安排檢查。
- Zone D：有損壞風險，依現場停機政策立即評估。

ISO 20816 是狀態區域，不是獨立的產品「Pass/Fail」認證。若現場需要二分法，本專案
可把 A/B 視為可接受、C/D 視為需處置，但正式驗收標準仍應由業主、OEM 或測試規範
定義。

### 6.4 正式測試前的重要限制

- RPM > 600 需要 10～1000 Hz Velocity RMS；120～600 RPM 需要 2～1000 Hz。
- 現行程式讀 Sensor `0x0032` 的 Velocity RMS，但尚未透過 `0x47` 自動設定 Sensor
  內部頻帶。
- 正式驗收前需確認 Sensor 頻帶，並以校正振動源或參考儀器比對。
- 系統不會自動停機；需結合負載、趨勢、OEM 限值與現場風險。

## 7. Edge AI 展示的定位

`/edge-ai` 會把真實波形送入 Gateway 上的 Tiny Vibration Fault Classifier。實機曾量到
約 2.9 ms 推論延遲。這個版本使用合成訊號訓練，只適合展示 Edge AI 資料流，畫面的
Normal/Imbalance/Misalignment/Looseness/Bearing impact 不可當成已驗證的故障診斷。

ISO Zone 與 Edge AI 是兩條不同判斷：ISO 使用 Velocity RMS 門檻；Edge AI 使用波形
FFT 特徵和展示模型。

## 8. 快速故障排除

- `Invoke-WebRequest: 無法連接`：先測 Ping、22、8080，不要直接重裝程式。
- Bash 顯示 `Invoke-WebRequest: command not found`：改用 `curl`，或回 Windows PowerShell。
- Ping 失敗且 ARP 無 Gateway：檢查電源、LAN2、網線與電腦 `192.168.2.100/24`。
- SSH 通但 8080 不通：依第 3 節啟動 app，並查看 log。
- Metrics 無數值：確認 P1、5 V 獨立供電、D+/D-、`/dev/ttyUSB0`、slave 1、3 Mbps。
- Edge AI 一直等待：先確認 Metrics/波形持續更新，且沒有重複 app 搶 RS-485。
