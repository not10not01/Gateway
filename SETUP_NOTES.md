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

## NPU 推論(尚未完成)
- 目前是 NXP 驅動路線(`/usr/local/lib/libethosu_delegate.so` 存在)
- 卡在 `tflite_runtime` 沒裝 → inference 是 stub mode,無法 train
- 對應 wheel:`/opt/npu/wheels/tflite_runtime-2.18.0-cp312-cp312-linux_aarch64.whl`
- 這個 wheel 專屬 Python **3.12**,但系統預設是 Python 3.14.4,apt 套件庫也只有 python3.14,沒有 3.12
- 待辦選項:
  1. 從原始碼編譯安裝 Python 3.12(需要 build-essential 等套件)
  2. 或改走 Mesa 驅動路線(`ai-edge-litert`,任何 Python 版本可用),但要改 `/etc/modprobe.d/blacklist.conf` + 重開機 + 修改 app.py 的 import

## 網路連線(裝置本身)
- Matrix800 有兩個網路孔:`end1`(接電腦,192.168.2.0/24,無對外路由)、`end0`(原本沒接)
- 把 `end0` 接上有網路的路由器後執行 `dhclient end0`,即可對外連網(不影響 end1)
- 確認方式:`ping -c 3 8.8.8.8`

## 下一步
- [ ] 安裝 Python 3.12(編譯或找 PPA)
- [ ] 裝好後建立 venv 並安裝 tflite_runtime wheel
- [ ] 重啟 app.py,確認 `[inference] tflite_runtime not available` 這行警告消失
- [ ] 用 Record 頁面錄各動作樣本,Train 頁面訓練分類器
