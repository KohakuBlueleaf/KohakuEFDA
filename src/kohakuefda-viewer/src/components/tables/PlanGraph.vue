<script setup>
import { labelAnchor, layerGraph, pathWithJumps, routeEdges } from "@/graph"
import { useI18n } from "@/i18n"
import { formatRate, useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const props = defineProps({
  plan: { type: Object, required: true },
})
const { t } = useI18n()
const names = useNames()
const store = useAppStore()

const NODE_W = 210
const NODE_H = 46
const ICON = 28
const METRICS = {
  nodeW: NODE_W,
  nodeH: NODE_H,
  rowH: 66,
  gapMin: 150,
  track: 12,
  stub: 12,
  margin: 24,
}
const JUMP = 4
const LABEL_RUN = 90
const ENDPOINTS = ["supply", "target", "depot", "dump", "sink"]

function nodeId(name, item) {
  return ENDPOINTS.includes(name) ? `${name}:${item}` : name
}

function endpointLabel(kind, item) {
  if (kind === "supply") {
    const phase = store.dataset?.items?.[item]?.phase ?? 1
    return t(phase === 1 ? "endpoint.fromDepot" : "endpoint.fromOutside")
  }
  return t(`endpoint.${kind}`)
}

function nodeInfo(id) {
  const [kind, item] = id.split(":")
  if (item !== undefined && ENDPOINTS.includes(kind)) {
    return {
      title: names.item(item),
      detail: endpointLabel(kind, item),
      icon: store.iconUrl("items", item),
      endpoint: true,
    }
  }
  const use = props.plan.recipes.find((r) => r.recipe_id === id)
  const recipe = store.dataset?.recipes?.[id]
  const products = recipe
    ? recipe.outputs.map((stack) => names.item(stack.item_id)).join(" + ")
    : names.recipe(id)
  return {
    title: products,
    detail: use ? `${use.machines} × ${names.machine(use.machine_id)}` : "",
    icon: use ? store.iconUrl("machines", use.machine_id) : "",
    endpoint: false,
  }
}

const graph = computed(() => {
  const nodes = []
  const edges = []
  const loops = []
  for (const net of props.plan.nets) {
    const source = nodeId(net.source, net.item_id)
    const target = nodeId(net.target, net.item_id)
    nodes.push(source, target)
    if (source === target) {
      loops.push({ id: source, net })
    } else {
      edges.push({ source, target, net })
    }
  }
  const layout = layerGraph(nodes, edges)
  const routed = routeEdges(layout, edges, METRICS)
  const drawn = edges.map((edge, index) => {
    const points = routed.routes.get(index)
    const crossings = routed.crossings.filter((c) => c.edge === index)
    return {
      index,
      net: edge.net,
      back: layout.back.has(index),
      path: pathWithJumps(points, crossings, JUMP),
      label: labelAnchor(points, LABEL_RUN),
    }
  })
  return {
    nodes: routed.nodeAt,
    edges: drawn,
    loops,
    crossings: routed.crossings.length,
    width: routed.width,
    height: routed.height + (loops.length ? 30 : 0),
  }
})

function labelLines(net) {
  const kind = net.fluid ? t("graph.pipe") : t("graph.belt")
  return [`${names.item(net.item_id)} ${formatRate(net.rate)}/min`, `${net.lanes} ${kind}`]
}

function labelProps(edge) {
  if (edge.label.along === "v") {
    return { x: edge.label.x + 5, y: edge.label.y, anchor: "start", dy: [-3, 9] }
  }
  return { x: edge.label.x, y: edge.label.y, anchor: "middle", dy: [-14, -4] }
}
</script>

<template>
  <div class="card">
    <div class="px-3 py-1 text-[10px] text-secondary flex gap-3 flex-wrap">
      <span>{{
        graph.crossings ? t("graph.crossings", { n: graph.crossings }) : t("graph.noCrossings")
      }}</span>
      <span>{{ t("graph.feedback") }}</span>
    </div>
    <div class="overflow-auto">
      <svg :width="graph.width" :height="graph.height" class="graph">
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="8"
            markerHeight="8"
            orient="auto"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" class="arrow" />
          </marker>
        </defs>
        <g v-for="edge in graph.edges" :key="edge.index">
          <path :d="edge.path" class="edge" :class="{ back: edge.back }" marker-end="url(#arrow)" />
          <text
            :x="labelProps(edge).x"
            :y="labelProps(edge).y"
            class="edge-label"
            :text-anchor="labelProps(edge).anchor"
          >
            <tspan
              v-for="(line, n) in labelLines(edge.net)"
              :key="n"
              :x="labelProps(edge).x"
              :dy="
                n === 0 ? labelProps(edge).dy[0] : labelProps(edge).dy[1] - labelProps(edge).dy[0]
              "
            >
              {{ line }}
            </tspan>
          </text>
        </g>
        <g
          v-for="[id, point] in graph.nodes"
          :key="id"
          :transform="`translate(${point.x}, ${point.y})`"
        >
          <rect
            :width="NODE_W"
            :height="NODE_H"
            rx="8"
            :class="nodeInfo(id).endpoint ? 'node endpoint' : 'node'"
          />
          <image
            v-if="nodeInfo(id).icon"
            :href="nodeInfo(id).icon"
            x="8"
            :y="(NODE_H - ICON) / 2"
            :width="ICON"
            :height="ICON"
          />
          <text :x="nodeInfo(id).icon ? 44 : 10" y="19" class="node-title">
            {{ nodeInfo(id).title }}
          </text>
          <text :x="nodeInfo(id).icon ? 44 : 10" y="35" class="node-detail">
            {{ nodeInfo(id).detail }}
          </text>
          <template v-for="loop in graph.loops.filter((l) => l.id === id)" :key="loop.net.item_id">
            <path
              :d="`M ${NODE_W - 30} 0 C ${NODE_W - 30} -22, ${NODE_W - 4} -22, ${NODE_W - 4} 0`"
              class="edge"
              marker-end="url(#arrow)"
            />
            <text :x="NODE_W - 17" y="-24" class="edge-label" text-anchor="middle">
              {{ labelLines(loop.net).join(" · ") }}
            </text>
          </template>
        </g>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.node {
  fill: var(--color-surface-alt);
  stroke: var(--color-border);
}
.node.endpoint {
  fill: var(--color-surface);
  stroke-dasharray: 4 3;
}
.node-title {
  fill: var(--color-text);
  font-size: 12px;
  font-weight: 500;
}
.node-detail {
  fill: var(--color-text-muted);
  font-size: 10px;
}
.edge {
  fill: none;
  stroke: var(--color-text-faint);
  stroke-width: 1.4;
}
.edge.back {
  stroke: #a57eae;
  stroke-dasharray: 5 3;
}
.arrow {
  fill: var(--color-text-faint);
}
.edge-label {
  fill: #d4920a;
  font-size: 10px;
  paint-order: stroke;
  stroke: var(--color-surface);
  stroke-width: 3px;
  stroke-linejoin: round;
}
</style>
