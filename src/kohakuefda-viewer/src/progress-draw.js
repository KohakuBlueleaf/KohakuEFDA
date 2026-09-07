import { drawLayout, drawRect } from "@/draw"
import { frameSpace } from "@/progress"

export function drawProgressLayout(ctx, frame, dataset, size, palette, options = {}) {
  drawLayout(ctx, frame.layout, dataset, size, palette, options)
  const space = frameSpace(frame, null)
  if (space.area.some((value, index) => value !== space.target[index])) {
    drawRect(ctx, space.area, size, palette.selection)
  }
  drawRect(ctx, space.target, size, palette.areaEdge)
}
