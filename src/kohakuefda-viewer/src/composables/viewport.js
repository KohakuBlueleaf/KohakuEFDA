import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue"

const MIN_SCALE = 0.2
const MAX_SCALE = 8
const WHEEL_SENSITIVITY = 0.0016
const STEP_FACTOR = 1.25

function sizeOf(contentSize) {
  const value = contentSize.value
  const [width, height] = Array.isArray(value) ? value : [value?.width, value?.height]
  return { width: width || 0, height: height || 0 }
}

function clampScale(value) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))
}

// Pan and zoom over a fixed-size content box inside a resizable container:
// wheel and pinch zoom around the pointer, drag pans, fit centres and scales to cover it.
export function useViewport(containerRef, contentSize) {
  const scale = ref(1)
  const offsetX = ref(0)
  const offsetY = ref(0)
  const containerWidth = ref(0)
  const containerHeight = ref(0)
  // Until the reader takes the wheel or drags, a resize or a content change keeps refitting.
  const locked = ref(false)

  let observer = null
  let dragging = false
  let dragPointerId = null
  let lastX = 0
  let lastY = 0
  let pinch = null

  function fit() {
    const { width, height } = sizeOf(contentSize)
    const cw = containerWidth.value
    const ch = containerHeight.value
    if (!width || !height || !cw || !ch) {
      return
    }
    const next = clampScale(Math.min(cw / width, ch / height))
    scale.value = next
    offsetX.value = (cw - width * next) / 2
    offsetY.value = (ch - height * next) / 2
    locked.value = false
  }

  function zoomAt(factor, px, py) {
    const next = clampScale(scale.value * factor)
    if (next === scale.value) {
      return
    }
    const ratio = next / scale.value
    offsetX.value = px - (px - offsetX.value) * ratio
    offsetY.value = py - (py - offsetY.value) * ratio
    scale.value = next
    locked.value = true
  }

  function zoomIn() {
    zoomAt(STEP_FACTOR, containerWidth.value / 2, containerHeight.value / 2)
  }

  function zoomOut() {
    zoomAt(1 / STEP_FACTOR, containerWidth.value / 2, containerHeight.value / 2)
  }

  function localPoint(clientX, clientY) {
    const rect = containerRef.value.getBoundingClientRect()
    return { x: clientX - rect.left, y: clientY - rect.top }
  }

  function onWheel(event) {
    event.preventDefault()
    const { x, y } = localPoint(event.clientX, event.clientY)
    zoomAt(Math.exp(-event.deltaY * WHEEL_SENSITIVITY), x, y)
  }

  function onDragMove(event) {
    if (!dragging || event.pointerId !== dragPointerId) {
      return
    }
    offsetX.value += event.clientX - lastX
    offsetY.value += event.clientY - lastY
    lastX = event.clientX
    lastY = event.clientY
  }

  function stopDrag() {
    dragging = false
    dragPointerId = null
    window.removeEventListener("pointermove", onDragMove)
    window.removeEventListener("pointerup", stopDrag)
  }

  function onPointerDown(event) {
    if (event.button !== 0 && event.button !== 1) {
      return
    }
    event.preventDefault()
    dragging = true
    dragPointerId = event.pointerId
    lastX = event.clientX
    lastY = event.clientY
    locked.value = true
    window.addEventListener("pointermove", onDragMove)
    window.addEventListener("pointerup", stopDrag)
  }

  function touchDistance(touches) {
    return Math.hypot(
      touches[0].clientX - touches[1].clientX,
      touches[0].clientY - touches[1].clientY,
    )
  }

  function touchMidpoint(touches) {
    const { x: ax, y: ay } = localPoint(touches[0].clientX, touches[0].clientY)
    const { x: bx, y: by } = localPoint(touches[1].clientX, touches[1].clientY)
    return { x: (ax + bx) / 2, y: (ay + by) / 2 }
  }

  function onTouchStart(event) {
    if (event.touches.length === 2) {
      dragging = false
      pinch = { distance: touchDistance(event.touches), scale: scale.value }
      return
    }
    dragging = true
    pinch = null
    lastX = event.touches[0].clientX
    lastY = event.touches[0].clientY
    locked.value = true
  }

  function onTouchMove(event) {
    if (event.touches.length === 2 && pinch) {
      event.preventDefault()
      const mid = touchMidpoint(event.touches)
      const factor = (touchDistance(event.touches) / pinch.distance) * (pinch.scale / scale.value)
      zoomAt(factor, mid.x, mid.y)
      return
    }
    if (dragging && event.touches.length === 1) {
      event.preventDefault()
      const touch = event.touches[0]
      offsetX.value += touch.clientX - lastX
      offsetY.value += touch.clientY - lastY
      lastX = touch.clientX
      lastY = touch.clientY
    }
  }

  function onTouchEnd(event) {
    pinch = null
    dragging = event.touches.length === 1
    if (dragging) {
      lastX = event.touches[0].clientX
      lastY = event.touches[0].clientY
    }
  }

  const style = computed(() => ({
    transform: `translate(${offsetX.value}px, ${offsetY.value}px)`,
    transformOrigin: "0 0",
  }))

  watch(
    () => sizeOf(contentSize),
    () => {
      if (!locked.value) {
        fit()
      }
    },
  )

  onMounted(() => {
    if (!containerRef.value || typeof ResizeObserver === "undefined") {
      return
    }
    observer = new ResizeObserver((entries) => {
      const [entry] = entries
      containerWidth.value = entry.contentRect.width
      containerHeight.value = entry.contentRect.height
      if (!locked.value) {
        fit()
      }
    })
    observer.observe(containerRef.value)
  })

  onUnmounted(() => {
    observer?.disconnect()
    stopDrag()
  })

  return reactive({
    scale,
    offsetX,
    offsetY,
    style,
    onWheel,
    onPointerDown,
    onTouchStart,
    onTouchMove,
    onTouchEnd,
    fit,
    zoomIn,
    zoomOut,
    reset: fit,
  })
}
