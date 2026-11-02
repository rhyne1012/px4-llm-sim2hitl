# autotakeoff：HITL 自動起飛

`autotakeoff.py` 模仿人用 QGC 搖桿起飛：讓 PX4 在 Stabilized 模式，送 MANUAL_CONTROL 桿量，PX4 負責穩住姿態，腳本只給俯仰和油門。`./runbridge takeoff`、`test-takeoff-hold`、`hitl-run`、`deploy-test` 都用它。它的數字由 owner 從 `hitl/aircraft/<飛機>/profile.json` 的 `automation` 傳進來；腳本裡的預設值是同一組 SkySurfer 數字。不寫 PX4 參數。

## 流程

| 階段 | 做什麼 | 換下一段的條件 | 放棄 |
|---|---|---|---|
| 檢查 | 讀回 `SYS_HITL=1` 與 `FW_MAN_P_MAX`（俯仰桿換算成角度）；確認是固定翼、未解鎖、在地上（空速 ≤ 5 m/s、高度在 ±5 m 內） | 全部通過 | 任一不符就不起飛 |
| 模式 | 切 Stabilized，桿量先送 1 s | 進入 Stabilized | 8 s 沒進 |
| 解鎖 | 送解鎖 | 已解鎖 | 10 s 沒解鎖 |
| 滑跑 | 油門以每秒 1 的速度加到 `takeoff_throttle`（0.6） | 空速 ≥ `rotate_cas`（12 m/s） | 40 s 還沒到 |
| 爬升 | 俯仰加到 `climb_pitch`（12°），油門不變 | 高度到目標 −2 m | 180 s 還沒到就直接平飛，記為逾時 |
| 平飛 | 油門 `cruise_throttle`（0.32；2026-11 換成推力隨空速下降的模型後由 0.45／0.35 改來）；俯仰 = `altitude_gain`（0.5°/m）× 高度差 − `climb_damping`（1°/(m/s)）× 爬升率，限 ±8° | 穩定 3 s 後跑起飛後動作（`--after`，例如 `after_takeoff_loiter` 切 Hold，見 [commands README](../commands/README.md)） | — |

- 滾轉桿和方向舵桿一直是 0，翅膀水平靠 PX4 的 Stabilized。
- 高度是 EKF 原點以上的高度。
- **平飛定高會停在目標上下，不在目標上**：只有比例控制，平飛需要的俯仰角要靠高度誤差撐住，偏差約 = 平飛要的俯仰角 ÷ `altitude_gain`（0.5°/m）。例：在巡航油門下平飛要低頭 3° 的機型，會停在目標上方約 6 m。起飛後腳本的開始條件是「目標 ±5 m、|爬升率| ≤ 1.5 m/s，連續 3 s」，所以常常在還在慢慢爬升時就開始（SkySurfer 是約 0.7 m/s）；換飛機時偏差超過 5 m，腳本可能等不到開始。外面的程式要判斷「平飛了沒」，看爬升率接近 0（`./runbridge status` 的 `pilot.climb_mps`），不要看高度接近目標。
- 停止：QGC 的桿動超過 150/1000、`stop`、或遙測中斷，就把控制交還；還在地上時改成放棄（桿歸零、上鎖）。PX4 被上鎖也會停。起飛中（滑跑、爬升）PX4 離開 Stabilized 會停；起飛後動作腳本失敗時也會停（例如 PX4 切到腳本沒要求的模式，見 [commands README](../commands/README.md)）。
- 飛起來以後（巡航、盤旋）**PX4 換模式不放手**，搖桿一直送：OFFBOARD 時固定不動；Stabilized 時平飛定高；其他模式（AUTO_LOITER、Offboard 斷訊後的 Position、RTL…）送中立搖桿。原因：HITL 沒有實體遙控器，這些搖桿就是 PX4 的「遙控」；一停超過 `COM_RC_LOSS_T`（0.5 s），PX4 的遙控斷訊保護就接手（`deploy/00_native` 的設定是 Hold 5 s 後 RTL），蓋掉原本要看的行為，例如外接電腦結束時要的 Hold、Offboard 斷訊後的 Position。所以在 HITL 的紀錄裡看到 RTL，先查是不是飛手放手造成的。

## 換飛機時（AI 要提醒使用者）

這些數字是照 SkySurfer（1.3 kg）和模型的簡易地面（[plant README「地面」](../../plant/README.md)）調的，換飛機很可能要改。改在 `hitl/aircraft/<飛機>/profile.json` 的 `automation`；它會打包進模型 release，改完要 `./runbridge update-model`（AGENTS 第 5 段）。

- `takeoff_throttle`：要能在模型的地面上滑起來（推力大過約 0.2 × 重量），並在 40 s 內到抬頭空速。
- `rotate_cas`：抬頭空速，要高於失速速度並留餘裕。
- `climb_pitch`：爬升角，太大會失速，太小爬不上去。
- `cruise_throttle`：平飛油門。
- `altitude_gain`、`climb_damping`：平飛定高的手感，通常不用動。
- PX4 參數也有關：`FW_MAN_P_MAX`（俯仰桿滿桿對應的角度），以及 Stabilized 的姿態控制。
- 起飛方式：這支腳本只會「地面滑跑起飛」，非固定翼會拒絕。實體 FC 的 HITL 只能從地面靜止開始，所以手擲、彈射、垂直起降的飛機也要用滑跑，或另寫一支起飛腳本。
- SITL 不跑起飛（情境從空中開始），新飛機第一次起飛只能在 HITL 試。失敗時腳本在地上放棄並上鎖，之後照標準 `recover`。
