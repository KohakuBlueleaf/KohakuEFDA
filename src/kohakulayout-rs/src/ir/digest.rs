//! sha256 over canonical JSON bytes, hex encoded; the same digest Python computes.

use sha2::{Digest, Sha256};

pub fn digest_of(value: &serde_json::Value) -> String {
    let text = super::json::canonical(value);
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    let bytes = hasher.finalize();
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
