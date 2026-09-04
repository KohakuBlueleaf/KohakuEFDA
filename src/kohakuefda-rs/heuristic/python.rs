//! `_Placement`: the heuristic placer's state and its annealing, handed everything once in flat
//! arrays so that nothing crosses the boundary per move.

use pyo3::prelude::*;

use crate::heuristic::core::{Placement, Scale, Terms, Weights};
use crate::heuristic::search::{anneal, Settings};

type Sizes = Vec<[(i32, i32); 4]>;
type Offsets = Vec<[Vec<(i32, i32)>; 4]>;
type Pads = Vec<[(i32, i32, i32, i32); 4]>;

fn four<T: Clone>(rows: Vec<Vec<T>>, what: &str) -> PyResult<Vec<[T; 4]>> {
    rows.into_iter()
        .map(|row| {
            <[T; 4]>::try_from(row).map_err(|_| {
                pyo3::exceptions::PyValueError::new_err(format!("{what} needs four rotations"))
            })
        })
        .collect()
}

#[pyclass]
pub struct _Placement {
    inner: Placement,
}

#[pymethods]
impl _Placement {
    #[new]
    #[allow(clippy::too_many_arguments)]
    fn new(
        size: Vec<Vec<(i32, i32)>>,
        offset: Vec<Vec<Vec<(i32, i32)>>>,
        pad: Vec<Vec<(i32, i32, i32, i32)>>,
        margin: Vec<i32>,
        frozen: Vec<bool>,
        wire_from: Vec<(usize, usize)>,
        wire_to: Vec<(usize, usize)>,
        groups: Vec<Vec<usize>>,
        unit_of: Vec<i32>,
        area_rect: (i32, i32, i32, i32),
        grid: (i32, i32),
    ) -> PyResult<Self> {
        let count = size.len();
        let size: Sizes = four(size, "size")?;
        let offset: Offsets = four(offset, "offset")?;
        let pad: Pads = four(pad, "pad")?;
        let mut incident: Vec<Vec<usize>> = vec![Vec::new(); count];
        for (wire, (source, _)) in wire_from.iter().enumerate() {
            incident[*source].push(wire);
        }
        for (wire, (sink, _)) in wire_to.iter().enumerate() {
            if wire_from[wire].0 != *sink {
                incident[*sink].push(wire);
            }
        }
        let mut group_of = vec![-1i32; count];
        for (index, members) in groups.iter().enumerate() {
            for &member in members {
                group_of[member] = index as i32;
            }
        }
        let floor = (0..count)
            .map(|b| (size[b][0].0 as i64) * (size[b][0].1 as i64))
            .sum();
        let wires = wire_from.len();
        Ok(_Placement {
            inner: Placement {
                count,
                x: vec![0; count],
                y: vec![0; count],
                rotation: vec![0; count],
                w: (0..count).map(|b| size[b][0].0).collect(),
                h: (0..count).map(|b| size[b][0].1).collect(),
                size,
                offset,
                pad,
                margin,
                extra: vec![0; count],
                frozen,
                wire_from,
                wire_to,
                incident,
                length: vec![0; wires],
                groups,
                group_of,
                unit_of,
                area_rect,
                heat: vec![0.0; (grid.0 * grid.1) as usize],
                stride: grid.0,
                floor,
                weights: Weights {
                    area: 1.0,
                    wire: 1.0,
                    overlap: 8.0,
                    group: 8.0,
                    shut: 8.0,
                    crowd: 1.0,
                    tight: 4.0,
                    slack: 1.5,
                },
                scale: Scale { area: 1.0, wire: 1.0 },
                terms: Terms::default(),
            },
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn weigh(
        &mut self,
        area: f64,
        wire: f64,
        overlap: f64,
        group: f64,
        shut: f64,
        crowd: f64,
        tight: f64,
        slack: f64,
    ) {
        self.inner.weights = Weights { area, wire, overlap, group, shut, crowd, tight, slack };
    }

    fn adopt(&mut self, anchors: Vec<(i32, i32, usize)>) {
        for (block, (x, y, rotation)) in anchors.into_iter().enumerate() {
            self.inner.x[block] = x;
            self.inner.y[block] = y;
            self.inner.rotation[block] = rotation;
            let (width, height) = self.inner.size[block][rotation];
            self.inner.w[block] = width;
            self.inner.h[block] = height;
        }
        self.inner.recompute();
    }

    fn anchors(&self) -> Vec<(i32, i32, usize)> {
        (0..self.inner.count)
            .map(|b| (self.inner.x[b], self.inner.y[b], self.inner.rotation[b]))
            .collect()
    }

    fn warm(&mut self, cells: Vec<(i32, i32)>, amount: f64) {
        for (x, y) in cells {
            let index = (y * self.inner.stride + x) as usize;
            if index < self.inner.heat.len() {
                self.inner.heat[index] += amount;
            }
        }
    }

    fn cool(&mut self, keep: f64) {
        for value in self.inner.heat.iter_mut() {
            *value *= keep;
        }
    }

    fn widen(&mut self, blocks: Vec<usize>, most: i32) {
        for block in blocks {
            self.inner.extra[block] = (self.inner.extra[block] + 1).min(most);
        }
        self.inner.recompute();
    }

    /// Every term rebuilt from the anchors, for the test that holds this to the Python one.
    fn terms(&mut self) -> (i64, i64, i64, i64, i64, f64) {
        self.inner.recompute();
        let terms = self.inner.terms;
        (terms.area, terms.wire, terms.overlap, terms.group, terms.shut, terms.crowd)
    }

    fn cost(&self) -> f64 {
        self.inner.cost()
    }

    #[allow(clippy::too_many_arguments)]
    fn anneal(
        &mut self,
        seed: u64,
        moves: usize,
        window: usize,
        warmup: usize,
        accept_initial: f64,
        end: f64,
        range_start: f64,
        range_floor: i32,
        weights: (f64, f64, f64, f64),
        polish: usize,
        polish_overlap: f64,
    ) -> (usize, usize, f64) {
        let settings = Settings {
            moves,
            window: window.max(1),
            warmup,
            accept_initial,
            end,
            range_start,
            range_floor,
            weights: [weights.0, weights.1, weights.2, weights.3],
            polish,
            polish_overlap,
        };
        let trace = anneal(&mut self.inner, &settings, seed);
        (trace.steps, trace.accepted, trace.best)
    }
}

pub fn register_heuristic_types(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<_Placement>()?;
    Ok(())
}
