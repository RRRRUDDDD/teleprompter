# 验证结果

环境：Windows，Python 3.11，Playwright 1.58.0。日期：2026-09-16。

| 检查 | 结果 |
| --- | --- |
| 最终 Chromium 回归 | 38 项，37 通过，1 项原生全屏能力条件跳过；67.22s |
| 最终 WebKit 回归 | 38 项，37 通过，1 项原生全屏能力条件跳过；135.47s |
| 审查修复的针对性回归 | Chromium、WebKit 均通过；新增键盘按钮检查在每个浏览器覆盖 12 种交互 |
| 最新修复的独立复核 | 18/18 通过，无剩余 Critical / Warning |
| 独立文档导入检查 | 72/72 通过，覆盖 Chromium 与 WebKit |
| axe-core WCAG 2/2.1 A、AA 规则 | 320/390/1440px 共 12 个界面状态，0 条规则违规 |
| JavaScript 语法 | app.js、document-import.js 通过 node --check |
| Python 测试语法 | verify_ui.py、capture_ui.py 编译通过 |
| HTML 与静态资源 | 无重复 ID，本地引用和 manifest 图标均存在 |
| 界面截图 | 13 张，截图过程无 console/page error；主代理已核对手机、窄屏、横屏和桌面 |
| git diff --check | 通过 |

浏览器回归覆盖：文稿保存与空稿、纯文本渲染、清空/导入撤销、TXT/DOCX、strict XML、段落/换行/tab/表格/超链接显示文字/非断行连字符、文件/解压/文本上限、损坏/空文档、组件加载失败重试、导入期间编辑保护、设置弹窗/焦点/背景隔离、设置保存和重置、字号范围/按钮/滑杆/键盘、阅读进度/结束判断、倒计时/暂停/拖动/重播、手柄、Wake Lock 释放、API 缺失、旋转和软键盘。

导入独立检查还包含 CRC 校验、伪造解压尺寸、重复正文 ZIP 成员、忽略无关大成员、UTF-16 XML、文本框与 AlternateContent 去重、file:// 和脚本相对子路径。其报告在 document_import_browser_results.json，脚本在 verify_document_import.py；此组在新增非断行连字符支持前运行，该修复已由最终 38 项套件覆盖。

原生全屏检查按浏览器能力跳过；页面内全屏替代及 API 拒绝路径均已验证。无未捕获浏览器异常。Chromium 唯一预期网络错误来自测试主动阻断解压库请求；WebKit 会提示忽略 interactive-widget viewport 字段。

软键盘测试为 visualViewport 模拟：竖屏可视区 [40, 530]，横屏 [20, 250]，均检查弹窗与关闭/完成按钮在可视区内。键盘仍展开时，使用鼠标和触摸分别激活关闭、完成、恢复默认，之后检查焦点和开始按钮恢复。鼠标按下后跨动画帧，再在原坐标松开，验证失焦不会使按钮移位或吞掉点击。实体 iOS/Android 系统键盘、安全区域硬件和完整屏幕阅读器体验未做实机验收。

首轮完整回归发现旧的键盘恢复夹具在 viewport 元数据解析前捕获了 980×2121 初始尺寸，与配置的 390×844 不一致。已改为显式测试尺寸，保留恢复断言；上表为修正夹具后重新运行的结果。

最终回归前后 app.js、index.html、styles.css、document-import.js、tests/verify_ui.py 的 SHA-256 全部一致，见 source-hashes-start.json 与 source-hashes-end.json。source-hashes.json 另记录相关静态资源与测试的本地快照，便于区分工作区内其他并行任务的后续修改。

## 复现

仓库根目录启动 `python -m http.server 4175 --bind 127.0.0.1`，安装 Python Playwright 及相应浏览器后运行 `python tests/verify_ui.py`。`TELEPROMPTER_TEST_BROWSER=webkit` 切换 WebKit；`TELEPROMPTER_TEST_URL` 可覆盖地址。

`python tests/capture_ui.py` 生成截图。当前截图在本目录 screenshots/，两个最终回归报告与可访问性报告同在本目录。无项目构建流程或服务端依赖。
