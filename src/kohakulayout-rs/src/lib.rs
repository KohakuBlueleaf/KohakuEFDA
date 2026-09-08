//! The native twin of KohakuLayout. Python is the ground truth; every function here
//! reproduces a Python function byte for byte and is checked by the parity suite.

pub mod ir;
pub mod kernel;
pub mod text;

#[cfg(feature = "python")]
mod pyo3_module;

/// One error type for the crate; the Python bridge turns it into a `ValueError`.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("text: {0}")]
    Text(String),
    #[error("ir: {0}")]
    Ir(String),
    #[error("json: {0}")]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, Error>;
