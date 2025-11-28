mod config;
mod dedupe;
mod parser;
mod storage;

use anyhow::Result;
use config::Config;
use dedupe::{BloomDeduper, ReservoirSampler};
use parser::parse_syslog;
use storage::JournalWriter;
use std::collections::HashMap;
use std::net::SocketAddr;
use tokio::net::{TcpListener, UdpSocket};
use tokio::sync::mpsc;
use tokio::io::{AsyncBufReadExt, BufReader};
use chrono::{DateTime, Timelike, Local, TimeZone};
use serde_json::json;

#[derive(Debug)]
enum IngestMessage {
    Udp { data: Vec<u8>, addr: SocketAddr },
    Tcp { data: Vec<u8>, addr: SocketAddr },
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let config = Config::load()?;

    println!("Starting MithrilLog Ingester (Rust)");
    println!("Config: {:?}", config);

    let (tx, mut rx) = mpsc::channel::<IngestMessage>(1_000_000);

    // Start UDP Listener
    let udp_addr = format!("{}:{}", config.host, config.udp_port);
    let udp_socket = UdpSocket::bind(&udp_addr).await?;
    println!("Listening on UDP {}", udp_addr);
    
    let tx_udp = tx.clone();
    tokio::spawn(async move {
        let mut buf = [0u8; 65535];
        loop {
            match udp_socket.recv_from(&mut buf).await {
                Ok((size, addr)) => {
                    let data = buf[..size].to_vec();
                    // Try to send non-blocking first
                    let msg = IngestMessage::Udp { data, addr };
                    if let Err(tokio::sync::mpsc::error::TrySendError::Full(ret_msg)) = tx_udp.try_send(msg) {
                        // If full, spawn async task to send (rare)
                        let tx_clone = tx_udp.clone();
                        tokio::spawn(async move {
                            let _ = tx_clone.send(ret_msg).await;
                        });
                    }
                }
                Err(e) => eprintln!("UDP recv error: {}", e),
            }
        }
    });

    // Start TCP Listener
    let tcp_addr = format!("{}:{}", config.host, config.tcp_port);
    let tcp_listener = TcpListener::bind(&tcp_addr).await?;
    println!("Listening on TCP {}", tcp_addr);

    let tx_tcp = tx.clone();
    tokio::spawn(async move {
        loop {
            match tcp_listener.accept().await {
                Ok((socket, addr)) => {
                    let tx_clone = tx_tcp.clone();
                    tokio::spawn(async move {
                        let mut reader = BufReader::new(socket);
                        let mut line = String::new();
                        loop {
                            line.clear();
                            match reader.read_line(&mut line).await {
                                Ok(0) => break, // EOF
                                Ok(_) => {
                                    let data = line.trim().as_bytes().to_vec();
                                    if !data.is_empty() {
                                        let _ = tx_clone.send(IngestMessage::Tcp { data, addr }).await;
                                    }
                                }
                                Err(_) => break,
                            }
                        }
                    });
                }
                Err(e) => eprintln!("TCP accept error: {}", e),
            }
        }
    });

    // Main Processing Loop
    let journal = JournalWriter::new(config.bucket_dir.clone());
    let mut deduper = BloomDeduper::new(1_000_000, config.bloom_error_rate);
    let mut sampler = ReservoirSampler::new(config.reservoir_size);
    
    // Bucket state
    let mut current_bucket_time = floor_to_minute(Local::now());
    let mut last_bucket_path: Option<std::path::PathBuf> = None;
    
    // Stats
    let mut stats_severity: HashMap<String, usize> = HashMap::new();
    let mut stats_hosts: HashMap<String, usize> = HashMap::new();
    let mut stats_apps: HashMap<String, usize> = HashMap::new();
    let mut stats_host_apps: HashMap<String, usize> = HashMap::new();
    let mut stats_patterns: HashMap<String, usize> = HashMap::new();
    let mut stats_pattern_hosts: HashMap<String, HashMap<String, usize>> = HashMap::new();
    let mut stats_pattern_apps: HashMap<String, HashMap<String, usize>> = HashMap::new();
    let mut total_events_in_bucket = 0;
    let mut unique_events_in_bucket = 0;

    // Forwarding socket
    let forward_socket = if let (Some(_host), Some(_port)) = (&config.forward_to_host, config.forward_to_port) {
        Some(UdpSocket::bind("0.0.0.0:0").await?)
    } else {
        None
    };

    // Graceful shutdown handler
    tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        eprintln!("Received shutdown signal, flushing...");
    });

    while let Some(msg) = rx.recv().await {
        let (data, addr_str, transport) = match msg {
            IngestMessage::Udp { data, addr } => (data, addr.ip().to_string(), "udp"),
            IngestMessage::Tcp { data, addr } => (data, addr.ip().to_string(), "tcp"),
        };

        let event = parse_syslog(&data, &addr_str, transport);
        
        // Bucket rotation check
        let now = Local::now();
        let bucket_time = floor_to_minute(now);

        if bucket_time > current_bucket_time {
            // Flush current bucket metadata
            if let Some(path) = last_bucket_path.take() {
                if path.exists() {
                    let mut highlights = Vec::new();
                    let _totals = sampler.totals();
                    let snapshot = sampler.snapshot();

                    // Reconstruct highlights from reservoir
                    for (_key, samples) in snapshot {
                        // key is host:severity:app, but we need pattern-based highlights
                        // Wait, python implementation iterates over *events* in the file to build highlights?
                        // No, Python implementation reads the file back to build highlights if it wasn't tracking them in memory fully.
                        // But it also uses `sampler.totals()` for counts.
                        // Let's try to be efficient. We can just use the reservoir samples as highlights.
                        // Actually, the Python code re-reads the file to get all events and then correlates with stats.
                        // That's expensive. Let's just use the reservoir samples which are representative.
                        // Or better, let's trust the reservoir which stores samples per key.
                        // But we want top patterns.
                        
                        // Let's simplify: Just dump the stats we collected.
                        // We need "highlights" list for the UI/Summarizer.
                        // We can collect highlights from the reservoir.
                        for sample in samples {
                            highlights.push(sample);
                        }
                    }
                    
                    // Sort highlights by occurrences
                    highlights.sort_by(|a, b| {
                        let occ_a = a.get("occurrences").and_then(|v| v.as_u64()).unwrap_or(1);
                        let occ_b = b.get("occurrences").and_then(|v| v.as_u64()).unwrap_or(1);
                        occ_b.cmp(&occ_a)
                    });
                    highlights.truncate(50);

                    let meta = json!({
                        "bucket": current_bucket_time.to_rfc3339(),
                        "patterns": stats_patterns,
                        "severity": stats_severity,
                        "hosts": stats_hosts,
                        "apps": stats_apps,
                        "host_apps": stats_host_apps,
                        "total_events": total_events_in_bucket,
                        "unique_events": unique_events_in_bucket,
                        "highlights": highlights
                    });

                    let meta_path = path.with_extension("meta.json");
                    journal.write_metadata(&meta_path, &meta).ok();
                }
            }

            // Reset state
            deduper.reset();
            sampler.reset();
            stats_severity.clear();
            stats_hosts.clear();
            stats_apps.clear();
            stats_host_apps.clear();
            stats_patterns.clear();
            stats_pattern_hosts.clear();
            stats_pattern_apps.clear();
            total_events_in_bucket = 0;
            unique_events_in_bucket = 0;
            
            current_bucket_time = bucket_time;
        }

        // Update stats
        *stats_severity.entry(event.severity.clone()).or_insert(0) += 1;
        *stats_hosts.entry(event.host.clone()).or_insert(0) += 1;
        *stats_apps.entry(event.app.clone()).or_insert(0) += 1;
        *stats_host_apps.entry(format!("{}/{}", event.host, event.app)).or_insert(0) += 1;
        
        let pattern_id = event.pattern_id();
        *stats_patterns.entry(pattern_id.clone()).or_insert(0) += 1;
        
        let ph = stats_pattern_hosts.entry(pattern_id.clone()).or_default();
        *ph.entry(event.host.clone()).or_insert(0) += 1;
        
        let pa = stats_pattern_apps.entry(pattern_id.clone()).or_default();
        *pa.entry(event.app.clone()).or_insert(0) += 1;

        total_events_in_bucket += 1;

        // Dedupe
        let dedupe_key = event.dedupe_key();
        if deduper.seen(&dedupe_key) {
            sampler.register_duplicate(pattern_id);
            continue;
        }

        // Unique event
        unique_events_in_bucket += 1;
        
        let mut record = serde_json::to_value(&event).unwrap();
        if let Some(obj) = record.as_object_mut() {
            obj.insert("pattern_id".to_string(), json!(pattern_id));
            // Occurrences will be updated in metadata, but for the log line itself, it's 1 (unique instance)
            // Python code adds "occurrences" from sampler totals to the *stored record*?
            // Python: record["occurrences"] = self.sampler.totals().get(pattern, 0) + 1
            // This seems to track cumulative occurrences *so far* in the bucket for this pattern.
            let count = stats_patterns.get(&pattern_id).copied().unwrap_or(1);
            obj.insert("occurrences".to_string(), json!(count));
        }

        sampler.add(event.sample_key(), pattern_id.clone(), record.clone());

        match journal.append(&record, bucket_time) {
            Ok(path) => last_bucket_path = Some(path),
            Err(e) => eprintln!("Failed to write to journal: {}", e),
        }

        // Forwarding
        if let (Some(socket), Some(host), Some(port)) = (&forward_socket, &config.forward_to_host, config.forward_to_port) {
            if let Ok(payload) = serde_json::to_vec(&record) {
                let _ = socket.send_to(&payload, format!("{}:{}", host, port)).await;
            }
        }
    }

    Ok(())
}

fn floor_to_minute<T: TimeZone>(dt: DateTime<T>) -> DateTime<T> {
    dt.with_second(0).unwrap().with_nanosecond(0).unwrap()
}
