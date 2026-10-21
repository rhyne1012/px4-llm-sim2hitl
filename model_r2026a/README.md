# R2026a 版模型（備份）

`FW_SkySurfer_HIL.slx` 是 `model/FW_SkySurfer_HIL.slx`（R2026b，main 061774f）用 Simulink 匯出成舊版轉成的 R2026a 版，給只有 R2026a 的電腦用；內容相同，沒有方塊被拿掉。

- 不放在 `model/`：那裡多一個檔案，`hitl/update.py` 就會認為模型來源變了。
- 在 R2026a 使用：複製去取代 `model/FW_SkySurfer_HIL.slx`（開模型時會讀同資料夾的 `PX4_HIL_preload.m`），再跑一次 `python -B hitl/update.py --generate`。
- 只是備份，不會跟著 R2026b 版自動更新；原模型改了要重新轉。
