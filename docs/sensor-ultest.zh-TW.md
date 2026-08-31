# ULTEST 微型多軸振動 Sensor 整合指南

本章依據 ULTEST 微型多軸振動感測器簡報與 2025-09-24 版
`Vibration_RS485_ModbusRTU` 通訊說明整理。實際接線仍以出貨線材標示與 Sensor
序號對應資料為準。

## 1. Sensor 規格

| 項目 | 規格 |
|---|---|
| 尺寸 | 22 x 20 x 15 mm |
| 最大重量 | 34 g |
| 軸數 | X/Y/Z 三軸 |
| 量測範圍 | 可選 ±2 g 至 ±16 g |
| 頻寬 | DC 至 2 kHz 或 5 kHz |
| 線性度 | ±0.1% |
| 數位解析度 | 16-bit/axis |
| 最大 ODR | 15625 Hz |
| 供電 | **5 VDC，<100 mA** |
| 接頭 | M8，8-pin，側出線 |
| 安裝 | Stud mounting |
| 防護 | IP67 |
| 工作溫度 | -20 至 85°C |
| 線長 | 15 m 或 30 m；RS-485/RS-422 最長宣稱 100 m |

> Matrix-800 P1 的 D+/D- 只承載 RS-485 資料，**不提供 Sensor 電源**。
> 不可把 12-24 V Gateway 電源直接送入 Sensor；本 Sensor 規格為 5 V。

## 2. 通訊設定

| 項目 | 值 |
|---|---|
| Protocol | Modbus RTU Slave |
| Slave ID | 1 (`0x01`) |
| Baud | 3,000,000 bps（預設）或 115,200 bps |
| Format | 8 data bits, no parity, 1 stop bit (8N1) |
| Function codes | FC03、FC04、FC06；部分功能另用非標準 Bulk/FC16 |
| Endian | Big-endian register data；Modbus CRC 在 wire 上 low byte first |

- **3 Mbps**：可讀 raw FIFO 與所有特徵值。
- **115200 bps**：僅支援特徵參數，不支援 raw data 連續讀取。
- 修改 baud 要先寫 High `0x17`，再寫 Low `0x18`，完成後 Sensor 斷電至少
  3 秒再上電。未確認連線前不要執行此寫入。

Matrix-800 P1 預期對應 `/dev/ttyUSB0`。專案的真實 Sensor 啟動設定為：

```bash
MATRIX800_SENSOR_PORTS=/dev/ttyUSB0 MATRIX800_HTTP_PORT=8080 python3 app.py
```

## 3. 接線重點

通訊文件中的 DB9-to-terminal adapter 定義如下：

| Adapter pin | RS-485 用途 |
|---:|---|
| 1 | RS-485 A / Data+ |
| 2 | RS-485 B / Data- |
| 5 | GND |
| 6 | 5 V VCC |

連接 Matrix-800 P1 時：

```text
Sensor/adapter RS-485 A / Data+  -> P1 D+
Sensor/adapter RS-485 B / Data-  -> P1 D-
Sensor 5 V VCC                   -> 獨立穩壓 5 V 正極
Sensor GND                       -> 5 V 電源負極
```

若有供電但完全收不到 bytes，斷電後交換 D+ 與 D- 再試；A/B 命名在不同廠牌
之間可能相反。

## 4. Register map

### FC04 Input Registers（raw / identity）

| 功能 | Address | Length | 說明 |
|---|---:|---:|---|
| Sample rate / conversion control | `0x01` | 1 | FC06 寫入；I-type: 7812/3906/1953 Hz |
| FIFO remaining length | `0x02` | 1 | 每一 XYZ sample 增加 3 registers |
| Raw XYZ stream | `0x03-0x7D` | 3-123 | signed int16 XYZ |
| Chip ID | `0x80` | 3 | 連線探測，固定三軸 ID |
| Latest XYZ | `0x83-0x85` | 3 | 讀取後清除舊暫存 raw data |

Raw data 必須先以 FC06 `0x01` 寫入 sample rate 才會開始轉換。現行程式採用
7812 Hz，並以 `int16 / 8192` 轉成 g；`8192` 係既有 Demo 的量程假設，正式校驗
前應向供應商確認目前 ±g range 對應的 LSB/g。

### FC03 Holding Registers（計算特徵）

所有三軸欄位都必須一次讀取 length=3。

| 特徵 | Address | 換算 | 建議更新率 |
|---|---:|---|---:|
| Temperature | `0x14` | value / 100 °C | 5 Hz |
| UCID | `0x1B` | 32-bit, length=2 | - |
| Firmware | `0x1D` | 32-bit, length=2 | - |
| Acceleration RMS | `0x1E` | value / 1000 g | 5 Hz |
| Acceleration Peak | `0x1F` | value / 1000 g | 5 Hz |
| Acceleration Crest Factor | `0x20` | value / 1000 | 5 Hz |
| Acceleration Skewness | `0x21` | value / 1000 | 2-5 s |
| Acceleration Kurtosis | `0x22` | value / 1000 | 2-5 s |
| Velocity RMS | `0x32` | value / 100 mm/s | 5 Hz |
| Velocity Peak | `0x33` | value / 100 mm/s | 5 Hz |
| Velocity Crest Factor | `0x34` | value / 1000 | 5 Hz |
| Velocity primary frequency XYZ | `0x3C` | value / 10 Hz | 2-5 Hz |
| Acceleration primary frequency XYZ | `0x3D` | value / 10 Hz | 2-5 Hz |
| Standard Key 1 | `0x45` | Acc RMS + Crest + Velocity RMS，length=9 | 2 Hz |
| Standard Key 2 | `0x46` | Skewness + Kurtosis + reserved，length=9 | 5-10 s |

通訊文件的 register 總表定義 Temperature 為 `value / 100`，但後段範例另列
ADC code 校正式；兩段內容不一致。現行程式依總表使用 `/100`，正式量測時需用
已知溫度交叉校驗，再決定是否改採範例公式。

Velocity RMS 的有效頻寬標示為 10 Hz 至 1 kHz，正好是本專案
ISO 20816-3（RPM > 600）使用的 broad-band 範圍。

## 5. 與 ISO 20816 / Edge AI 的分工

- ISO 20816 使用 Sensor `0x32` 的三軸 Velocity RMS，取最大軸做 A/B/C/D Zone。
- Edge AI 使用 3 Mbps raw FIFO 建立波形、FFT 與故障分類。
- Crest Factor、Kurtosis 與 IMP 適合補強 bearing impact 的早期異常判定。
- `0x48` 可回傳 IMP、主頻、1x/2x/前10倍頻與剩餘 RMS，但需要先透過
  `0x47`（FC16）設定頻率上下限；現行程式尚未啟用此功能。

## 6. 連線驗證順序

1. 確認獨立 5 V 供電與 GND。
2. P1 D+ / D- 接妥，確認 `guest` 屬於 `dialout`。
3. 以 3 Mbps、8N1、Slave 1，FC04 讀 `0x80`, length=3。
4. 若無回應：斷電交換 D+/D-；仍無回應再測 115200。
5. Chip ID 成功後，先用 FC03 讀 `0x14`、`0x32`、`0x3C`。
6. 只有在 3 Mbps 且特徵值正常後，才用 FC06 `0x01=7812` 啟動 raw FIFO。

寫入 sample rate、baud 或 frequency range 都會改變 Sensor 狀態；正式測試前應先
完成上述唯讀探測並保存原始設定。
