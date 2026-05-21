# fix: 视频浮窗无法拖动和调整大小

## Goal

修复 VideoPlayerFloat 组件的拖拽和缩放功能完全失效的 bug，使其能够正常拖动和调整窗口大小。

## What I already know

* `VideoPlayerFloat.tsx` 中的拖拽逻辑使用 `useEffect` + `dragRef`（ref）模式
* `useEffect` 依赖 `[pos.x, pos.y]`，守卫条件为 `if (!dragRef.current) return`
* 组件挂载时 effect 运行 → dragRef 为 null → 直接 return，**不注册 listener**
* `onDragStart` 设置 `dragRef.current`，但 ref 变更不触发重渲染 → effect 不重新执行 → listener 永远不会被注册
* 缩放逻辑（resize）存在完全相同的 bug
* 根本原因：依赖 ref 来控制 listener 注册时机，但 ref 变更不触发 effect 重执行

## Assumptions (temporary)

* 修复仅涉及 `VideoPlayerFloat.tsx` 一个文件
* 不需要引入额外依赖库

## Open Questions

* (none — bug 根因已明确，修复方案清晰)

## Requirements

* 标题栏拖拽功能正常工作
* 右下角 resize handle 缩放功能正常工作
* 拖拽和缩放过程中位置/尺寸实时更新

## Acceptance Criteria (evolving)

* [ ] 鼠标按住标题栏拖拽，浮窗跟随移动
* [ ] 鼠标按住右下角 resize handle，浮窗跟随缩放
* [ ] 拖拽/缩放结束后状态正确保留
* [ ] 最小化/关闭按钮点击不触发拖拽

## Definition of Done

* 修复通过手动验证
* TypeScript 类型检查通过
* Lint 无新增错误

## Out of Scope

* 触摸/移动端拖拽支持
* 拖拽边界约束（浮窗不允许超出视口）
* 动画或视觉增强

## Technical Notes

* 文件: `frontend/src/components/VideoPlayerFloat.tsx`
* Bug 位于第 151-174 行（drag effect）和第 198-221 行（resize effect）
* 修复方案：引入 `isDragging` / `isResizing` state，在 mousedown 时设为 true，作为 effect 依赖驱动 listener 注册
