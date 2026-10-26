# Ubuntu 24.04：環境準備（驗證機的做法）

> 用途：每一項環境為什麼要、驗證機（Ubuntu 24.04 x86-64）怎麼做；怎麼確認在 [README](../README.md)「環境準備」。
> 什麼時候讀：第一次在 Ubuntu 上設定、換一台 Ubuntu 機器，或某一項核對不過時。
> 可以跳過：README「環境準備」的每一項都已經核對通過時。
> 從 README「環境準備」的表搬來，原文不改，只改了連結。做法只是例子，換平台或版本時，先查該項的官方文件。

| 項目 | 為什麼要 | Ubuntu 24.04 的做法（例子） |
|---|---|---|
| Python 環境 | runtime、測試、SITL、分析 | 安裝 [uv](https://docs.astral.sh/uv/)，再 `./runbridge --setup`（venv 的位置：`./runbridge where venv`） |
| MATLAB | 只有改飛機模型（第 1.1 段產碼）才需要：R2026b＋Simulink＋Simulink Coder＋Embedded Coder＋Aerospace Blockset。不需要 Java。沒有 MATLAB 的機器照樣能發布模型 release（第二段改用專案自己的兩個最小標頭檔，見 [plant README](../plant/README.md)「沒有 MATLAB 的機器」） | MathWorks 安裝程式；建議接上 MATLAB MCP，讓 AI 能直接操作 |
| C 編譯器 | plant 與 HIL 函式庫 | 系統內建 gcc（`CC` 可指定別的） |
| PX4 原始碼與工具鏈 | SITL 與編韌體；版本鎖在 [px4/px4_lock.json](../px4/px4_lock.json) | 下載鎖定的 tag 到專案外，`python3 px4/check_px4_tree.py --path <樹> --remember`；工具鏈用 PX4 官方腳本 `bash <樹>/Tools/setup/ubuntu.sh --no-sim-tools`（不裝 Gazebo；會用 sudo）。官方腳本把 PX4 的 Python 套件用 `--break-system-packages` 裝進使用者的 Python；不想動它時，另建一個 venv 放在 PX4 樹外（`pip install -r <樹>/Tools/setup/requirements.txt "setuptools<70"`），編譯時把它的 `bin` 放在 PATH 最前面（2026-10-20 第二台 Ubuntu 的做法；樹裡放 `.venv` 會讓乾淨度核對 FAIL）。樹已經被別的工作改過時，另複製一份乾淨的給本專案，不要動原樹。官方說明：PX4 文件 “Ubuntu Development Environment” |
| **即時排程權限** | 4 ms 迴圈的 worker 執行緒要用即時排程（Linux：SCHED_FIFO，優先權 2）。沒有權限也能跑，但時間餘裕變小：驗證機 600 s 負載最慢晚到 3.7 ms（門檻 4 ms），有權限時 0.47 ms | 桌面程式由 systemd 使用者服務啟動，`/etc/security/limits.d` 管不到；改用 systemd，兩個檔都要：`/etc/systemd/system/user@<UID>.service.d/rtprio.conf` 寫入 `[Service]` 與 `LimitRTPRIO=10`（使用者管理程式本身的上限），以及 `/etc/systemd/user.conf.d/rtprio.conf` 寫入 `[Manager]` 與 `DefaultLimitRTPRIO=10`（它啟動桌面程式時套用的值；只設第一個，實測重開機後桌面程式仍是 0），`sudo systemctl daemon-reload`，再重新登入。暫時只給一個程序：`sudo prlimit --pid <PID> --rtprio=10:10`。官方說明：systemd.exec(5) 的 `LimitRTPRIO=`、sched(7) |
| 序列埠 | 連 Pixhawk（USB CDC-ACM） | 使用者加入 `dialout` 群組；停用 ModemManager（它會試探新插上的序列埠）：`sudo systemctl disable --now ModemManager` |
| QGC | 人看飛控、手動操作（3.1） | 官方 GitHub 發布的 AppImage（驗證機：v5.1.5，`~/Applications/`，核對官方公布的 SHA-256）；系統套件照 QGC 官方 Linux 說明（驗證機補裝 `libfuse2t64 gstreamer1.0-plugins-bad gstreamer1.0-libav libxcb-cursor0`）。**關掉 USB 自動連線**，只用 UDP 14550 連 runtime，否則會和 owner 搶飛控序列埠：設定檔 `~/.config/QGroundControl/QGroundControl.ini` 的 `[AutoConnect]` 把 `autoConnectPixhawk`、`autoConnectSiKRadio`、`autoConnectRTKGPS`、`autoConnectLibrePilot`、`autoConnectZeroConf` 設 `false`、`autoConnectUDP=true`（QGC 第一次啟動建好設定檔、關閉後再改；或在 QGC 的 Application Settings → Comm Links 取消勾選） |
