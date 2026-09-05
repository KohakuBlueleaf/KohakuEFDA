//! PyO3 bindings for the routing grid.

use pyo3::prelude::*;

use crate::route::core::{Cells, Ends, Grid, Search, AXIS_H, AXIS_NONE, AXIS_T, AXIS_V, LAYERS};

/// A grid's occupancy put by, so a search that is undone costs a copy instead of a rebuild.
/// Rust frees it with the Python object, so a caller may hold as many as it has snapshots.
#[pyclass(name = "_State")]
pub struct PyState {
    layers: [Cells; LAYERS],
    width: usize,
    height: usize,
}

/// The two-layer routing grid; `kohakuefda.route.pathfinder.RouteGrid` is the proxy over it.
#[pyclass(name = "_Grid")]
pub struct PyGrid {
    inner: Grid,
}

#[pymethods]
impl PyGrid {
    #[new]
    fn new(
        width: usize,
        height: usize,
        turn_cost: f32,
        bridge_cost: f32,
        history_cost: f32,
    ) -> Self {
        Self { inner: Grid::new(width, height, turn_cost, bridge_cost, history_cost) }
    }

    /// Whether a cell of a layer is closed to every wire.
    fn block(&mut self, layer: usize, x: i32, y: i32, value: bool) {
        if let Some(index) = self.inner.index(x, y) {
            self.inner.layers[layer].blocked[index] = value;
        }
    }

    /// Whether a machine's own footprint covers a cell of a layer.
    fn own(&mut self, layer: usize, x: i32, y: i32, value: bool) {
        if let Some(index) = self.inner.index(x, y) {
            self.inner.layers[layer].owned[index] = value;
        }
    }

    /// The rectangle the line needs, or ``None`` when nothing stands yet.
    fn extent(&self) -> Option<(i32, i32, i32, i32)> {
        self.inner.extent()
    }

    /// The first free square of ``size`` inside ``window``, or ``None``: where a pylon may go.
    fn free_square(
        &self,
        window: (i32, i32, i32, i32),
        size: i32,
        taken: Vec<(i32, i32)>,
    ) -> Option<(i32, i32)> {
        self.inner.free_square(window, size, &taken)
    }

    /// Whether every cell of a footprint is free for a machine: inside area, and blocked
    /// by nothing but the machine's own cells. One call for a whole candidate position, where
    /// asking cell by cell would cost more in crossings than the test itself.
    fn free_for(
        &self,
        cells: Vec<(i32, i32)>,
        area: (i32, i32, i32, i32),
        mine: Vec<(i32, i32)>,
    ) -> bool {
        let ground = &self.inner.layers[0];
        for (x, y) in cells {
            if x < area.0 || y < area.1 || x >= area.2 || y >= area.3 {
                return false;
            }
            let Some(index) = self.inner.index(x, y) else {
                return false;
            };
            if ground.blocked[index] && !mine.contains(&(x, y)) {
                return false;
            }
        }
        true
    }

    /// Whether a cell of a layer is closed to every lane.
    fn is_blocked(&self, layer: usize, x: i32, y: i32) -> bool {
        match self.inner.index(x, y) {
            Some(index) => self.inner.layers[layer].blocked[index],
            None => true,
        }
    }

    /// The first of cells on layer that no lane is shut out of, or None.
    fn first_open(&self, layer: usize, cells: Vec<(i32, i32)>) -> Option<(i32, i32)> {
        cells
            .into_iter()
            .find(|&(x, y)| match self.inner.index(x, y) {
                Some(index) => !self.inner.layers[layer].blocked[index],
                None => false,
            })
    }

    /// The wires holding a cell of a layer, with their axis.
    fn holders_at(&self, layer: usize, x: i32, y: i32) -> Vec<(i32, u8)> {
        let Some(index) = self.inner.index(x, y) else {
            return Vec::new();
        };
        let side = &self.inner.layers[layer];
        (0..side.count[index].min(2) as usize)
            .map(|slot| (side.holder[index][slot], side.axis[index][slot]))
            .collect()
    }

    /// Whether a logistics unit stands on a cell of a layer.
    fn has_unit(&self, layer: usize, x: i32, y: i32) -> bool {
        match self.inner.index(x, y) {
            Some(index) => self.inner.layers[layer].unit[index],
            None => false,
        }
    }

    /// Whether the ground under a sky cell is clear of buildings and belts.
    fn ground_free(&self, x: i32, y: i32) -> bool {
        match self.inner.index(x, y) {
            Some(index) => {
                let ground = &self.inner.layers[0];
                !ground.blocked[index] && ground.count[index] == 0
            }
            None => false,
        }
    }

    /// Whether a pipe unit stands on a cell: a junction, or the bridge two holders make.
    fn pipe_unit(&self, x: i32, y: i32) -> bool {
        match self.inner.index(x, y) {
            Some(index) => {
                let sky = &self.inner.layers[1];
                sky.unit[index] || sky.count[index] == 2
            }
            None => false,
        }
    }

    /// Whether the two wires on a cell cross it legally: both straight, one per axis, no unit,
    /// and on the sky layer nothing on the ground under the bridge.
    fn legal_crossing(&self, layer: usize, x: i32, y: i32) -> bool {
        let Some(index) = self.inner.index(x, y) else {
            return false;
        };
        let side = &self.inner.layers[layer];
        if side.count[index] != 2 || side.unit[index] {
            return false;
        }
        let axes = [side.axis[index][0], side.axis[index][1]];
        let straight = (axes[0] == 1 && axes[1] == 2) || (axes[0] == 2 && axes[1] == 1);
        straight && (layer == 0 || self.ground_free(x, y))
    }

    /// The cells of a layer more wires hold than may legally share them.
    fn overused(&self, layer: usize) -> Vec<(i32, i32)> {
        let side = &self.inner.layers[layer];
        let mut out = Vec::new();
        for index in 0..side.count.len() {
            let (x, y) = self.inner.cell(index);
            if side.count[index] > 1 && !self.legal_crossing(layer, x, y) {
                out.push((x, y));
            } else if layer == 0 && side.count[index] > 0 && self.pipe_unit(x, y) {
                out.push((x, y));
            }
        }
        out
    }

    /// Every cell the line uses, on either layer.
    fn used(&self) -> Vec<(i32, i32)> {
        (0..self.inner.width * self.inner.height)
            .filter(|&index| self.inner.used(index))
            .map(|index| self.inner.cell(index))
            .collect()
    }

    /// Whether a logistics unit stands on a cell of a layer.
    fn unit(&mut self, layer: usize, x: i32, y: i32, value: bool) {
        if let Some(index) = self.inner.index(x, y) {
            self.inner.layers[layer].unit[index] = value;
        }
    }

    /// One wire takes a cell, travelling along `axis`.
    fn hold(&mut self, layer: usize, x: i32, y: i32, wire: i32, axis: u8) {
        if let Some(index) = self.inner.index(x, y) {
            self.inner.hold(layer, index, wire, axis);
        }
    }

    /// A whole path taken at once: one crossing instead of one per cell.
    fn hold_many(&mut self, layer: usize, cells: Vec<(i32, i32, u8)>, wire: i32) {
        for (x, y, axis) in cells {
            if let Some(index) = self.inner.index(x, y) {
                self.inner.hold(layer, index, wire, axis);
            }
        }
    }

    /// A whole path let go at once.
    fn release_many(&mut self, layer: usize, cells: Vec<(i32, i32)>, wire: i32) {
        for (x, y) in cells {
            if let Some(index) = self.inner.index(x, y) {
                self.inner.release(layer, index, wire);
            }
        }
    }

    /// A whole footprint blocked or freed at once, on both layers.
    fn block_many(&mut self, cells: Vec<(i32, i32)>, value: bool, owned: bool) {
        for (x, y) in cells {
            if let Some(index) = self.inner.index(x, y) {
                for layer in 0..LAYERS {
                    self.inner.layers[layer].blocked[index] = value;
                    if owned || !value {
                        self.inner.layers[layer].owned[index] = value && owned;
                    }
                }
            }
        }
    }

    /// The pylons the placed machines need and the machines none can reach: the same sweep the
    /// cost is measured with, so what is paid for is what gets built.
    fn pylons(
        &self,
        rects: Vec<(i32, i32, i32, i32)>,
        area: (i32, i32, i32, i32),
        size: i32,
        reach: i32,
    ) -> (Vec<(i32, i32)>, Vec<usize>) {
        let span = size + 2 * reach;
        let mut order: Vec<usize> = (0..rects.len()).collect();
        order.sort_by_key(|&i| (rects[i].1, rects[i].0));
        let mut clusters: Vec<(i32, i32, i32, i32)> = Vec::new();
        let mut members: Vec<Vec<usize>> = Vec::new();
        let mut uncovered = Vec::new();
        for i in order {
            let rect = rects[i];
            let mut joined = false;
            for slot in 0..clusters.len() {
                let box_ = clusters[slot];
                let grown = (
                    box_.0.min(rect.0),
                    box_.1.min(rect.1),
                    box_.2.max(rect.2),
                    box_.3.max(rect.3),
                );
                if grown.2 - grown.0 <= span
                    && grown.3 - grown.1 <= span
                    && self.spot(grown, area, size, reach, &[]).is_some()
                {
                    clusters[slot] = grown;
                    members[slot].push(i);
                    joined = true;
                    break;
                }
            }
            if joined {
                continue;
            }
            if self.spot(rect, area, size, reach, &[]).is_some() {
                clusters.push(rect);
                members.push(vec![i]);
            } else {
                uncovered.push(i);
            }
        }
        let mut anchors = Vec::new();
        for (slot, cluster) in clusters.iter().enumerate() {
            match self.spot(*cluster, area, size, reach, &anchors) {
                Some(spot) => anchors.push(spot),
                None => uncovered.extend(members[slot].iter().copied()),
            }
        }
        (anchors, uncovered)
    }

    /// One wire lets a cell go.
    fn release(&mut self, layer: usize, x: i32, y: i32, wire: i32) {
        if let Some(index) = self.inner.index(x, y) {
            self.inner.release(layer, index, wire);
        }
    }

    /// The wires a cell is closed to everything but; an empty list opens it.
    fn reserve(&mut self, layer: usize, x: i32, y: i32, owners: Vec<i32>) {
        let Some(index) = self.inner.index(x, y) else {
            return;
        };
        let side = &mut self.inner.layers[layer];
        if owners.is_empty() {
            side.reserved.remove(&index);
        } else {
            side.reserved.insert(index, owners);
        }
    }

    /// Add one wire to the owners a reserved cell is closed to everything but.
    fn reserve_add(&mut self, layer: usize, x: i32, y: i32, wire: i32) {
        let Some(index) = self.inner.index(x, y) else {
            return;
        };
        let owners = self.inner.layers[layer].reserved.entry(index).or_default();
        if !owners.contains(&wire) {
            owners.push(wire);
        }
    }

    /// Drop one wire from a cell's owners, opening the cell when it was the last.
    fn reserve_drop(&mut self, layer: usize, x: i32, y: i32, wire: i32) {
        let Some(index) = self.inner.index(x, y) else {
            return;
        };
        let side = &mut self.inner.layers[layer];
        if let Some(owners) = side.reserved.get_mut(&index) {
            owners.retain(|&owner| owner != wire);
            if owners.is_empty() {
                side.reserved.remove(&index);
            }
        }
    }

    /// What a cell of a layer has been charged for being contested.
    fn history(&mut self, layer: usize, x: i32, y: i32, value: f32) {
        if let Some(index) = self.inner.index(x, y) {
            self.inner.layers[layer].history[index] = value;
        }
    }

    /// Take every layer back to empty, for a grid the caller is about to refill.
    fn clear(&mut self) {
        let size = self.inner.width * self.inner.height;
        for layer in 0..LAYERS {
            self.inner.layers[layer] = Cells::new(size);
        }
    }

    /// Put the whole occupancy by, to come back to with `load_state`.
    fn save(&self) -> PyState {
        PyState {
            layers: self.inner.layers.clone(),
            width: self.inner.width,
            height: self.inner.height,
        }
    }

    /// Come back to a saved occupancy.
    fn load_state(&mut self, state: &PyState) -> PyResult<()> {
        if (state.width, state.height) != (self.inner.width, self.inner.height) {
            return Err(pyo3::exceptions::PyValueError::new_err("grid snapshot dimensions differ"));
        }
        self.inner.layers = state.layers.clone();
        Ok(())
    }

    /// Refill one layer in one call: the cells it blocks, the units on it, the wires holding
    /// each cell with their axis, the reservations, and the history.
    #[allow(clippy::too_many_arguments)]
    fn load(
        &mut self,
        layer: usize,
        blocked: Vec<(i32, i32)>,
        owned: Vec<(i32, i32)>,
        units: Vec<(i32, i32)>,
        holders: Vec<(i32, i32, i32, u8)>,
        reserved: Vec<(i32, i32, Vec<i32>)>,
        history: Vec<(i32, i32, f32)>,
    ) {
        let size = self.inner.width * self.inner.height;
        self.inner.layers[layer] = Cells::new(size);
        for (x, y) in blocked {
            if let Some(index) = self.inner.index(x, y) {
                self.inner.layers[layer].blocked[index] = true;
            }
        }
        for (x, y) in owned {
            if let Some(index) = self.inner.index(x, y) {
                self.inner.layers[layer].owned[index] = true;
            }
        }
        for (x, y) in units {
            if let Some(index) = self.inner.index(x, y) {
                self.inner.layers[layer].unit[index] = true;
            }
        }
        for (x, y, wire, axis) in holders {
            if let Some(index) = self.inner.index(x, y) {
                self.inner.hold(layer, index, wire, axis);
            }
        }
        for (x, y, owners) in reserved {
            if let Some(index) = self.inner.index(x, y) {
                if !owners.is_empty() {
                    self.inner.layers[layer].reserved.insert(index, owners);
                }
            }
        }
        for (x, y, value) in history {
            if let Some(index) = self.inner.index(x, y) {
                self.inner.layers[layer].history[index] = value;
            }
        }
    }

    /// The cheapest path from any start to any goal, or ``None``.
    #[allow(clippy::too_many_arguments)]
    fn astar(
        &self,
        layer: usize,
        wire: i32,
        starts: Ends,
        goals: Ends,
        present_cost: f32,
        share: bool,
        limit: f32,
        shared: Option<Vec<(i32, i32)>>,
    ) -> Option<Vec<(i32, i32)>> {
        self.inner.astar(&Search {
            layer,
            wire,
            starts: &starts,
            goals: &goals,
            present_cost,
            share,
            limit,
            shared: shared.as_ref(),
        })
    }

    /// Every wire holding a cell of a layer, for a test that holds the mirror to the Python
    /// state it is supposed to copy.
    fn holders(&self, layer: usize) -> Vec<(i32, i32, i32, u8)> {
        let side = &self.inner.layers[layer];
        let mut out = Vec::new();
        for index in 0..side.count.len() {
            let (x, y) = self.inner.cell(index);
            for slot in 0..side.count[index].min(2) as usize {
                out.push((x, y, side.holder[index][slot], side.axis[index][slot]));
            }
        }
        out
    }

    fn blocked(&self, layer: usize) -> Vec<(i32, i32)> {
        let side = &self.inner.layers[layer];
        (0..side.blocked.len())
            .filter(|&index| side.blocked[index])
            .map(|index| self.inner.cell(index))
            .collect()
    }

    fn units(&self, layer: usize) -> Vec<(i32, i32)> {
        let side = &self.inner.layers[layer];
        (0..side.unit.len())
            .filter(|&index| side.unit[index])
            .map(|index| self.inner.cell(index))
            .collect()
    }

    fn __repr__(&self) -> String {
        format!("_Grid({}x{})", self.inner.width, self.inner.height)
    }
}

impl PyGrid {
    /// A free square that covers rect whole and is none of taken.
    fn spot(
        &self,
        rect: (i32, i32, i32, i32),
        area: (i32, i32, i32, i32),
        size: i32,
        reach: i32,
        taken: &[(i32, i32)],
    ) -> Option<(i32, i32)> {
        let window = (
            area.0.max(rect.2 - size - reach),
            area.1.max(rect.3 - size - reach),
            (area.2 - size).min(rect.0 + reach) + 1,
            (area.3 - size).min(rect.1 + reach) + 1,
        );
        self.inner.free_square(window, size, taken)
    }
}

pub fn register_route_types(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyGrid>()?;
    m.add_class::<PyState>()?;
    m.add("AXIS_NONE", AXIS_NONE)?;
    m.add("AXIS_H", AXIS_H)?;
    m.add("AXIS_V", AXIS_V)?;
    m.add("AXIS_T", AXIS_T)?;
    Ok(())
}
