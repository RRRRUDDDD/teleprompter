# 实施计划与文件归属

根据用户追加需求，最终产品为 Material Design 手机优先的单文稿控制台，右上角打开全部设置；实时预览、三面板导航、桌面设置侧栏全部移除。

## Layer 1：并行实施

1. 主代理：`index.html`、`styles.css`。
   - 单文稿编辑器、导入与清空操作、保存状态和字数、底部开始按钮。
   - Material 圆角表面、tonal/filled 按钮、系统字体与本地 SVG。
   - 原生 `settingsDialog`，移动端为可滚动底部弹窗、桌面居中；主页面右上角 `openSettingsBtn`。
   - 保留现有设置输入 ID：fontFamily/fontSize/fontSizeRange/fontColor/bgColor/speed/speedRange/countdownSetting/mirror/showTimer/refLineColor/refLineWidth；颜色文本 fontColorValue/bgColorValue。
   - 弹窗关闭按钮 `closeSettingsBtn`、`doneSettingsBtn`，重置按钮 `resetSettingsBtn`。帮助作为弹窗内文字/折叠说明，移除独立旧帮助弹窗。
   - 编辑 ID 保留 controls/appHeader/inputText/wordCount/readTime/saveStatus/saveLabel/clearBtn/sampleBtn/importBtn/importFile/startBtn/startHint，新增 importLabel；toast/toastMessage/toastAction 保留。
   - 提词 ID 保留 display/readerViewport/readerMirror/text/referenceLine/playbackStatus/timer/countdown/countdownNumber/controlButtons/restartBtn/slowerBtn/fasterBtn/playbackSpeed/exitBtn/readingProgress/progressFill。
   - 删除 pauseBtn/pauseLabel/pauseIcon。新增 `fontSizeBtn`、`fontSizePanel`、`playerFontSizeRange`、`playerFontSizeValue`、`smallerFontBtn`、`largerFontBtn`、`closeFontSizeBtn`；`playerTip` 显示状态提示。
   - 提词字号弹层为工具栏上方的非模态 group，调整按钮 aria-controls/aria-expanded；阅读区域键盘可聚焦。
   - 所有触控按钮至少 44px；320px 工具栏完整可见，横屏减少装饰占用。

2. app 实施代理只负责 `app.js`。
   - 移除全部 preview/tab/旧 help dialog 逻辑，接入上述 DOM；保留存储键、字体/颜色边界、纯文本渲染、倒计时、键盘/手柄、触控拖动、FullScreen/Wake Lock 降级。
   - 设置弹窗使用 showModal，支持原生 Escape、关闭/完成、遮罩关闭及焦点返回；设置即时保存。
   - 调用 `window.FlowDocumentImport.read(file): Promise<string>`；忙碌状态、导入前后 revision/token 保护、失败不覆盖原稿、成功可撤销，同文件可再次选择。
   - 字号按钮展开/收起，滑杆和 +/- 实时同步 10–100px、主设置与存储；按字号/宽度变化更新文本高度与阅读位置，不重置状态/计时，完成条件使用新高度。
   - 点击阅读区域暂停/继续，拖动及滑杆操作不误触暂停；Space/Enter 阅读控制，输入控件自己的方向键不被全局截获，Escape 先收起字号面板再退出。
   - 维护 `--app-height`（visualViewport.height 的 px 值）与 `body.keyboard-open`（实际键盘遮挡/缩短明显时），编辑键盘不被固定底部按钮遮挡，退出/旋转恢复尺寸。

3. 导入实施代理只负责 `document-import.js`、`vendor/fflate-0.8.3.min.js`、`vendor/fflate-LICENSE.txt`、`vendor/README.md`。
   - 暴露 `window.FlowDocumentImport.read(file)`，仅提取纯文字；异常 message 使用用户可理解的简体中文。
   - 本地固定版本 fflate，首次 DOCX 导入按需加载，TXT/首屏不依赖 ZIP 下载；资源路径兼容 file:// 和 Pages 子目录。
   - TXT ≤1 MiB，DOCX ≤10 MiB，Word 主文档解压尺寸有上限，仅解压必要 XML；最终文字设合理上限。
   - 支持 Word 常用与 strict 命名空间，段落/手动换行/tab/表格文字/超链接显示文字；不导入脚本或文档样式，不请求文档外链。
   - 损坏 ZIP/XML、空文稿、旧 .doc、超限、库加载失败提供提示，可重试。

4. 验证代理只负责 `tests/verify_ui.py`、可选 `tests/capture_ui.py`、`tests/.gitignore`，生成截图放 `tests/artifacts/`，主代理将选定验证记录复制到任务目录归档。
   - 先写行为测试骨架与内存 DOCX 测试夹具，再按上述 DOM 合同补全测试。
   - 覆盖导入及失败保护、设置弹窗/存储、字号同步/范围/进度、触控手势、倒计时/结束/重播、320/390/844×390/桌面布局、静态子路径、浏览器 API 缺失。
   - 测试用 Python Playwright（环境已安装 1.58）；不引入网页构建流程或修改历史归档测试。

所有实施代理 fork_turns=none，禁止再 spawn，各自仅写归属文件，不回退其他代理的改动。

## Layer 2：主代理集成与验证

- 审核所有交付，修正 DOM/接口衔接，更新 README 和前端 Spec 的过期布局约定。
- node --check 应用脚本；Playwright Chromium 和 WebKit 执行浏览器测试，保存手机/横屏/设置/桌面截图并检查；实体系统键盘未做实机测试时明确记录。
- 双路并行 claude reviewer 审查最终 git diff 与新增模块，合并 Critical/Warning/Info，修复问题并复验。
- 更新 task/review/validation 记录；核查 git diff --check 与变更范围；验证归档绝对路径在工作区内后移动本任务至 archive/YYYY-MM，并只提交本次任务归档，不包含先前 publish-github-pages 任务。
