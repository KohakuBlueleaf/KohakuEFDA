//! A rate is a normalised fraction; it crosses JSON as the string `"n/d"`, the way Python writes it.

use serde::{Deserialize, Deserializer, Serialize, Serializer};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Rate {
    pub num: i64,
    pub den: i64,
}

fn gcd(a: i64, b: i64) -> i64 {
    let (mut a, mut b) = (a.abs(), b.abs());
    while b != 0 {
        let t = a % b;
        a = b;
        b = t;
    }
    a
}

impl Rate {
    pub fn new(num: i64, den: i64) -> Rate {
        if den == 0 {
            return Rate { num: 0, den: 1 };
        }
        let g = gcd(num, den).max(1);
        let sign = if den < 0 { -1 } else { 1 };
        Rate { num: sign * num / g, den: sign * den / g }
    }

    pub fn int(value: i64) -> Rate {
        Rate { num: value, den: 1 }
    }

    pub fn is_zero(&self) -> bool {
        self.num == 0
    }

    /// The text form: the numerator alone when whole, else `n/d`.
    pub fn text(&self) -> String {
        if self.den == 1 {
            self.num.to_string()
        } else {
            format!("{}/{}", self.num, self.den)
        }
    }

    /// The JSON form: what Python's `str(Fraction)` writes, the same as the text form.
    pub fn json_text(&self) -> String {
        self.text()
    }

    pub fn parse(text: &str) -> Option<Rate> {
        let text = text.trim();
        if let Some((n, d)) = text.split_once('/') {
            Some(Rate::new(n.trim().parse().ok()?, d.trim().parse().ok()?))
        } else {
            text.parse::<i64>().ok().map(Rate::int)
        }
    }
}

impl Serialize for Rate {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.json_text())
    }
}

impl<'de> Deserialize<'de> for Rate {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Rate, D::Error> {
        let value = serde_json::Value::deserialize(deserializer)?;
        match value {
            serde_json::Value::String(s) => {
                Rate::parse(&s).ok_or_else(|| serde::de::Error::custom(format!("not a rate: {s}")))
            }
            serde_json::Value::Number(n) => n
                .as_i64()
                .map(Rate::int)
                .ok_or_else(|| serde::de::Error::custom("not a rate")),
            other => Err(serde::de::Error::custom(format!("not a rate: {other}"))),
        }
    }
}
