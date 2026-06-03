# WorkflowProgram 总览 PPT

这个目录存放用 `slides` 生成的 `WorkflowProgram` 总览演示文稿。

## 产物

- `generate_workflowprogram_flow_slides.js`
  - deck 源码
- `workflowprogram_overview.pptx`
  - 生成后的总览演示文稿
- `pptxgenjs_helpers/`
  - 从 `slides` skill 复制过来的本地 helper

## 内容范围

这份 deck 当前覆盖这些主题：

1. 安装步骤
2. 设计哲学与核心概念
3. 快速使用
4. 文件结构
5. 运行过程
6. 运行证据与进展资产
7. 维护说明

## 重新生成

在本目录执行：

```bash
npm install
npm run generate
```

## 渲染预览

如果本机装有 LibreOffice / `soffice`，可以继续执行：

```bash
python3 /mnt/c/Users/zhd/.codex/skills/slides/scripts/render_slides.py workflowprogram_overview.pptx --output_dir rendered
python3 /mnt/c/Users/zhd/.codex/skills/slides/scripts/create_montage.py --input_dir rendered --output_file montage.png
python3 /mnt/c/Users/zhd/.codex/skills/slides/scripts/slides_test.py workflowprogram_overview.pptx
```

当前这台机器还缺少 `pdf2image` / `soffice` 这类渲染依赖，因此生成 `.pptx` 没问题，但本地 PNG 渲染预览暂时无法执行。
