//! Maps read through to a base they never change: an attempt's writes kept beside the mirror's
//! records, so the attempt starts without copying them and drops its writes at the end.

use std::borrow::Borrow;
use std::hash::Hash;

use super::grid::XY;
use super::hash::Map;
use super::records::Attach;

/// A map over a base: the entries written or removed since, the base's for every other key.
pub struct Overlay<'a, K, V> {
    base: &'a Map<K, V>,
    changed: Map<K, Option<V>>,
}

impl<'a, K: Eq + Hash + Clone, V: Clone> Overlay<'a, K, V> {
    pub fn new(base: &'a Map<K, V>) -> Self {
        Overlay { base, changed: Map::default() }
    }

    pub fn get<Q>(&self, key: &Q) -> Option<&V>
    where
        K: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        match self.changed.get(key) {
            Some(value) => value.as_ref(),
            None => self.base.get(key),
        }
    }

    pub fn contains_key<Q>(&self, key: &Q) -> bool
    where
        K: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        self.get(key).is_some()
    }

    pub fn insert(&mut self, key: K, value: V) {
        self.changed.insert(key, Some(value));
    }

    pub fn remove<Q>(&mut self, key: &Q) -> Option<V>
    where
        K: Borrow<Q>,
        Q: Hash + Eq + ToOwned<Owned = K> + ?Sized,
    {
        let old = self.get(key).cloned();
        if old.is_some() {
            self.changed.insert(key.to_owned(), None);
        }
        old
    }

    /// The value at the key to change in place, the default written there when there is none.
    pub fn entry_or_default(&mut self, key: K) -> &mut V
    where
        V: Default,
    {
        let base = self.base;
        self.changed
            .entry(key)
            .or_insert_with_key(|k| base.get(k).cloned())
            .get_or_insert_with(V::default)
    }

    /// Every entry: the base's where nothing changed them, then the ones written.
    pub fn iter(&self) -> impl Iterator<Item = (&K, &V)> {
        self.base
            .iter()
            .filter(|(k, _)| !self.changed.contains_key(*k))
            .chain(
                self.changed
                    .iter()
                    .filter_map(|(k, v)| v.as_ref().map(|v| (k, v))),
            )
    }

    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.iter().map(|(_, v)| v)
    }
}

/// The attach tables over the mirror's.
pub struct AttachOver<'a> {
    pub open: Overlay<'a, (String, XY), String>,
    pub routed: Overlay<'a, (String, XY), String>,
    pub ports: Overlay<'a, (String, XY), XY>,
    pub entries: Overlay<'a, String, Vec<(String, String, XY)>>,
    pub pins: Overlay<'a, String, Vec<(String, String, String)>>,
}

impl<'a> AttachOver<'a> {
    pub fn new(base: &'a Attach) -> Self {
        AttachOver {
            open: Overlay::new(&base.open),
            routed: Overlay::new(&base.routed),
            ports: Overlay::new(&base.ports),
            entries: Overlay::new(&base.entries),
            pins: Overlay::new(&base.pins),
        }
    }
}
