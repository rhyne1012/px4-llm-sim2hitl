# 控制台：HITL／實飛切換與模擬（一個視窗）

衍生專案 2026-11-21 做的：捷徑不要多，一個視窗就能切 HITL／實飛，HITL 時還能跑模擬、看地面站。2026-11-22 搬進框架，改成不綁飛機、飛控與配方。做法是 [sim_to_flight.md](../sim_to_flight.md) 第 1 點：同一份韌體，HITL 和實飛只差參數；列計畫與寫入用 [deploy/flight_switch.py](../../deploy/flight_switch.py)。

```bash
hitl/console/console.sh                    # 桌面捷徑用：開一個終端機視窗跑控制台，網頁自動打開
hitl/console/console.sh --units <檔案>     # 用別的飛控清單（預設 deploy/units.json）
```

**結束**：按網頁上的「關閉控制台」，或關掉它的終端機視窗（Ctrl-C 也可以）。只關瀏覽器不會結束。結束時依序做：
1. 停模擬（有在跑的話），存記錄。
2. 關掉 QGC。QGC 5.1.5 不理會一般的關閉訊號，5 秒後強制結束；它的設定在改的當下就存了，不會丟。
3. 把 QGC 的 USB（飛控）和數傳（SiK radio）自動連線打開。
4. 關 HITL 主程式。

正常結束時終端機視窗會自己關；有狀況時視窗留著，裡面寫停在哪一步。

**切到實飛是人的決定**：只有人按網頁上的「確定寫入」才寫。AI 不替人按（[AGENTS](../../AGENTS.md) 第 3 節：自動流程不關 HITL）。

## 飛控清單（units 檔）

控制台用 `AUTOPILOT_VERSION` 的 uid 認飛控。清單是專案自己的 `deploy/units.json`，框架只附範例 [units.example.json](units.example.json)。沒有清單（或清單有錯）時，網頁只說怎麼做，不讀也不寫飛控；「關閉控制台」照樣能用。

1. 把 `hitl/console/units.example.json` 複製成 `deploy/units.json`。
2. 每塊飛控一筆，key 是 uid：
   - uid 從哪裡來：`./runbridge param-readback` 結果裡 `autopilot_version` 的 `uid`。或先照範例放一筆，控制台核對時，沒列的飛控會顯示完整的 uid。
   - `name`：網頁上顯示的名稱。
   - `role`：`aircraft`（飛機上那塊，在 HITL 和實飛之間切）或 `hitl_only`（只做 HITL 的那塊，`flight` 寫 `null`）。
   - `hitl`、`flight`：`deploy/` 下的配方資料夾名稱。
3. `title`：網頁的標題（預設「HITL／實飛控制台」）；`takeoff_m`：模擬時自動起飛的高度（預設 40 m）。

存檔後按「重新核對」，就用新的清單。uid 是那塊板子的身分，放在自己專案的 `deploy/units.json`。

**只有 `aircraft` 會切到實飛**，而且它的兩份配方要成對：同一份韌體、同樣的記憶卡檔案（開機檔、記錄清單），HITL 那份 `SYS_HITL` 1、實飛那份 0。核對時會用 `flight_switch.py` 檢查；對不上時不切到實飛（切回 HITL 照樣可以，由 HITL 配方自己的核對把關），網頁寫出哪裡不同。自己查：`"$PY" -B deploy/flight_switch.py --pair deploy/<HITL 配方> deploy/<實飛配方>`。`hitl_only` 的飛控不會切到實飛。

配方的韌體檔（`firmware/` 裡的 `.px4` 和 `parameters.json.xz`）是在本機編的，不進 git。實飛那份沒有在這台電腦編過時，核對會寫要先 `./runbridge build-firmware --release deploy/<實飛配方>`。

## 畫面

- **上半**：
  - 接的是哪塊飛控、現在是 HITL 還是實飛（`SYS_HITL`）。
  - 設定核對：參數讀回後用 `deploy/check_params.py` 對配方，記憶卡的開機檔和記錄清單也對配方的 `sd/`。
  - 讀回用哪份參數表：這次開著時最後認出的那塊飛控的 HITL 配方，還沒認出過就用清單第一塊的。飛控是另一份韌體時參數名稱對不上，讀回只差在名稱就照樣用（它還是會說是哪塊飛控），再用那塊自己的 HITL 配方讀一次。韌體是不是配方的，由 `check_params` 判。
  - 核對完的日誌寫出 HITL 和實飛配方差幾個值。
- **切到 HITL／切到實飛**：
  1. 先讀回、列計畫（`flight_switch.py`）：要寫哪些值；配方以外、不是預設的值改回預設，標「配方沒有，改回預設」；PX4 寫完輸出功能後會自己改的值（新舵機的中立 1500、新馬達的範圍 1100–1900，見 [host/pwm_defaults.py](../host/pwm_defaults.py)）也標出來，等它改完再寫回。
  2. 跳出確認框，你按「確定寫入」才寫：經 HITL 主程式的 agent 埠（UDP 14560），每個值都要讀到飛控的回音，`GPS_1_CONFIG`、`SYS_HITL` 最後寫，寫到一半失敗時飛控還是原本的模式。
  3. 寫完重開，再核對一次。
  - 列出計畫後超過 10 分鐘，或飛控重新連線過，要重按切換。
  - 韌體不是配方的：先燒錄（`./runbridge deploy-test --release deploy/<配方> --flash`，飛控要在 HITL）。
  - 記憶卡的檔案不對時（例如剛用過別的配方），先用 `deploy-test --reuse --no-hitl` 寫 HITL 配方的參數、開機檔和記錄清單，只能在 HITL 做。
- **模擬**（HITL、核對 PASS 時才能按）：
  - 開始：打開 QGC（設定要關 USB 自動連線，控制台會先關好），模型放到地面。
    - 自動起飛：到 `takeoff_m` 後交給 PX4 盤旋（`after_takeoff_loiter`），動 QGC 的搖桿就接手。
    - 或自己飛：QGC 的搖桿或遙控器（[hitl/README](../README.md)「用 QGC 搖桿手動飛」）。飛控接著實體遙控器時，誰優先看配方的 `COM_RC_IN_MODE`。
  - 從地面重來：停模型、恢復（飛控重開），再開始。
  - 結束並存記錄：飛控記錄下載兩次核對，放在 cache 的 `manual_flights/console_<時間>/`。
  - 顯示高度、空速、PX4 模式；地圖、姿態、警告看 QGC。
  - 輸出：從飛控的 `PWM_MAIN_FUNCn`、`PWM_AUX_FUNCn` 讀出哪些通道是舵面（201–208）、哪些是馬達（101–112），例如 `MAIN3`、`AUX1`。HITL 時馬達有輸出就警告：模擬時馬達會轉，要拆槳。

## 要注意

- **QGC 的自動連線**：控制台開著時，QGC 不能用 USB 或數傳自動連線，不然會和 HITL 主程式搶飛控的序列埠。所以控制台第一次碰飛控前，如果 QGC 開著，會請你先關掉；接著把這兩個關掉，只留 UDP（QGC 經 HITL 主程式連飛控）。設定檔是 `~/.config/QGroundControl/QGroundControl.ini` 的 `[AutoConnect]`。
- **CPU 綁定**：照這台電腦的隔離核心（`/sys/devices/system/cpu/isolated`）自動決定。例如隔離 7、15：HITL 主程式在 CPU 7，控制台和它開的其他程式在其餘的核心。沒有隔離核心的電腦就不綁。
- 網頁是 `http://127.0.0.1:8765/`，只有本機能開；每個按鈕都要帶啟動時產生的 token，其他網頁按不到。一次只能開一個（和 `hitl/qgc_session.py` 共用同一把鎖）。
- 切換、模擬都只在未解鎖、沒有待恢復時做；有狀況時頁面會寫停在哪一步，照 [hitl/README](../README.md) 的恢復規則處理。
- **空速只在實飛模式校**：空速零點（`SENS_DPRES_OFF`、`SENS_DPRES_ANSC`）是飛控自己的校正，放進兩份配方的 `fc_owned`，核對不比、切換就不會動它（衍生專案 2026-11-21 的做法）；HITL 時在 QGC 校空速，會用模擬的差壓把實飛的值蓋掉。
- 實飛前：工具只保證參數和記憶卡，其他照自己的檢查表（[sim_to_flight.md](../sim_to_flight.md) 第 3 點）。

## 桌面捷徑（Ubuntu GNOME）

捷徑的路徑屬於這台機器，不進專案；每台機器自己建一次。

```ini
[Desktop Entry]
Type=Application
Name=HITL／實飛控制台
Exec=gnome-terminal --title=HITL／實飛控制台 -- <專案>/hitl/console/console.sh
Icon=utilities-terminal
Terminal=false
```

- `<專案>` 換成這台機器上專案的絕對路徑；`Icon` 也可以寫圖示檔的絕對路徑。
- 存成 `~/.local/share/applications/hitl-console.desktop`（應用程式選單找得到），或放在桌面（桌面資料夾：`xdg-user-dir DESKTOP`）。
- `chmod +x <檔案>`。
- 放桌面的還要 `gio set <檔案> metadata::trusted true`（等於右鍵 Allow Launching），不然點兩下不會執行。
