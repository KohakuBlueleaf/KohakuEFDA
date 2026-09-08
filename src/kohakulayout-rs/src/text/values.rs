//! Typing the VALUE tokens of the text form, and writing values back; Python's `values.py`.

use serde_json::Value;

use crate::ir::rate::Rate;

fn is_int(token: &str) -> bool {
    let body = token.strip_prefix('-').unwrap_or(token);
    !body.is_empty() && body.chars().all(|c| c.is_ascii_digit())
}

pub fn parse_scalar(token: &str, rates: bool) -> Value {
    if token == "true" {
        return Value::Bool(true);
    }
    if token == "false" {
        return Value::Bool(false);
    }
    if is_int(token) {
        if let Ok(n) = token.parse::<i64>() {
            return Value::Number(n.into());
        }
    }
    if rates {
        if let Some((n, d)) = token.split_once('/') {
            if !n.is_empty()
                && !d.is_empty()
                && n.chars().all(|c| c.is_ascii_digit())
                && d.chars().all(|c| c.is_ascii_digit())
            {
                let rate = Rate::new(n.parse().unwrap_or(0), d.parse().unwrap_or(1));
                return Value::String(rate.json_text());
            }
        }
    }
    Value::String(token.to_string())
}

/// A scalar, or a list of scalars when the token holds commas.
pub fn parse_value(token: &str, rates: bool) -> Value {
    if token.contains(',') {
        Value::Array(
            token
                .split(',')
                .filter(|p| !p.is_empty())
                .map(|p| parse_scalar(p, rates))
                .collect(),
        )
    } else {
        parse_scalar(token, rates)
    }
}

/// Python's `unicode_escape` decoding of the body of a quoted string, for the escapes the writer emits.
pub fn unquote(token: &str) -> String {
    let body = &token[1..token.len() - 1];
    if !body.contains('\\') {
        return body.to_string();
    }
    let mut out = String::new();
    let mut chars = body.chars().peekable();
    while let Some(c) = chars.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('n') => out.push('\n'),
            Some('t') => out.push('\t'),
            Some('r') => out.push('\r'),
            Some('"') => out.push('"'),
            Some('\\') => out.push('\\'),
            Some('\'') => out.push('\''),
            Some('u') => {
                let hex: String = (0..4).filter_map(|_| chars.next()).collect();
                if let Some(ch) = u32::from_str_radix(&hex, 16).ok().and_then(char::from_u32) {
                    out.push(ch);
                }
            }
            Some(other) => {
                out.push('\\');
                out.push(other);
            }
            None => out.push('\\'),
        }
    }
    out
}

pub fn quote(text: &str) -> String {
    let escaped = text
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n");
    format!("\"{escaped}\"")
}

pub fn write_scalar(value: &Value) -> String {
    match value {
        Value::Bool(b) => (if *b { "true" } else { "false" }).to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => {
            if s.is_empty()
                || s.chars().any(|c| " \t;{}#\",".contains(c))
                || s == "true"
                || s == "false"
                || is_int(s)
            {
                quote(s)
            } else {
                s.clone()
            }
        }
        other => other.to_string(),
    }
}

/// A JSON string `n/d` written by Python for a Fraction; text form prints it as a rate.
fn looks_like_rate(s: &str) -> Option<Rate> {
    let (n, d) = s.split_once('/')?;
    if n.is_empty() || d.is_empty() || !d.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let body = n.strip_prefix('-').unwrap_or(n);
    if body.is_empty() || !body.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    Some(Rate::new(n.parse().ok()?, d.parse().ok()?))
}

/// A metric is an int or a rate; a rate crosses JSON as a string and prints as the text form's rate.
pub fn write_metric(value: &Value) -> String {
    if let Value::String(s) = value {
        if let Some(rate) = looks_like_rate(s) {
            return rate.text();
        }
    }
    write_value(value)
}

/// For attrs and params, which the reader types by content: one element keeps a trailing comma, none is a lone comma.
pub fn write_loose_value(value: &Value) -> String {
    match value {
        Value::Array(items) if items.len() == 1 => format!("{},", write_scalar(&items[0])),
        Value::Array(items) if items.is_empty() => ",".to_string(),
        _ => write_value(value),
    }
}

pub fn write_value(value: &Value) -> String {
    match value {
        Value::Array(items) => items.iter().map(write_scalar).collect::<Vec<_>>().join(","),
        other => write_scalar(other),
    }
}
