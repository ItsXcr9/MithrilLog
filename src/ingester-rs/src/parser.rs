use chrono::{DateTime, Utc};
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::OnceLock;

// Regex patterns mirroring Python implementation
static ISO_TIMESTAMP_RE: OnceLock<Regex> = OnceLock::new();
static UUID_RE: OnceLock<Regex> = OnceLock::new();
static IP_RE: OnceLock<Regex> = OnceLock::new();
static HEX_RUN_RE: OnceLock<Regex> = OnceLock::new();
static QUOTED_STR_RE: OnceLock<Regex> = OnceLock::new();
static MAC_RE: OnceLock<Regex> = OnceLock::new();

fn get_iso_timestamp_re() -> &'static Regex {
    ISO_TIMESTAMP_RE.get_or_init(|| Regex::new(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})").unwrap())
}

fn get_uuid_re() -> &'static Regex {
    UUID_RE.get_or_init(|| Regex::new(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b").unwrap())
}

fn get_ip_re() -> &'static Regex {
    IP_RE.get_or_init(|| Regex::new(r"\b(?:\d{1,3}\.){3}\d{1,3}\b").unwrap())
}

fn get_hex_run_re() -> &'static Regex {
    HEX_RUN_RE.get_or_init(|| Regex::new(r"\b[0-9a-fA-F]{16,}\b").unwrap())
}

fn get_quoted_str_re() -> &'static Regex {
    QUOTED_STR_RE.get_or_init(|| Regex::new(r#""[^"]{5,}""#).unwrap())
}

fn get_mac_re() -> &'static Regex {
    MAC_RE.get_or_init(|| Regex::new(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b").unwrap())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogEvent {
    pub timestamp: DateTime<Utc>,
    pub host: String,
    pub app: String,
    pub severity: String,
    pub facility: String,
    pub message: String,
    pub raw: String,
    pub transport: String,
}

impl LogEvent {
    pub fn normalize_message(&self) -> String {
        let mut msg = self.message.clone();
        
        // Try to parse as JSON
        if msg.trim().starts_with('{') {
            if let Ok(data) = serde_json::from_str::<serde_json::Value>(&msg) {
                // Extract component and message type logic mirroring Python
                let component = data.get("c").and_then(|v| v.as_str()).unwrap_or("");
                let mut msg_text = String::new();

                // Handle nested MongoDB format
                if let Some(attr) = data.get("attr").and_then(|v| v.as_object()) {
                    if let Some(message) = attr.get("message").and_then(|v| v.as_object()) {
                        if let Some(m) = message.get("msg") {
                            msg_text = m.as_str().unwrap_or("").to_string();
                        }
                    }
                } else if let Some(m) = data.get("msg") {
                    if let Some(s) = m.as_str() {
                        msg_text = s.to_string();
                    } else if let Some(obj) = m.as_object() {
                        if let Some(inner) = obj.get("msg").and_then(|v| v.as_str()) {
                            msg_text = inner.to_string();
                        }
                    }
                }

                if !msg_text.is_empty() || !component.is_empty() {
                    // Normalize the extracted message
                    let re_nums = Regex::new(r"\b\d+\b").unwrap();
                    msg_text = re_nums.replace_all(&msg_text, "N").to_string();
                    
                    // Remove timestamp tuples
                    let re_ts_tuple = Regex::new(r"\(N, N\)").unwrap();
                    msg_text = re_ts_tuple.replace_all(&msg_text, "").to_string();
                    
                    // Remove specific fields
                    let re_fields = Regex::new(r"ts_sec:N|ts_usec:N").unwrap();
                    msg_text = re_fields.replace_all(&msg_text, "").to_string();
                    
                    let re_oldest = Regex::new(r"oldest timestamp:\s*\(N, N\)").unwrap();
                    msg_text = re_oldest.replace_all(&msg_text, "oldest timestamp: (N, N)").to_string();
                    
                    let re_meta = Regex::new(r"meta checkpoint timestamp:\s*\(N, N\)").unwrap();
                    msg_text = re_meta.replace_all(&msg_text, "meta checkpoint timestamp: (N, N)").to_string();
                    
                    let re_hex = Regex::new(r"0x[0-9a-fA-F]+").unwrap();
                    msg_text = re_hex.replace_all(&msg_text, "0xHEX").to_string();
                    
                    let re_thread = Regex::new(r#"thread:"[^"]*""#).unwrap();
                    msg_text = re_thread.replace_all(&msg_text, "").to_string();
                    
                    let re_session = Regex::new(r#"session_name:"[^"]*""#).unwrap();
                    msg_text = re_session.replace_all(&msg_text, "").to_string();
                    
                    let re_commas = Regex::new(r",\s*,").unwrap();
                    msg_text = re_commas.replace_all(&msg_text, ",").to_string();
                    
                    let re_spaces = Regex::new(r"\s+").unwrap();
                    msg_text = re_spaces.replace_all(&msg_text, " ").to_string();
                    
                    msg_text = mask_variable_tokens(&msg_text);

                    if !component.is_empty() && !msg_text.is_empty() {
                        return format!("{}:{}", component, msg_text);
                    } else if !component.is_empty() {
                        return component.to_string();
                    } else if !msg_text.is_empty() {
                        return msg_text;
                    }
                }
            }
        }

        // Non-JSON normalization
        let re_nums = Regex::new(r"\d+").unwrap();
        msg = re_nums.replace_all(&msg, "N").to_string();
        
        let re_ts1 = Regex::new(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*[+-]\d{2}:\d{2}").unwrap();
        msg = re_ts1.replace_all(&msg, "TIMESTAMP").to_string();
        
        let re_ts2 = Regex::new(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*").unwrap();
        msg = re_ts2.replace_all(&msg, "TIMESTAMP").to_string();
        
        let re_spaces = Regex::new(r"\s+").unwrap();
        msg = re_spaces.replace_all(&msg, " ").trim().to_string();
        
        mask_variable_tokens(&msg)
    }

    pub fn pattern_payload(&self) -> serde_json::Value {
        serde_json::json!({
            "severity": self.severity,
            "facility": self.facility,
            "message": self.normalize_message(),
        })
    }

    pub fn dedupe_key(&self) -> Vec<u8> {
        // Sort keys is handled by serde_json::to_vec if we use a struct, but Value might not be deterministic.
        // However, the Python code uses json.dumps(sort_keys=True).
        // We can construct a BTreeMap or similar to ensure order, or just use the normalized message string + severity + facility.
        // Actually, let's just use the JSON string of the payload, ensuring key order.
        // serde_json doesn't guarantee key order for maps unless "preserve_order" feature is on, but we can just manually format it or use a struct.
        // Let's use a struct for the payload to ensure order.
        #[derive(Serialize)]
        struct Payload {
            facility: String,
            message: String,
            severity: String,
        }
        let payload = Payload {
            facility: self.facility.clone(),
            message: self.normalize_message(),
            severity: self.severity.clone(),
        };
        serde_json::to_vec(&payload).unwrap()
    }

    pub fn sample_key(&self) -> String {
        format!("{}:{}:{}", self.host, self.severity, self.app)
    }

    pub fn pattern_id(&self) -> String {
        use sha1::{Sha1, Digest};
        let mut hasher = Sha1::new();
        hasher.update(self.dedupe_key());
        hex::encode(hasher.finalize())
    }
}

fn mask_variable_tokens(text: &str) -> String {
    let mut text = text.to_string();
    text = get_uuid_re().replace_all(&text, "UUID").to_string();
    text = get_mac_re().replace_all(&text, "MAC").to_string();
    text = get_ip_re().replace_all(&text, "IP").to_string();
    text = get_hex_run_re().replace_all(&text, "HEX").to_string();
    text = get_quoted_str_re().replace_all(&text, "\"STR\"").to_string();
    
    let re_0x = Regex::new(r"\b0x[0-9a-fA-F]+\b").unwrap();
    text = re_0x.replace_all(&text, "0xHEX").to_string();
    
    let re_n = Regex::new(r"\b\d+\b").unwrap();
    text = re_n.replace_all(&text, "N").to_string();
    
    let re_spaces = Regex::new(r"\s+").unwrap();
    text = re_spaces.replace_all(&text, " ").trim().to_string();
    
    text
}

pub fn parse_syslog(payload: &[u8], addr: &str, transport: &str) -> LogEvent {
    let raw = String::from_utf8_lossy(payload).trim().to_string();
    let mut timestamp = Utc::now();
    let mut host = addr.to_string();
    let mut app = "-".to_string();
    let mut severity = "info".to_string();
    let mut facility = "user".to_string();
    let mut message;

    let mut remainder = raw.as_str();

    // Parse PRI <N>
    if raw.starts_with('<') {
        if let Some(end) = raw.find('>') {
            if let Ok(pri) = raw[1..end].parse::<i32>() {
                let severities = ["emerg", "alert", "crit", "err", "warn", "notice", "info", "debug"];
                severity = severities[(pri % 8) as usize].to_string();
                facility = (pri / 8).to_string();
                if end + 1 < raw.len() {
                    remainder = raw[end+1..].trim();
                } else {
                    remainder = "";
                }
            }
        }
    }

    // Simple syslog parsing (RFC3164-ish)
    // Format: Timestamp Host App: Message
    // Or: Timestamp Host Message
    let parts: Vec<&str> = remainder.splitn(5, ' ').collect();
    if parts.len() >= 4 {
        // Try parsing timestamp: MMM DD HH:MM:SS
        // This is hard without year. We'll skip complex timestamp parsing for now and rely on server time if it fails,
        // or try to match the Python logic which defaults to server time if parse fails.
        // Python: datetime.strptime(" ".join(parts[:3]), "%b %d %H:%M:%S")
        // We'll assume server time for simplicity in this MVP unless we see ISO timestamp.
        
        // Host is usually part 3 (index 3) if timestamp is 3 parts
        host = parts[3].to_string();
        
        let message_part = if parts.len() == 5 { parts[4] } else { "" };
        
        if let Some(idx) = message_part.find(':') {
            // Split tag and message
            // Python: _split_tag_and_message
            let tag_part = &message_part[..idx];
            let msg_part = &message_part[idx+1..];
            
            // App token selection logic
            app = tag_part.split_whitespace().last().unwrap_or("-").to_string();
            message = msg_part.trim().to_string();
        } else {
            message = message_part.trim().to_string();
        }
    } else {
        // Fallback
        message = remainder.to_string();
    }

    // Check for structured timestamp in raw message
    if let Some(mat) = get_iso_timestamp_re().find(&raw) {
        if let Ok(ts) = DateTime::parse_from_rfc3339(mat.as_str()) {
            timestamp = ts.with_timezone(&Utc);
        }
    }

    LogEvent {
        timestamp,
        host,
        app,
        severity,
        facility,
        message,
        raw,
        transport: transport.to_string(),
    }
}
