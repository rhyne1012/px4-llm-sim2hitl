# missions：繞圈任務（航線）

`mission.py` 從一份航線定義（JSON）產生兩種輸出，也能把在 QGC 改過的 plan 匯入回來：

- **QGC 用**：`.plan`。實飛或手動 HITL 時，在 QGroundControl 開啟再上傳。
- **自動化用**：`mavlink_items()` 給起飛後動作腳本（[hitl/commands](../commands/README.md)）用 MAVLink 上傳同一份航點。框架目前還沒有這樣的腳本，要用時自己寫。

兩邊同源，所以 QGC 上的航線和自動化的航線不會分岔。航線分析 [loop_tracking.py](../../analysis/loop_tracking.py) 和檢視圖 [flight_review.py](../../analysis/flight_review.py) 讀同一種定義檔。

```sh
PY="$(./runbridge where python)"
"$PY" -B hitl/missions/mission.py --definition hitl/missions/example_loop.json --plan hitl/missions/example_loop.plan   # 改了 JSON 之後重新產生
```

## 定義檔

- `home`：原點（緯度、經度）；航點是相對它的東／北公尺。
- `altitude_m`：相對 home 的高度，所有航點同一個。
- `airspeed_mps`：第一項 DO_CHANGE_SPEED 設的空速；沒有就飛 FC 的 trim 空速。
- `loop_repeat`：最後的 DO_JUMP 跳回第一個航點的次數；65535 實際上等於一直繞。
- `waypoints_east_north_m`：航點，依飛行順序，一行一個。
- `name`、`note`：名稱，以及為什麼長這樣（改了就補上原因）。

沒有起飛和降落項目：手動或由腳本起飛後再切到 Mission，所以 FC 要 `MIS_TKO_LAND_REQ=0`。腳本要用別的定義檔時，用環境變數 `SIM2HITL_MISSION` 指定。

**範例** `example_loop.json`：在 `hitl/scenarios/ground.json` 起點北邊的順時針跑道。兩段 300 m 直線（WP1→WP2 往西、WP6→WP7 往東），兩端各是半徑 70.6 m 的半圓，每 45° 一個點，所以每個轉角最多轉 45°（16 m/s 時約 20° 坡度）。高度 85 m，空速 16 m/s。複製一份再改成自己的。

## 現場在 QGC 微調之後：匯入回來

在 QGC 存成 `.plan`（Plan 畫面的 File → Save As；如果只上傳到飛控、沒有存檔，先從飛控讀回再存）。帶回來後：

```sh
"$PY" -B hitl/missions/mission.py --definition <定義檔> --import <存下來的.plan> --dry-run   # 先看會改什麼，不寫檔
"$PY" -B hitl/missions/mission.py --definition <定義檔> --import <存下來的.plan>             # 寫回定義檔，並重新產生旁邊的 .plan
```

- 帶回來的是航點位置（換成相對 home 的東／北公尺，取到 1 cm）、高度、速度、DO_JUMP 重複次數。名稱、說明和 home 不變：home 仍是座標原點，QGC 的 planned home 只會列出它離 home 多遠。
- 輸出會列出每個移動過的航點（從哪裡到哪裡、移了幾公尺），以及高度、速度、重複次數的改動。
- 只接受這個工具寫出的那種任務：
  - 第一項是改空速；
  - 接著是同一個相對高度的航點，停留時間、接受半徑、通過半徑都是 0（用 `NAV_ACC_RAD`）；
  - 最後是跳回第一個航點的 DO_JUMP。
- 其他東西整份拒絕，並列出是 QGC 裡的第幾項，不會默默丟掉。例如：起飛點、AMSL 高度、個別航點的半徑、跳到別的點、刪掉改空速的那一項。
- 航點可以增減，至少 4 個；航線分析要求最長的兩段直線至少是其他段的兩倍長。
- 匯入之後，在定義檔的 note 寫下為什麼改，再用 SITL 或 HITL 飛一趟新航線。

## 注意

- `.plan` 裡 DO_JUMP 的目標是 QGC 的 `doJumpId`，由 QGC 上傳時換成任務序號；MAVLink 自動上傳直接用序號。這個換算還沒在 QGC 上實測：第一次載入時，看 DO_JUMP 是否指向第一個航點。
- QGC 存檔時 `doJumpId` 可能重新編號，所以匯入時跟著「第一個航點」走，不看固定的數字。
