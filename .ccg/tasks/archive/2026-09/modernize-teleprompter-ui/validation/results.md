# 验证结果

日期：2026-09-16。环境：Windows，Python 3.11，Playwright 1.58.0。

| 检查 | 结果 |
| --- | --- |
| Chromium 浏览器回归 | 17 项全部通过，22.284s |
| Chromium 最终针对性复验 | 4 项全部通过，5.292s |
| WebKit 26.0 浏览器回归 | 17 项全部通过，49.849s |
| axe-core WCAG 2 / 2.1 A、AA | 6 状态，0 规则违规 |
| JavaScript 语法 | node --check app.js 通过 |
| 差异空白检查 | git diff --check 通过 |
| HTML | lang=zh-CN，无重复 ID |
| 静态资源与 manifest | JSON 有效，引用的本地文件存在 |
| 截图采集 | 7 张最终截图，无浏览器错误 |

回归覆盖：文稿保存、HTML 作为纯文本显示、清空与撤销、空稿恢复、UTF-8 导入、编辑快捷键隔离、设置同步与持久化、倒计时与计时、暂停／继续、退出／重复启动、原生全屏退出、实时预览与颜色、镜像、手柄按键边沿、完成／重播、速度边界、触控点击、拖动、横竖屏阅读位置、API 不可用与无效存储数据。

## 复现

从仓库根目录启动静态服务：`python -m http.server 4173 --bind 127.0.0.1`。

安装 Playwright 及其浏览器后，运行归档目录中的 `verify_ui.py`。默认浏览器是 Chromium；设置环境变量 TELEPROMPTER_TEST_BROWSER=webkit 可验证 WebKit。可用 TELEPROMPTER_TEST_URL 指定其他地址。

`capture_ui.py` 生成截图。`check_accessibility.py` 使用独立安装的 axe-core；通过 AXE_CORE_PATH 指向 axe.min.js。验证工具依赖不属于网页运行依赖。

截图：desktop.png、mobile-editor.png、mobile-preview.png、mobile-settings.png、mobile-settings-bottom.png、mobile-player.png、mobile-player-landscape.png。before-desktop.png 为旧版对照。

实体手机、真实系统键盘与完整屏幕阅读器体验未做实机验收。
