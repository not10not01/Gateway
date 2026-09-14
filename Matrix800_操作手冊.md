# Matrix800 震動辨識 Demo 操作手冊

從連線到閘道器開始,到即時動作辨識(live inference)為止的完整操作流程。

## 一、連線到 Matrix800

用 SSH 連進去:

```
ssh guest@192.168.2.127
```

密碼是 guest。

如果需要 root 權限(例如裝套件、改網路設定),先用 guest 登入,再切換:

```
su -
```

密碼是 root。注意 root 沒辦法直接用 SSH 登入,一定要先用 guest 登入再切換。

## 二、確認網路(需要時才做)

如果要連網路安裝套件,先測試看看:

```
ping -c 3 8.8.8.8
```

如果不通,而且 end0 這個網路孔有接到有網路的路由器,執行:

```
dhclient end0
```

再測一次 ping 確認。

## 三、啟動 Dashboard 服務

進到專案資料夾:

```
cd /home/guest/matrix800-iso20816-gateway.new
```

啟用虛擬環境:

```
source .venv/bin/activate
```

啟動服務(指定 port 8080,避免 root 才能綁定的 port 80):

```
MATRIX800_HTTP_PORT=8080 python app.py
```

看到出現 `Running on http://0.0.0.0:8080` 或類似字樣,代表啟動成功。這個視窗要保持開著,不要關掉、不要按 Ctrl+C,不然服務會跟著中斷。

想要背景執行、關掉 SSH 也不會中斷,可以改用:

```
nohup env MATRIX800_HTTP_PORT=8080 python app.py > app.log 2>&1 &
```

之後看 log 用 `tail -f app.log`,要停掉服務用 `pkill -f app.py`。

## 四、打開網頁儀表板

瀏覽器連到:

```
http://192.168.2.127:8080
```

## 五、設定 Settings(第一次使用時)

如果目前只是拿感測器手動製造震動做 demo,沒有裝在實際的馬達或機器上,建議把 Enable ISO evaluation 的勾勾拿掉,這樣才不會跳出跟實際情境對不上的警報等級。Display name 可以填一個好識別的名字,方便儀表板上辨認。其他欄位(Rated power、Speed、Support type 等)在沒開 ISO evaluation 的情況下不會有影響,留預設值即可。改完按 Save settings。

## 六、錄製動作樣本(Record)

先想好要展示的幾種動作,動作差異越明顯,辨識效果越好,例如:靜止不動、規律搖晃、用力敲擊。

到 Record 頁面,先啟用感測器(activate),接著針對每一種動作分別錄製,錄的當下實際做出那個動作。每種動作建議錄 2~3 次、每次幾秒鐘,並取一個好記的名稱(例如 idle、shake、tap)。

## 七、訓練分類器(Train)

到 Train 頁面,按下開始訓練。這一步很快,幾秒內就會完成,終端機會顯示類似下面的訊息,代表訓練成功:

```
[trainer] idle: ... windows → prototype
[trainer] shake: ... windows → prototype
[inference] head reloaded: ... labels [...]
```

如果某一類動作訓練後辨識不準,回 Record 頁面針對那一類多錄幾組樣本,再重新訓練一次即可。

## 八、即時動作辨識(Live Inference)

到 `/edge-ai` 頁面,先確認感測器是啟用狀態。現場實際做出你訓練過的每一種動作,畫面上會即時顯示判斷出的類別跟信心度(confidence)。

也可以故意做一個沒訓練過的動作,展示系統會判斷成信心度較低或不確定的結果,說明這是用相似度比對做分類,而不是寫死的規則。

## 九、其他可以參考的頁面

`/metrics` 頁面可以看到震動的統計數據(例如 RMS),可以在 demo 時輔助說明。

## 疑難排解

如果 Train 頁面出現「backbone interpreter not loaded — can't train」,代表 NPU 推論引擎沒有正確載入,通常是缺少對應的 Python 套件(`ai_edge_litert`)或 delegate 檔案路徑不對,可以參考另一份 SETUP_NOTES.md 裡的環境建置紀錄排查。
