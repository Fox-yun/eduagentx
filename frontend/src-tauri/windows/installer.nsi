Unicode True

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

!ifndef APP_EXE
  !error "APP_EXE must point to the compiled EduAgentX.exe"
!endif
!ifndef APP_ICON
  !error "APP_ICON must point to the EduAgentX .ico file"
!endif
!ifndef OUTPUT_FILE
  !define OUTPUT_FILE "EduAgentX_4.1.0_x64-setup.exe"
!endif
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "4.1.0"
!endif
!ifndef VIPRODUCT_VERSION
  !define VIPRODUCT_VERSION "4.1.0.0"
!endif
!ifndef WEBVIEW2_BOOTSTRAPPER
  !error "WEBVIEW2_BOOTSTRAPPER must point to the Microsoft WebView2 bootstrapper"
!endif
!ifndef WEBVIEW2_STANDALONE
  ; If WEBVIEW2_STANDALONE is not provided, fall back to the bootstrapper (requires network)
  !define WEBVIEW2_STANDALONE ""
!endif

!define PRODUCT_NAME "EduAgentX"
!define PRODUCT_PUBLISHER "EduAgentX Team"
!define PRODUCT_EXE "EduAgentX.exe"
!define PRODUCT_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\EduAgentX"
!define PRODUCT_REGISTRY_KEY "Software\EduAgentX"
!define WEBVIEW2_CLIENT_KEY "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
!define KEYRING_SERVICE "com.eduagentx.desktop"

Name "${PRODUCT_NAME}"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\${PRODUCT_NAME}"
InstallDirRegKey HKCU "${PRODUCT_REGISTRY_KEY}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompress auto
SetDatablockOptimize on
CRCCheck on
XPStyle on
ManifestDPIAware true
Icon "${APP_ICON}"
UninstallIcon "${APP_ICON}"
BrandingText "${PRODUCT_NAME} ${PRODUCT_VERSION}"

VIProductVersion "${VIPRODUCT_VERSION}"
VIAddVersionKey /LANG=2052 "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=2052 "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey /LANG=2052 "FileDescription" "${PRODUCT_NAME} Windows x64 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${PRODUCT_VERSION}.0"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Copyright © 2026 ${PRODUCT_PUBLISHER}"

!define MUI_ABORTWARNING
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "启动 ${PRODUCT_NAME}"
!define MUI_FINISHPAGE_NOAUTOCLOSE

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Function IsWebView2Installed
  ClearErrors
  SetRegView 32
  ReadRegStr $0 HKLM "${WEBVIEW2_CLIENT_KEY}" "pv"
  ${If} ${Errors}
    ClearErrors
    ReadRegStr $0 HKCU "${WEBVIEW2_CLIENT_KEY}" "pv"
  ${EndIf}

  ${If} ${Errors}
    Push "0"
  ${ElseIf} $0 == ""
    Push "0"
  ${Else}
    Push "1"
  ${EndIf}
FunctionEnd

Function EnsureWebView2
  Call IsWebView2Installed
  Pop $0
  ${If} $0 == "1"
    Return
  ${EndIf}

  !if "${WEBVIEW2_STANDALONE}" != ""
    ; Use the offline standalone installer (no network required)
    DetailPrint "正在安装 Microsoft Edge WebView2 Runtime (离线安装)..."
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File "/oname=MicrosoftEdgeWebView2RuntimeInstallerX64.exe" "${WEBVIEW2_STANDALONE}"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebView2RuntimeInstallerX64.exe" /silent /install' $1
    DetailPrint "WebView2 离线安装程序返回代码：$1"
  !else
    ; Fall back to the Evergreen Bootstrapper (requires network)
    DetailPrint "正在安装 Microsoft Edge WebView2 Runtime (在线安装)..."
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File "/oname=MicrosoftEdgeWebview2Setup.exe" "${WEBVIEW2_BOOTSTRAPPER}"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $1
    DetailPrint "WebView2 安装程序返回代码：$1"
  !endif

  Call IsWebView2Installed
  Pop $0
  ${If} $0 != "1"
    MessageBox MB_ICONSTOP|MB_OK "Microsoft Edge WebView2 Runtime 安装失败（代码 $1）。请检查网络连接或使用离线安装包。"
    Abort
  ${EndIf}
FunctionEnd

Section "安装 ${PRODUCT_NAME}" SEC_MAIN
  SectionIn RO
  SetShellVarContext current
  Call EnsureWebView2

  SetOutPath "$INSTDIR"
  SetOverwrite on
  File "/oname=${PRODUCT_EXE}" "${APP_EXE}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 ${PRODUCT_NAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0

  WriteRegStr HKCU "${PRODUCT_REGISTRY_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${PRODUCT_REGISTRY_KEY}" "Version" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${PRODUCT_EXE}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${PRODUCT_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${PRODUCT_UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\卸载 ${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  ; Ask user about user data BEFORE deleting anything
  MessageBox MB_ICONQUESTION|MB_YESNO "是否同时删除 EduAgentX 的配置、缓存和登录会话？（下载的文件不会被删除）" IDNO SkipDataCleanup

  ; Delete app data directories — cover all locations used by ProjectDirs:
  ; Local AppData (cache), Roaming AppData (config), and the legacy install dir.
  RMDir /r "$LOCALAPPDATA\EduAgentX\EduAgentX"
  RMDir /r "$LOCALAPPDATA\EduAgentX\EduAgentX\Cache"
  RMDir /r "$APPDATA\EduAgentX\EduAgentX"
  RMDir /r "$APPDATA\EduAgentX"

  ; Clean up Windows Credential Manager entries (Keyring)
  ; The Rust keyring crate on Windows uses Credential Manager with the service
  ; name as the Target Name. We try both the exact service name and common
  ; variants to ensure thorough cleanup.
  nsExec::Exec 'cmdkey /delete:${KEYRING_SERVICE}'
  Pop $0
  DetailPrint "清理凭据管理器返回代码：$0"
  ; Also try the generic variant without dots (some keyring versions normalize)
  nsExec::Exec 'cmdkey /delete:eduagentx.desktop'
  Pop $0

  SkipDataCleanup:
  ; Always delete program files, logs, and cache (even if user chose to keep data)
  Delete "$INSTDIR\${PRODUCT_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  ; Always clean up logs and cache
  RMDir /r "$LOCALAPPDATA\EduAgentX\EduAgentX\logs"
  RMDir /r "$LOCALAPPDATA\EduAgentX\EduAgentX\Cache\media"

  DeleteRegKey HKCU "${PRODUCT_UNINSTALL_KEY}"
  DeleteRegKey HKCU "${PRODUCT_REGISTRY_KEY}"
SectionEnd
