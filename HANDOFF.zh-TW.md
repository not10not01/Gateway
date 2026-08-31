# Matrix-800 ISO 20816 可攜式交接手冊

> 日常操作請優先閱讀 [`docs/operation-guide.zh-TW.md`](docs/operation-guide.zh-TW.md)。
> 該文件反映目前實機使用的 `/home/guest/matrix800-iso20816-gateway.new`、8080 埠、
> 真實 Sensor、Edge AI 與 ISO 網頁流程；本手冊其餘章節著重全新電腦/正式 `/opt` 部署。

這個資料夾可以複製到另一台 Windows、Linux 電腦或 Matrix-800。建議架構是：

```text
一般電腦（設定、瀏覽器、SSH）
        │ Ethernet / LAN2
        ▼
Matrix-800（實際執行 Python、Modbus、ISO 20816 與 NPU）
        │ RS-485 P1～P4
        ▼
振動 Sensor（尚未到貨時先執行單元測試）
```

## 已在實機確認的 Gateway 資訊

| 項目 | 實測結果 |
|---|---|
| 產品 | Artila Matrix-800 |
| LAN2 | `end1`，`192.168.2.127/24` |
| SSH | TCP 22，可使用 `guest` 登入 |
| OS | Ubuntu 26.04 LTS (Resolute Raccoon) |
| Kernel | 6.18.20-matrix800，aarch64 |
| Python | 3.14.4 |
| NPU | `/dev/ethosu0`，NXP Ethos-U 路線 |
| RS-485 | `/dev/ttyUSB0`～`/dev/ttyUSB3` |
| RAM | 約 1.9 GiB |
| Root filesystem | 約 13 GiB，可用約 11 GiB |

> 公開軟體指南的 Ubuntu／kernel 範例和這台實機不同。部署時以表中的實測值為準。

## A. 在另一台 Windows 電腦連接 Gateway

1. 將網路線插到 Matrix-800 **LAN2**。
2. 將 Windows 有線網卡設成：

   ```text
   IP：192.168.2.100
   Mask：255.255.255.0
   Gateway：留白
   DNS：留白
   ```

3. 測試：

   ```powershell
   ping 192.168.2.127
   Test-NetConnection 192.168.2.127 -Port 22
   ssh guest@192.168.2.127
   ```

4. 若另一台電腦原本有 Wi-Fi，不需要關閉 Wi-Fi；Wi-Fi 繼續負責上網，有線網路只負責 Gateway。

## B. 沒有 Sensor 時先測程式

一般電腦安裝 Python 3.12 以上。解壓後在專案根目錄：

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

預期為 7 個測試全部 `OK`，內容包含：

- PDF 四組 A/B/C/D 門檻。
- 75 kW、3.2 mm/s、Rigid → G2-R Zone C。
- 場域案例 S1=3.77、S2=5.62 mm/s 在 Rigid/Flexible 下的結果。
- RPM 頻帶、告警確認時間與恢復遲滯。
- `machine_profiles.json` 儲存與重新載入。

沒有 Sensor 時，完整 `app.py` 可以啟動，但不會出現即時測點；這是正常狀態。

## C. 複製專案到 Gateway

在 Windows 專案資料夾的上一層執行：

```powershell
scp -r matrix800-iso20816-gateway guest@192.168.2.127:/home/guest/
```

登入 Gateway：

```bash
ssh guest@192.168.2.127
su -
mv /home/guest/matrix800-iso20816-gateway /opt/
cd /opt/matrix800-iso20816-gateway
```

安裝與測試：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

這台實機為 `/dev/ethosu0`，因此 `inference.py` 應使用：

```text
tflite_runtime
/usr/local/lib/libethosu_delegate.so
models/vibration_backbone_int8_vela.tflite
```

## D. Sensor 到貨後

先閱讀 `docs/sensor-ultest.zh-TW.md`。ULTEST Sensor 規格為 **5 VDC、<100 mA**；
P1 D+/D- 只有 RS-485 資料，不提供 Sensor 電源。

1. 將 Sensor 的 RS-485 A/B 接到 P1 D+/D-，5 V 與 GND 接獨立穩壓電源。
2. P1 對應 `/dev/ttyUSB0`。
3. 核對 Sensor 是否符合目前程式假設：

   ```text
   Modbus slave ID：1
   Serial：3,000,000 baud、8N1
   Raw FIFO：FC04 0x02
   Sample-rate：FC06 0x01
   Velocity RMS：FC03 0x0032，三軸，register / 100 = mm/s RMS
   ```

4. 最重要的是確認 `0x0032` 的速度 RMS 頻帶：
   - RPM > 600：10～1000 Hz。
   - 120～600 RPM：2～1000 Hz。

5. 啟動：

   ```bash
   sudo /opt/matrix800-iso20816-gateway/.venv/bin/python \
     /opt/matrix800-iso20816-gateway/app.py
   ```

6. 電腦瀏覽器開啟 `http://192.168.2.127/`。

## E. ISO 20816 設定

到 `http://192.168.2.127/settings`，對每個測點設定：

- 額定功率 kW：使用銘牌額定值。
- RPM。
- Rigid/Flexible 支撐型式。
- Group：建議 Auto。
- Confirmation time：預設 10 秒。
- Recovery hysteresis：預設 0.2 mm/s。

到 `/metrics` 查看最大軸 Velocity RMS、G1/G2-R/F、頻帶、A/B/C/D Zone 與處置建議。

## F. 開機自動執行

```bash
sudo cp deploy/matrix800-iso20816.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now matrix800-iso20816
sudo journalctl -u matrix800-iso20816 -f
```

## G. 安全與限制

- 系統只提供狀態評估，不會自動停機。
- 正式停機需結合 OEM 限值、趨勢、負載及現場風險。
- 初始帳密只用於首次設定；完成後應更改 `guest`、`root` 密碼，且不得把密碼寫入 Git。
- 不要在未確認 Sensor 頻帶與校正前，把 Zone 當作正式驗收結果。

更完整的 ISO 說明請見 `docs/iso20816.zh-TW.md`。
