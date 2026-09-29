# Matrix800 NPU Setup — Debug Progress Notes

## 網路存取
- 裝置 SSH: `ssh guest@192.168.2.127`
- 預設帳密:`guest` / `guest`,`root` / `root`(來源:Artila 官方 software_guide.md)
- root 不能直接 SSH 登入,要先用 guest 登入,再 `su -` 切換

## Web Dashboard
- app.py 預設監聽 port 80(需要 root 才能綁),可用環境變數改成非特權 port:
  `MATRIX800_HTTP_PORT=8080 python3 app.py`
- host 已經是 `0.0.0.0`,沒問題
- 啟動指令:- 瀏覽器連 `http://192.168.2.127:8080`

## NPU 推論(已完成 ✅)
- 採用 **Mesa/Ethos-U 驅動路線**(`ai-edge-litert`),放棄了原本 NXP `tflite_runtime` + 編譯 Python 3.12 的方案
- 套件:`.venv` 裡已裝 `ai-edge-litert==2.1.6`(任何 Python 版本可用,不需要額外編譯 Python 3.12)
- Delegate 檔案:`/usr/local/lib/litert_delegate.so`
- 模型檔:`models/vibration_backbone_int8_vela.tflite`(Vela 編譯過的 int8 模型)
- `inference.py` 可透過環境變數切換:
  - `MATRIX800_NPU_MODEL`(預設 `models/vibration_backbone_int8_vela.tflite`)
  - `MATRIX800_DELEGATE`(預設 `/usr/local/lib/litert_delegate.so`)

### 曾經卡住的問題:裝置權限不足(已修好)
- 症狀:用 guest(非 root)跑 `app.py` 時,出現
  ```
  [inference] NPU delegate failed (Failed to create ethos_u driver.
  Encountered unresolved custom op: ethos-u.
  ...); stub mode
  ```
  自動退回 CPU stub 模式,無法真正用 NPU。
- 根因:`/dev/ethosu0` 預設權限是 `crw------- root root`,只有 root 能開啟這個裝置節點。`load_delegate()` 本身會成功(只是載入 .so),但建立 `Interpreter`(內部呼叫 `ModifyGraphWithDelegate` 去實際開裝置)時,guest 因為沒有權限打開 `/dev/ethosu0` 而失敗;用 root 跑就完全正常。
- 修法:加一條 udev rule,把 `/dev/ethosu0` 開放給 `dialout` 群組(guest 本來就在這個群組裡,不用額外建群組):
  ```bash
  # 以 root 執行
  echo 'KERNEL=="ethosu0", MODE="0660", GROUP="dialout"' > /etc/udev/rules.d/99-ethosu.rules
  udevadm control --reload-rules
  udevadm trigger --name-match=ethosu0
  ```
- 這條規則是永久的,重開機或裝置重新初始化都會自動套用。套用後 `ls -la /dev/ethosu0` 應該看到 `crw-rw---- root dialout`。
- 驗證方式:用 **guest**(不切 root)跑 `app.py`,啟動 log 裡應該出現
  ```
  INFO: EthosuDelegate: 1 nodes delegated out of 1 nodes with 1 partitions.
  ```
  而不是 `NPU delegate failed ... stub mode`。

## 網路連線(裝置本身)
- Matrix800 有兩個網路孔:`end1`(接電腦,192.168.2.0/24,無對外路由)、`end0`(原本沒接)
- 把 `end0` 接上有網路的路由器後執行 `dhclient end0`,即可對外連網(不影響 end1)
- 確認方式:`ping -c 3 8.8.8.8`

## 下一步
- [x] ~~安裝 Python 3.12(編譯或找 PPA)~~ → 改走 ai-edge-litert 路線,不需要
- [x] ~~建立 venv 並安裝 tflite_runtime wheel~~ → 改裝 `ai-edge-litert`
- [x] 修好 `/dev/ethosu0` 權限,guest 身分下 NPU delegate 也能正常跑
- [ ] 用 Record 頁面錄各動作樣本,Train 頁面訓練分類器
