# 佳明数据导出用户指引

这是一份给普通用户的快速说明。程序只导出你自己的 Garmin Connect 数据，账号密码不会保存到磁盘。

## 1. 先选择启动方式

### 已打包版本

- macOS 使用 `GarminDataExporter.app`。
- Windows 使用 `GarminDataExporter.exe`。
- Windows 构建包 ZIP 只包含源码和打包脚本，不是现成的 exe。需要在 Windows 电脑上运行 `scripts\build_windows.bat` 才能生成 exe。

### 源码版本

电脑需要 Python 3.12 或更高版本，并保持网络连接：

- macOS：双击 `启动.command`。
- Windows：双击 `启动.bat`。

第一次启动会创建虚拟环境并安装依赖，可能需要几分钟。Windows 安装 Python 时请勾选“Add Python to PATH”。

## 2. 登录账号

1. 选择服务器：
   - 中国区账号选择“中国区”。
   - 国际区账号选择“国际区”。
2. 输入 Garmin 账号邮箱。
3. 第一次使用时输入密码并点击“登录 Garmin”。
4. 如果 Garmin 要求两步验证，输入邮箱或手机收到的验证码，再点击“验证”。

登录成功后，程序会在本机保存会话令牌。下次启动时，程序会自动尝试恢复最近保存的会话，不需要再次选择账号或点击登录。

如果会话已经过期，程序会提示自动恢复失败。此时输入密码，再点击“登录 Garmin”即可重新建立会话。程序不会因为自动恢复失败而删除旧会话。

## 3. 导出数据

1. 选择开始日期和结束日期。
2. 选择保存目录。默认目录是用户的“下载/Garmin导出”。
3. 选择要导出的内容：活动、睡眠、心率、步数、压力、身体电量或 HRV。
4. 点击“开始导出”。
5. 完成后点击“打开导出目录”。

“跳过已存在文件（断点续传）”默认开启。同一日期范围再次导出时，程序会复用原目录，只补齐缺少的文件。导出过程中可以点击“取消导出”，已经写入的文件会保留。

日期范围越长，请求次数越多。建议一次导出 1 到 3 个月的数据。

导出目录中常见的文件包括：

- `activities/activities.json`：活动列表。
- 每个活动目录中的 `activity.json`、`details.json` 和 FIT 原始文件。
- `health/` 下按日期保存的健康数据 JSON。
- `manifest.json`：本次导出的统计和错误记录。

## 4. 生成 HTML 分析报告（可选）

源码目录提供了离线报告工具。它不会联网，也不会修改原始导出数据。在终端执行：

```bash
python tools/garmin_report.py "/path/to/garmin_export目录"
```

报告默认生成在导出目录中的 `Garmin数据分析报告.html`，用浏览器打开即可。也可以指定输出文件：

```bash
python tools/garmin_report.py "/path/to/garmin_export目录" -o "/path/to/report.html"
```

## 5. 会话和隐私

会话令牌保存在当前用户目录：

- macOS：`~/Library/Application Support/GarminDataExporter/sessions/`
- Windows：`%APPDATA%\GarminDataExporter\sessions\`

令牌文件只允许当前系统用户读取，但没有额外加密，请像保护密码一样保护自己的电脑。程序不会把账号密码写入磁盘，也不会上传导出数据。

如果需要重新登录，在界面中点击“清除本机保存的会话”，确认后重新输入密码即可。也可以设置 `GARMIN_EXPORTER_DATA_DIR` 把配置、日志和会话放到指定目录。

## 6. 常见问题

**提示请求过于频繁（HTTP 429）**

等待几分钟后重试，并缩小日期范围或减少一次选择的健康数据项目。

**提示 Cloudflare、403 或访问被拦截**

稍后再试，必要时切换网络，例如使用手机热点。不要连续快速点击登录。

**提示验证码错误**

验证码有有效期，请输入最新验证码。超过重试次数后重新点击登录。

**某天没有健康数据**

程序仍会生成对应 JSON 文件，文件中的 `data` 可能为空。某些指标还需要设备支持并且 Garmin Connect 中确实有记录。

**Windows 双击没有反应**

源码版可以在项目目录打开命令提示符执行 `启动.bat`，查看错误信息。已打包 exe 可以在终端直接运行查看提示。未签名程序可能被 Windows SmartScreen 拦截，可在“更多信息”中确认来源后运行。

## 7. Windows 打包说明

可以在 Windows 上打包成一个 `GarminDataExporter.exe`，不要求使用者另外安装 Python。打包必须在 Windows 目标电脑上进行，不能在 macOS 上直接交叉生成 Windows exe。

在项目根目录运行：

```bat
scripts\build_windows.bat
```

产物位于 `dist\GarminDataExporter.exe`。打包脚本会安装依赖并清理旧的 `build`、`dist` 目录，请先备份其中需要保留的文件。单文件程序第一次启动会先解压运行组件，可能比源码版稍慢；未签名程序也可能触发 SmartScreen 提示。

程序的配置和会话不会打包进 exe。建议在没有安装 Python 的干净 Windows 电脑上先测试启动、登录、验证码、导出和会话保存。
