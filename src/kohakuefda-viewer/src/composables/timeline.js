import { onMounted, onUnmounted, ref, watch } from "vue"

const TICK_MS = 33

export function useTimeline(frames) {
  const index = ref(0)
  const playing = ref(false)
  const speed = ref(4)
  const live = ref(true)
  let animation = 0
  let lastTick = 0
  const count = () => frames.value.length

  function tick(now) {
    if (playing.value && now - lastTick > TICK_MS) {
      lastTick = now
      if (index.value >= count() - 1) playing.value = false
      else index.value = Math.min(index.value + speed.value, count() - 1)
    }
    animation = requestAnimationFrame(tick)
  }

  watch(
    () => frames.value.length,
    (n) => {
      if (live.value) index.value = Math.max(0, n - 1)
      else if (index.value >= n) index.value = Math.max(0, n - 1)
    },
    { immediate: true },
  )
  watch(live, (on) => {
    if (on) {
      playing.value = false
      index.value = Math.max(0, count() - 1)
    }
  })
  watch(
    () => frames.value[0],
    (first, before) => {
      if (first !== before) {
        playing.value = false
        index.value = live.value ? Math.max(0, count() - 1) : 0
      }
    },
  )
  watch(playing, (on) => {
    if (on) {
      live.value = false
      if (index.value >= count() - 1) index.value = 0
    }
  })
  onMounted(() => {
    animation = requestAnimationFrame(tick)
  })
  onUnmounted(() => cancelAnimationFrame(animation))
  return { index, playing, speed, live }
}
