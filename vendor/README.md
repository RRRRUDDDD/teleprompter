# 本地文档导入依赖

- 组件：fflate **0.8.3**，MIT License，作者 Arjun Barrett。
- 来源：npm 官方注册表中的 `fflate@0.8.3` 包（上游项目 https://github.com/101arrowz/fflate）。
- 获取：在任务专用临时目录运行 `npm pack fflate@0.8.3 --ignore-scripts --json`，校验包完整性后解包。
- `fflate-0.8.3.min.js` 是包内 `umd/index.js` 的原样副本，仅改名；`fflate-LICENSE.txt` 是包内 `LICENSE` 的原样副本。
- 获取日期：2026-09-16。npm 包 integrity：`sha512-tbZNuJrLwGUp3zshBtdy4W+ORxZuIh8a5ilyIEQDC5rY1f3U20JMry0Ll3WBzU58EZKsEuJFXhb5gwv8CsPvgA==`。
- 脚本 SHA-256：`462ef8041fc970e3615a20a9dd2b2e3047a073b2da729ef4f02b634bba8b7b83`。
- 许可证 SHA-256：`0a1df3a083d0c010560aa342e87959c8c1070e6fd54545741f083f22d0c8b551`。

`document-import.js` 仅在读取 DOCX 时按需加载此本地脚本。没有运行时 CDN、远程文档访问、上传、构建工具或 npm 安装步骤。脚本地址相对于导入模块解析，兼容直接打开本地 HTML 与 GitHub Pages 子目录。

导入模块只读取 `word/document.xml`，先验证 ZIP 目录、加密标记和尺寸，再以有界分块解压并验证实际长度与 CRC-32。分卷、ZIP64 目录和加密 ZIP 不受支持，可用 Word 另存为普通未加密 DOCX。TXT 上限为 1 MiB，DOCX 上限为 10 MiB，解压正文 XML 上限为 8 MiB，返回文字上限为 1,000,000 个 UTF-16 代码单元。DOCX 仅提取纯文字，正文 XML 的图片、外链、样式及脚本均不执行或加载。
