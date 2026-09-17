# 实施计划

2026-09-17 继续同一任务。基线 0afcb2b，当前工作区已完整提交。此前双路外部分析失败记录及两份独立研究保留，按现有研究落实。

## 文件分工

- 主代理：index.html、styles.css、app.js、前端 spec、任务记录、集成和最终发布。
- 存储代理：script-library.js、tests/verify_script_library.py。实现 IndexedDB 按文稿持久化、旧 savedText 单次迁移、故障保留内存内容与真实保存状态。
- PWA 代理：pwa.js、worker.js、manifest.json、tests/verify_pwa.py。作用域内预缓存、离线文本/Word 导入、安装入口、等待式版本更新。
- UI 测试代理：tests/verify_ui.py、tests/capture_ui.py、README.md。移除示例/面板旧断言，覆盖文稿库和直接字号控件。

## 实现契约

### 页面

- 引入脚本顺序 document-import.js、script-library.js、app.js、pwa.js，全部 defer。
- 保留 inputText；新增文稿标题 draftTitle、文稿库入口 openLibraryBtn、原生弹窗 libraryDialog、关闭 closeLibraryBtn、新建 newDraftBtn、搜索 librarySearch、列表 draftList、空列表提示 libraryEmpty。
- 文稿条目为 .draft-item[data-draft-id]；切换按钮 .draft-open，删除按钮 .draft-delete。标题均以 textContent 渲染。
- 新设备空稿；已有 savedText 单次迁移为文稿。不删现有示例文字，因为它已经属于用户保存内容。
- importBtn / openSettingsBtn 只显示 SVG，保留名称、44px 点击区和 aria-busy。
- 移除 sampleBtn、startHint、fontSizeBtn、fontSizePanel、playerFontSizeRange 及对应事件。保留 smallerFontBtn、playerFontSizeValue、largerFontBtn；数字独立，单位 px。
- 设置弹窗新增 installAppBtn、installHint、offlineStatus（role=status）、updateStatus。
- 页面对外用 body[data-library-ready="true"] 表示初始化完成；异步恢复前禁用编辑/导入/播放，失败则启用内存模式并显示未保存状态。

### 文稿模块

- window.FlowScriptLibrary.open({legacyText, onStatus}) 异步返回库，初始化异常返回保留正文的内存模式，不能挂死。
- 库提供 active getter（克隆文稿对象或 null）、list()（克隆数组）、update({title,text})、create({title,text})、select(id)、remove(id)、restore(record)、flush()。
- update 同步更新内存、异步持久化。操作不得因存储故障丢弃内存内容。文稿含 id/title/text/createdAt/updatedAt，id 稳定。
- create/select/remove/restore 返回 Promise，remove 返回完整已删文稿快照；删除最后一篇时创建空稿，restore 仅恢复记录而不切换，以保护删除后的新编辑。
- onStatus({state}) 的 state 为 saving/saved/unavailable；只有全部当前改动写入成功才显示 saved。存储失败时后续设置写入成功不能掩盖文稿未保存状态。
- 保留独立 savedText 兼容镜像，权威来源为 IndexedDB；写入 mirror 要有 active ID 与修订守卫。

## 验证与发布

1. 各代理仅修改所分配文件，不撤销其他代理工作，不再 spawn。
2. 主代理做集成、基础语法检查、现有 Chromium/WebKit UI 回归、存储故障/迁移和离线测试、移动截图与可访问性检查。
3. 并行调用两个外部审查。如外部不可用则明确记录，并使用独立子代理审查，不伪造通过。
4. 修复真实问题，更新 spec；归档并提交任务，全库提交推送 main；确认 Pages 成功与线上版本。
