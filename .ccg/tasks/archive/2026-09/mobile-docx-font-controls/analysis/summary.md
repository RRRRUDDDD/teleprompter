# 分析结论与需求调整

初始任务按 M 评估，并行调用了两个 claude analyzer。移动端分析返回有效报告（mobile.md）；导入/行为分析退出码 1，无有效报告。随后用户追加要求：Material Design 单文稿控制台、删除预览、全部设置移到右上角弹窗。任务因此升级 L，更新 requirements/plan 并按文件归属并行实施。

追加需求的两路分析及简化请求重试均实际并行执行，但模型服务返回 “hit a safety filter and returned no content”。这些输出保留作为失败记录，不计作有效分析。主代理结合已读源码与有效移动端分析制定文件/DOM/API 合同，各实施代理在自己的范围内分析后实现。

最终采用：

- Material 风格单文稿页面，原生设置 dialog，移动端底部弹窗，桌面居中。用户的新要求优先于旧的三面板/双栏/预览规范。
- 文稿编辑、播放状态、本地文件导入分离；保持静态部署，移除全部 preview/tab/pause-button 依赖。
- DOCX 使用本地固定 fflate 0.8.3，首次导入按需加载，读取有界 Word 主文档 XML。相对 Mammoth 的完整浏览器包更小，并明确处理段落、手动换行、tab、表格和文本框。
- 字号变化沿用提词阅读行程比例，更新文稿高度和结束条件；输入控件保留各自键盘行为。
- 依据浏览器实际可视区域调整软键盘下的弹窗位置和大小；此项以模拟 visualViewport 覆盖，未宣称实体手机验收。

实现与验证代理分别负责 app.js、document-import.js/vendor、tests；主代理负责 HTML/CSS、集成、文档、规范与归档。无文件写入冲突，未修改原有 publish-github-pages 任务。
