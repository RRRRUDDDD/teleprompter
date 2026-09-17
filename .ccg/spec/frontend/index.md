# 前端约定

## 静态部署与语言

- 当前产品保持直接静态部署：index.html 引用 styles.css、document-import.js 与 app.js，不需要构建流程或后端。
- 界面当前优先简体中文，HTML lang 为 zh-CN。核心图标使用本地 SVG，字体提供系统字体回退。
- 相对资源路径须兼容根路径与 GitHub Pages 子目录；manifest 的图标位于项目根目录。

## 移动端与阅读状态

- 手机是主要使用场景。界面采用 Material Design 风格的单文稿控制台，右上角打开原生设置弹窗；手机为底部弹窗，桌面居中。预览页、三面板导航与桌面设置侧栏已按用户要求移除。
- 保留固定底部开始操作，实际检测到软键盘打开时让出编辑空间。通过 visualViewport 更新可用高度，旋转或关闭键盘后恢复。
- 检查 320px 窄屏、390px 竖屏与 844×390 横屏；底部操作考虑 safe-area-inset-bottom，输入框避免 iOS 自动缩放。
- Fullscreen 和 Wake Lock 都是可选能力，拒绝或缺失时仍须正常提词。退出、重复启动、切换后台时清理计时和动画状态。
- 文稿通过 textContent 渲染。保留 savedText 存储键，区分“没有保存记录”和“已保存空文稿”，存储异常不能中断编辑。

## 已验证的兼容性经验

- 某些 WebKit 构建会将 type="color" 的 input.type 返回为 "text"。绑定颜色输入事件应参考原始 type 属性，并提供可编辑的十六进制文本回退。
- 原生 dialog 在不同浏览器中关闭后不一定回到触发按钮；在 close 事件中显式恢复焦点。
- 软键盘缩短或平移 visualViewport 时，设置弹窗的位置与最大高度须落在实际可视区内。输入框失焦后保留键盘布局直到可视区恢复，避免 pointerdown 与 click 之间移动按钮而吞掉关闭/完成操作；回归测试应在键盘仍展开时实际点击或轻触按钮。
- Playwright 的 add_init_script 早于 viewport 元数据解析；模拟 visualViewport 时使用测试配置的 CSS 宽高，不要在初始化脚本中捕获尚未适配手机的 innerWidth/innerHeight，否则会把页面缩放前的尺寸误当作键盘关闭状态。
- 镜像作用于文稿容器，操作按钮不翻转。触控与鼠标拖动使用 Pointer Events，拖动结束不能同时触发暂停。
- 提词工具栏提供“调整大小”，滑杆与加减按钮同步设置及存储；暂停/继续由阅读区域的点击、键盘或手柄完成。字号或视口变化后重测文稿高度，保留阅读行程比例、播放状态和计时。
- 全局提词快捷键不拦截 range、number、select、button 等控件自己的按键。原生 dialog 的 Tab 可能经过浏览器界面，测试应检查页面背景不可聚焦，而不是强制每一步 activeElement 都位于弹窗内。

## 本地文档导入

- window.FlowDocumentImport.read(file) 返回纯文本 Promise；导入模块负责格式与尺寸检查，app.js 负责忙碌状态、错误反馈、文稿版本保护与撤销。
- TXT 与 DOCX 均在浏览器本地读取，不上传。fflate 固定版本存放 vendor 并保留来源/许可证，首次 DOCX 导入才按需加载。模块初始化时捕获脚本 URL，异步加载时不再依赖 document.currentScript，以兼容 file:// 和 Pages 子路径。
- DOCX 只提取 Word 主文档 XML，验证实际解压字节数和 CRC，不仅依赖 ZIP 声明尺寸；同时限制文件、正文 XML、最终文字长度。
- Word 的 AlternateContent 可能同时包含同一文本框的 Choice/Fallback，提取时只选择一个分支，避免重复文字。支持常用与 strict 命名空间；段落、手动换行、tab 和 noBreakHyphen 不间断连字符保留。
- 导入期间用户可以继续编辑，但异步结果不能覆盖期间的新修改或后发导入。失败和空文档不得替换原稿。
