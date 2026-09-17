# 前端约定

## 静态部署与语言

- 当前产品保持直接静态部署：index.html 引用 styles.css，脚本依次为 document-import.js、script-library.js、app.js、pwa.js，不需要构建流程或后端。
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
- 提词工具栏直接提供字号与速度加减；字号每次 2px，范围 10–100px。窄屏分两行，重播与退出可跨行居中，所有按钮至少 44×44px。暂停/继续由阅读区域的点击、键盘或手柄完成。字号或视口变化后重测文稿高度，保留阅读行程比例、播放状态和计时。
- 全局提词快捷键不拦截 range、number、select、button 等控件自己的按键。原生 dialog 的 Tab 可能经过浏览器界面，测试应检查页面背景不可聚焦，而不是强制每一步 activeElement 都位于弹窗内。

## 本地文档导入

- window.FlowDocumentImport.read(file) 返回纯文本 Promise；导入模块负责格式与尺寸检查，app.js 负责忙碌状态、错误反馈、文稿版本保护与撤销。
- TXT 与 DOCX 均在浏览器本地读取，不上传。fflate 固定版本存放 vendor 并保留来源/许可证，首次 DOCX 导入才按需加载。模块初始化时捕获脚本 URL，异步加载时不再依赖 document.currentScript，以兼容 file:// 和 Pages 子路径。
- DOCX 只提取 Word 主文档 XML，验证实际解压字节数和 CRC，不仅依赖 ZIP 声明尺寸；同时限制文件、正文 XML、最终文字长度。
- Word 的 AlternateContent 可能同时包含同一文本框的 Choice/Fallback，提取时只选择一个分支，避免重复文字。支持常用与 strict 命名空间；段落、手动换行、tab 和 noBreakHyphen 不间断连字符保留。
- 导入期间用户可以继续编辑，但异步结果不能覆盖期间的新修改或后发导入。失败和空文档不得替换原稿。

## 文稿库与 IndexedDB

- script-library.js 负责权威存储，app.js 负责 UI。初始化完成以 body[data-library-ready="true"] 标示；新设备默认空稿，旧 savedText 只在首次迁移时导入。
- update 同步改变内存状态，写入按顺序执行；切换/新建/删除前 flush。savedText 仅是当前正文的兼容镜像，写成功且 ID/修订仍一致时才更新。
- 更新或删除前，在同一写事务中核对最后成功保存的记录；遇到其他窗口修改或删除则保留本窗口未保存内容并提示冲突，不能静默覆盖或复活文稿。
- IDB 不可用、结构无法识别或读写失败时保留内存文稿，显示真实未保存状态，不清空旧资料。设置保存成功不能清除文稿保存失败提示。
- 文稿导入与撤销检查稳定文稿 ID 和修订，切换后过期结果不能覆盖新稿。删除撤销仅恢复记录，不覆盖后来输入的当前文稿。
- native dialog 的 close 事件可能延后，需协调新建后的标题焦点和切换后的正文焦点，不能无条件抢回入口按钮。键盘缩短视口时文稿列表 min-height 为 0，固定区域仍需容纳新建、关闭及撤销操作。

## 离线与安装

- worker.js 的 RELEASE 随每次应用资源发布升级；预缓存包含本地 DOCX 解压库及所有脚本，按 registration.scope 构造路径和缓存命名前缀。
- 更新自然等待旧窗口全部关闭，禁止 skipWaiting 或编辑/播放中强制刷新；仅清理本应用当前 scope 的旧缓存。
- 离线状态由 worker 实查缓存，不能仅依据已注册就显示准备完成。更新提示要同时更新文本与 hidden 状态。
- manifest 的 sizes 必须与实际 PNG 宽高一致。file:// 下不添加 manifest href、不注册 worker；本地文件保留基本提词能力。
- 普通 UI 回归屏蔽 service worker，避免缓存绕开路由拦截；PWA 专项用真实 worker 检查根目录与子路径部署、离线首次 DOCX 导入和等待更新。
