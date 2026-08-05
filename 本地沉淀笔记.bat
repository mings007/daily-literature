@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在运行文献追踪流水线（只沉淀笔记，不推送飞书）...
echo 大约需要 1~2 分钟，请稍候...
"C:\Users\mamin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" src\run_daily.py --no-push
echo.
echo 完成！打开 Obsidian 即可查看新笔记。
pause
