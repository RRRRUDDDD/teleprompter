# Flow · 简易提词器

以手机为主的 Material Design 风格提词器。首页直接编辑文稿，所有提词设置通过右上角“设置”打开。

## 使用

1. 输入或粘贴文字，也可以点击“导入文件”，选择 UTF-8 的 TXT 或 Word 的 DOCX 文稿。
2. 点击右上角“设置”，调整字体、字号、颜色、滚动速度、倒计时、镜像、计时器和参考线。设置会自动保存。
3. 点击“开始提词”。轻点画面暂停或继续，上下拖动调整位置。
4. 提词中点击“调整大小”，用滑杆或加减按钮修改字号。字号会同步保存，阅读进度和计时保持连续。
5. 点击右下角关闭按钮返回文稿；左侧重播按钮从头开始。

文稿保存在当前设备的浏览器中。清空、示例载入和文件导入支持撤销；导入失败会保留原稿。

## 文件导入

- TXT：UTF-8 编码，文件不超过 1 MiB。
- DOCX：文件不超过 10 MiB，正文解压后不超过 8 MiB，导入文字不超过 100 万个 UTF-16 代码单元。
- DOCX 提取正文中的文字，保留段落、手动换行、制表符及表格内容。图片与文档样式不会导入。
- 旧版 DOC、加密文档、分卷 ZIP 和 ZIP64 目录请先在 Word 中另存为普通 DOCX。
- 文件在浏览器本地解析，不会上传。解压组件随项目提供，仅首次导入 DOCX 时按需加载。

## 快捷操作

| 操作 | 快捷键 |
| --- | --- |
| 暂停 / 继续 | 在提词画面按 Space 或 Enter |
| 调整文字位置 | ↑ / ↓，PageUp / PageDown |
| 调整滚动速度 | ← / → |
| 收起字号面板 / 返回编辑 | Esc |

蓝牙手柄方向键控制位置与速度，A 键暂停 / 继续，B 键返回编辑。iPhone 可在 Safari 中添加到主屏幕；浏览器不支持原生全屏或保持屏幕常亮时，仍可正常使用页面内提词。

## 本地运行与验证

直接打开 `index.html`，或将项目作为静态网站部署。无需构建或安装网页运行依赖，资源路径兼容 GitHub Pages 子目录。

浏览器测试使用 Python 与 Playwright。从项目根目录运行：

```powershell
python -m http.server 4175 --bind 127.0.0.1
```

在另一个终端运行：

```powershell
python tests/verify_ui.py
$env:TELEPROMPTER_TEST_BROWSER = "webkit"
python tests/verify_ui.py
```

首次使用测试工具需安装 Python 的 `playwright` 包及 Chromium、WebKit 浏览器。可用 `TELEPROMPTER_TEST_URL` 指定服务地址；`tests/capture_ui.py` 生成截图，结果位于被 Git 忽略的 `tests/artifacts/`。

原作：仨宝爸中医博士吴启铭。项目沿用原有 MIT 授权；本地解压依赖 fflate 的来源、版本与许可证见 [vendor/README.md](vendor/README.md)。
