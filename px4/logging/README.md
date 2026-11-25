# 記憶卡上的記錄清單

PX4 的記錄器開機時讀飛控記憶卡上的 `/fs/microsd/etc/logging/logger_topics.txt`（PX4 官方文件 “Logging” 的自訂記錄項目）。這裡放產生清單的程式；配方要用時，把清單放在配方的 `sd/etc/logging/logger_topics.txt`（或連到這裡產生的檔），`deploy-test` 會照配方放上記憶卡或拿掉（`hitl/host/deploy.py`）。框架自己的配方都不用清單，照 `SDLOG_PROFILE` 記。

## 什麼時候需要（PX4 v1.18）

- 記錄器只有 255 格（`src/modules/logger/logged_topics.h` 的 `MAX_TOPICS_NUM`）。多實例的項目照它要的實例數佔格，不管飛機上有沒有那麼多個；格子滿了，後面的項目只在主控台印 `Too many subscriptions, failed to add: …`，記錄檔裡看不出來。
- v1.18 的預設組變大（固定 163 格，v1.17 是 137 格）。衍生專案 `px4-skysurfer-sim2hitl`（2026-11-25，SkySurfer、Cube Orange+）在 `SDLOG_PROFILE` 49（預設＋高頻率＋debug）和 41 時，debug 組都進不去，自己模組的 `debug_vect` 因此沒記到；v1.17 同樣的 49 塞得下。框架的配方用 17（預設＋高頻率），在 v1.18 上放得下。
- **v1.18 的清單是加在 profile 後面**（v1.17 是取代 profile）：有清單的配方要把 `SDLOG_PROFILE` 設 0，記錄器才只照清單記（`logged_topics.cpp` 的 `initialize_logged_topics`）。`SDLOG_PROFILE` 不是 0 時，清單和 profile 共用 255 格。

## 清單怎麼產生

[make_logger_topics.py](make_logger_topics.py) 照 PX4 自己的原始碼產生，不手寫：

1. 依 `--profile` 的位元，照記錄器的順序展開各組（`add_default_topics()`、`add_high_rate_topics()`、`add_debug_topics()`……）；同一個項目後面的組只改記錄間隔，和記錄器一樣。SITL 專用的那一段不放（清單是給飛控的）。
2. 韌體沒有的項目不放（`--fw-topics`：建置目錄的 `msg/topics_sources`）。
3. 每個實例寫一行（`<項目> <間隔 ms> <實例>`），只寫這架飛機有的實例（`--seen`：這架飛機的 ULog，或從同型飛控紀錄產生的清單）。沒看過的可選項目不放（PX4 開機時它不存在也不會加）；必備的項目至少留實例 0（PX4 一定會加）。

```bash
"$(./runbridge where python)" -B px4/logging/make_logger_topics.py --px4 <PX4 樹> \
  --fw-topics <PX4 建置樹>/build/<韌體目標>/msg/topics_sources --profile 49 \
  --seen <這架飛機的 .ulg 或清單…> --note "<這份清單給誰>" --out <配方>/sd/etc/logging/logger_topics.txt
```

- 衍生專案的例子：profile 49 的清單 201 格（實例數取自它的 SITL FC 紀錄，以及另一個衍生專案用 Cube Orange+ 實飛與 HITL 紀錄做的清單：3 顆 IMU、3 個 EKF、2 個氣壓計、2 個磁力計）。產生器最早是另一個衍生專案 `skysurfer-unstable-sim2hitl` 在 v1.17 上做修模型清單用的（2026-11-21）。
- 換 PX4 版本、換飛控或改模組（新的 topic）要重新產生，再看開頭列的「沒看過而拿掉的可選項目」有沒有該記的。
- 確認有生效：PX4 主控台沒有 `Too many subscriptions`；記錄裡有清單上的項目（`logging N topics from logger_topics.txt` 在開檔前印出，記錄檔裡看不到）。
