# 佳明数据导出（Garmin Data Exporter）

一个跨 macOS / Windows 的图形化工具，用来把 Garmin Connect 上的活动和健康数据按日期范围批量导出到本地。支持**中国区**（connect.garmin.cn）和**国际区**（connect.garmin.com）账号，默认选择中国区。

> 本项目调用 Garmin Connect 的非官方 Web API，仅适合导出自己的账号数据。Garmin 可能随时调整接口或增加风控；请合理控制导出频率。

> 普通用户请先阅读：[用户指引](USER_GUIDE_ZH.md)。

## 功能

- 账号密码登录 + 两步验证（MFA）
- 登录会话自动保存在本机，下次通常可免密登录
- 中国区 / 国际区账号切换，默认中国区
- 按日期范围批量导出：
  - 活动列表 `activities.json`
  - 每个活动的概要 JSON、详情 JSON
  - 每个活动的原始 FIT 文件
  - 每日睡眠、心率、步数、压力、身体电量、HRV，按天保存 JSON
- 后台线程导出，不阻塞界面；支持取消、断点续传（跳过已存在文件）
- 导出清单 `manifest.json`，记录统计与错误
- PySide6 原生界面，支持 PyInstaller 打包成 `.app` / `.exe`

## 一键启动（源码版）

### macOS

双击 **`启动.command`**。

如果 Finder 提示没有权限，在终端执行一次：

```bash
chmod +x 启动.command
```

首次启动会在项目目录创建 `.venv`，自动安装 PySide6、garminconnect 等依赖，然后打开界面。首次安装约需下载 150 MB，请保持网络连接。

### Windows

双击 **`启动.bat`**。

首次启动会自动创建 `.venv` 并安装依赖，然后打开界面。如果系统没有 Python 3.12+，脚本会提示安装并打开 Python 下载页。

> 需要 Python **3.12 或更高版本**。Windows 安装 Python 时请勾选 **Add Python to PATH**。
> 依赖安装默认使用清华镜像加速；失败时自动回退到官方 PyPI 和阿里云镜像。也可以用环境变量 `GARMIN_EXPORT_INDEX_URL` 或 `PIP_INDEX_URL` 指定自己的源。

如果双击没有反应，也可以在本目录打开终端手动运行：

```bash
# macOS
python3 bootstrap.py

# Windows
py -3 bootstrap.py
```

## 使用步骤

1. 选择服务器：中国区账号选「中国区」，国际区账号选「国际区」。
2. 输入 Garmin 账号邮箱和密码，点击「登录 Garmin」。
   - 如果本机已有该账号的会话，可以留空密码直接登录。
   - 程序启动时会自动尝试恢复最近保存的会话；恢复成功后无需再次点击登录。
   - 如果保存的会话已失效，请输入密码后手动点击「登录 Garmin」。
   - 如果 Garmin 要求两步验证，界面会出现验证码输入框。输入邮箱/短信收到的验证码并点击「验证」。
3. 选择开始日期、结束日期，或使用「最近 7 天 / 30 天 / 90 天 / 今年」快捷按钮。
4. 选择保存目录和导出内容，点击「开始导出」。
5. 导出完成后点击「打开导出目录」。

长日期范围会产生大量 API 请求。程序在遇到 HTTP 429 时会自动等待并重试，但仍建议分段导出（例如每次 1–3 个月）。

## 导出目录结构

每次导出会创建一个独立目录，例如：

```text
Garmin导出/garmin_export_2026-10-01_2026-10-31_20261031_120000/
├── README.md
├── manifest.json
├── activities/
│   ├── activities.json
│   ├── 2026-10-01_1234567890_Morning_Run/
│   │   ├── activity.json      # 活动概要
│   │   ├── details.json       # 活动详情 / 采样数据
│   │   └── activity_1234567890.fit
│   └── ...
└── health/
    ├── 2026-10-01_sleep.json
    ├── 2026-10-01_heart_rate.json
    ├── 2026-10-01_steps.json
    ├── 2026-10-01_stress.json
    ├── 2026-10-01_body_battery.json
    ├── 2026-10-01_hrv.json
    └── ...
```

- `activities.json` 是所选日期范围内的活动列表，内容为 Garmin 返回的原始数组。
- `activity.json` 是活动概要，`details.json` 是活动详情（时间序列/图表数据）。
- FIT 文件来自 Garmin 的「原始文件」下载接口。该接口返回 ZIP，程序会自动解压并保存其中的 `.fit`。极少数活动没有 FIT 时，会保留 `activity_<ID>_original.zip`。
- 每日健康 JSON 的结构为：

```json
{
  "date": "2026-10-01",
  "type": "sleep",
  "label": "睡眠",
  "exported_at": "2026-10-01T12:00:00+00:00",
  "data": { "...": "Garmin 原始响应" }
}
```

某天没有对应数据时也会生成文件，`data` 为 `null`、`[]` 或 `{}`。

目录名带时间戳，表示一次新的导出。如果勾选「跳过已存在文件（断点续传）」，并且同一日期范围已经导出过，程序会复用 `garmin_export_<开始日期>_<结束日期>/` 目录继续补齐缺失文件；取消勾选则每次创建新的时间戳目录。

## 会话与隐私

- 账号密码只保存在内存中，不写入磁盘，登录成功后会从界面清除。
- 登录成功后的令牌保存在：
  - macOS：`~/Library/Application Support/GarminDataExporter/sessions/<cn|global>/`
  - Windows：`%APPDATA%\GarminDataExporter\sessions\<cn|global>\`
- 令牌文件权限限制为仅当前用户可读（目录 0700，文件 0600）。令牌**没有额外加密**，请像保护密码一样保护本机账户。
- 中国区和国际区的会话分别保存；切换区服不会串用账号。
- 如果保存的账号邮箱与当前输入不一致，程序不会复用旧会话。
- 「清除本机保存的会话」会删除当前区服的令牌，下次需要重新输入密码和验证码。
- 所有导出数据只写入你选择的本地目录，不会上传到任何第三方服务。
- 如需把配置和会话放到指定目录（便携模式），可设置环境变量 `GARMIN_EXPORTER_DATA_DIR`。

## 打包

PyInstaller 不能跨平台交叉编译，请在目标系统上分别构建。

### macOS

```bash
./scripts/build_macos.sh
```

输出：`dist/GarminDataExporter.app`

未签名应用首次打开可能被 Gatekeeper 拦截：右键点击 App →「打开」，或在「系统设置 → 隐私与安全性」中允许。

### Windows

双击或运行：

```bat
scripts\build_windows.bat
```

输出：`dist\GarminDataExporter.exe`（单文件）。该脚本必须在 Windows 目标系统上运行，PyInstaller 不能从 macOS 交叉编译 Windows exe。仓库中的 `GarminExporter-windows-build-kit.zip` 是源码/构建包，不是已经生成的 exe。

Windows Defender / SmartScreen 可能对未签名程序提示风险，选择「更多信息 → 仍要运行」。单文件程序首次启动时会先解压运行组件，启动速度可能略慢。

## 项目结构

```text
app.py                      # GUI 入口
bootstrap.py                # 一键启动：创建/修复 .venv、安装依赖、启动
启动.command / 启动.bat      # 双击入口（macOS / Windows）
requirements.txt            # 运行依赖
requirements-build.txt      # 打包依赖
GarminExporter.spec         # PyInstaller 配置
garmin_exporter/
  config.py                 # 非敏感偏好设置
  exporter.py               # 导出核心（不依赖 Qt，便于测试）
  garmin_service.py         # garminconnect 封装、会话保存、错误翻译
  paths.py                  # 跨平台路径与 JSON 写入
  ui.py                     # PySide6 界面
  workers.py                # 登录 / 导出后台线程
tests/test_exporter.py      # 导出逻辑单元测试
tests/test_ui_smoke.py      # 界面冒烟测试（离屏）
```

运行测试：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Windows：

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 常见问题

**登录失败 / 一直提示验证码错误**

- 确认区服选择正确：中国区账号只能用中国区（connect.garmin.cn）。
- 验证码有时间限制，请尽快输入；验证码错误时可以重试 3 次。
- 如果频繁尝试触发 429，请等待几分钟后再试。

**提示 Cloudflare / 403 / 登录被拦截**

Garmin 的登录风控可能临时拦截请求。稍后重试，或切换网络（例如手机热点）后再登录。不要频繁重复点击登录。

**导出很慢或频繁 429**

每日健康数据是逐日请求的，日期越长请求越多。建议每次导出 1–3 个月；遇到 429 时程序会自动等待并重试。

**身体电量 / HRV 没有数据**

这些指标需要设备支持并在 Garmin Connect 中产生过记录。没有数据时仍会生成 JSON，`data` 为空。

**中国区账号导出的睡眠时间看起来偏移**

garminconnect 对部分中国区账号的睡眠本地时间字段存在已知时区偏移问题。建议以 `*GMT` 字段为准，程序保持 Garmin 原始响应不做改写。

**双击启动脚本没有反应**

在终端手动运行 `python3 bootstrap.py`（macOS）或 `py -3 bootstrap.py`（Windows）查看错误信息。首次启动依赖安装失败通常与网络有关，可直接重试。

**会话失效**

重新输入密码登录即可。若一直失败，可点击「清除本机保存的会话」后重试。
