# 审查结果

最终实现：Material Design 手机优先的单文稿控制台，删除预览，右上角打开设置弹窗；支持本地 TXT/DOCX 导入；提词工具栏提供字号调整，阅读区域保留点击暂停/继续。

## 独立审查与修复

独立只读审查覆盖页面结构与样式、app.js 状态/交互、本地文档导入及本次变更的差异。

- **Critical：无。**
- **Warning：已修复 2 项，最终复核无剩余 Warning。**
  1. Word 正文的 `w:noBreakHyphen` 原先被遗漏，现提取为 U+2011，避免复合词丢失连字符。
  2. 数字输入框失焦后立即移除键盘布局，可能令设置弹窗在 pointerdown 与 click 之间移位，吞掉“完成/关闭”操作。现保留键盘布局直到 visualViewport 恢复，并按实际 offsetTop、高度定位弹窗。
- **Info：** 手机使用底部设置弹窗，桌面居中；所有导入在本地处理；原有文稿/设置存储键保持兼容。软键盘检查使用 visualViewport 模拟，未进行实体手机键盘或安全区硬件验收。

最新修复的独立复核 **18/18 通过**，覆盖 Chromium/WebKit、竖屏/横屏、鼠标/触摸、可视区恢复、进出提词、切换桌面宽度和非断行连字符提取。复核未修改文件，JavaScript 语法和差异检查通过。

验证代理另补充键盘仍展开时的“完成/关闭/恢复默认”交互回归：使用真实指针或触摸事件，鼠标按下后跨动画帧再在原坐标松开，避免自动重试掩盖按钮移动。完整套件的最终结果记录在 [validation/results.md](validation/results.md)。

完整回归还发现旧测试夹具在 viewport 元数据解析前读取 innerWidth/innerHeight，得到 980×2121，而实际手机布局为 390×844。已将模拟初始值改为测试配置的尺寸，保留全部键盘恢复断言；针对性恢复检查通过后重跑完整套件。这是测试环境修正，未为消除测试失败修改产品行为。

## 外部双路审查调用限制

按 CCG 要求实际并行调用两路 `codeagent-wrapper.exe --progress --backend claude`：

- 第一轮 UI 与行为审查均退出码 1，没有有效报告，记录在 `review/ui.log`、`review/behavior.log`。
- 依服务先前提示，以仅进程生效的 `ANTHROPIC_MODEL=claude-opus-4.8` 重试两路，均超时退出（124），没有有效报告，记录在 `review/ui-retry.log`、`review/behavior-retry.log`。
- 未修改全局模型设置，未将失败调用计为通过。双路外部审查未完成；上述独立审查与浏览器验证提供本次交付的实际复核依据。

这是外部模型服务失败，不是用户权限或自动审批拒绝。初始与追加需求的双路分析调用情况见 [analysis/summary.md](analysis/summary.md)。
