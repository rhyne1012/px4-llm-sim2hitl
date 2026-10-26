# 接手時先查平台：平台、路徑與工具權限

> 用途：接手時怎麼查平台、路徑與環境，以及工具層面的權限（永久權限、即時排程、AI 工具的允許清單）怎麼一次拿永久的。
> 什麼時候讀（必讀）：第一次在這台電腦用、換平台、權限被擋或要新的權限時。
> 可以跳過：這台電腦已經核對過、這次也沒有碰到權限問題時。
> 從 [AGENTS](../AGENTS.md) 第 2 節搬來，原文不改，只改了連結與指向。綠燈規則、寫入與解鎖前先說、時間敏感測試前、接手用過的 FC，留在 AGENTS 第 2 節（P0–P3）。

- 完整流程只在 Ubuntu 24.04 x86-64 驗證過；各平台驗證到哪一段見 README「驗證矩陣」，macOS 的平台差異見 [platforms/macos.md](../platforms/macos.md)。換平台時，照 [README](../README.md)「環境準備」（每一項的做法在 [platforms/ubuntu.md](../platforms/ubuntu.md)）逐項查官方文件，確認做法再裝；遇到和文件不同的現象，先查證、留證據，再提議更新對應的平台文件。
- 路徑與工具不寫死：MATLAB、編譯器、暫存位置見 `plant/core/toolchain.py`（可用環境變數指定），PX4 原始碼樹見 `px4/check_px4_tree.py`；這台機器實際的位置用 `./runbridge where` 查，文件與指令不寫死某個平台的資料夾。
- 檢查：`./runbridge --check-python`、`python3 px4/check_px4_tree.py`、`./runbridge preflight`。
- **工具層面的權限一律第一次就拿永久的**（不要每次都請人做技術步驟）：不論哪一種權限（系統設定、AI 工具的允許清單、序列埠群組），第一次需要時就給人永久的做法，能合成一次貼完就合成一次；不要先給臨時的、下次再問。臨時的只用來撐到永久的生效（例如重開機前）。範圍是這套專案用得到的，不是讓 AI 能任意 sudo。
  - 即時排程權限：照 [platforms/ubuntu.md](../platforms/ubuntu.md) 表中「即時排程權限」那一列的長期設定，重開機（或完全登出）一次才生效；生效後看程序實際拿到的值（`ulimit -r` 或 `/proc/<PID>/limits`），不能只看設定檔寫了什麼。生效前臨時給：請人執行 `sudo prlimit --pid <AI 程序的 PID> --rtprio=10:10`，再用 `ulimit -r` 確認。
  - AI 工具的允許清單：`runbridge` 的動作（開 owner、解鎖起飛、刷機、參數、開機檔、恢復）會被 AI 工具的自動權限檢查擋下；AI 不能自己改權限設定（也會被擋），請人一次加整個 `runbridge`。Claude Code 是在 `~/.claude/settings.json` 的 `permissions.allow` 加 `Bash(<專案絕對路徑>/runbridge *)`；AI 執行時也用同樣的絕對路徑開頭，不包在 `cd … &&` 或 `timeout` 裡，規則才對得上。
  - 之後碰到新的權限需求也照這樣：一次給永久的，並補進本段，下一個 AI 照著做。
