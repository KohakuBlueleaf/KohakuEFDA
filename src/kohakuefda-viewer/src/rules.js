// The recipe filter of plan/recipes.py, so pickers offer only what the planner may use.

export const GAS_MODES = ["gas", "gasliquid", "gastrans", "solidtrans", "liquidtrans"]
export const FLUID_MODES = [...GAS_MODES, "liquid"]

function usesPhase(dataset, recipe, phases) {
  return [...recipe.inputs, ...recipe.outputs].some((stack) =>
    phases.includes(dataset.items[stack.item_id]?.phase ?? 1),
  )
}

export function recipeAllowed(dataset, scenario, recipe) {
  const machine = dataset.machines[recipe.machine_id]
  if ((scenario.banned_machines ?? []).includes(recipe.machine_id)) {
    return false
  }
  if (scenario.basement.region === "valley4") {
    if (machine?.place_domains?.length && !machine.place_domains.includes("domain_1")) {
      return false
    }
    if (FLUID_MODES.includes(recipe.mode) || usesPhase(dataset, recipe, [2, 4])) {
      return false
    }
  }
  if (
    !scenario.gas &&
    (GAS_MODES.includes(recipe.mode) || recipe.env || usesPhase(dataset, recipe, [4]))
  ) {
    return false
  }
  if (
    scenario.liquids === false &&
    (FLUID_MODES.includes(recipe.mode) || usesPhase(dataset, recipe, [2, 4]))
  ) {
    return false
  }
  return true
}

export function makeableItems(dataset, scenario) {
  const out = new Set()
  for (const recipe of Object.values(dataset?.recipes ?? {})) {
    if (recipeAllowed(dataset, scenario, recipe)) {
      for (const stack of recipe.outputs) {
        out.add(stack.item_id)
      }
    }
  }
  return [...out]
}

export function productionMachines(dataset) {
  return Object.values(dataset?.machines ?? {})
    .filter((machine) => machine.modes?.length)
    .map((machine) => machine.id)
}
