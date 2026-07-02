; X_crawl NSIS 自定义安装脚本
; 安装结束后写入 Windows 防火墙入站规则，避免后端/前端本地环回被拦。
; 失败不阻塞安装（UAC 拒绝时由应用首次启动再行引导）。

!macro customInstall
  ; 允许 X_crawl 主程序入站（本地环回通信用）
  nsExec::Exec 'netsh advfirewall firewall add rule name="X_crawl" dir=in action=allow program="$INSTDIR\X_crawl.exe" enable=yes profile=any'
!macroend

!macro customUnInstall
  ; 卸载时移除防火墙规则
  nsExec::Exec 'netsh advfirewall firewall delete rule name="X_crawl"'
!macroend
