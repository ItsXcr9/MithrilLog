use anyhow::Result;
use chrono::{DateTime, Datelike, Timelike, Utc};
use serde_json::Value;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

pub struct JournalWriter {
    base_dir: PathBuf,
}

impl JournalWriter {
    pub fn new(base_dir: PathBuf) -> Self {
        fs::create_dir_all(&base_dir).ok();
        Self { base_dir }
    }

    pub fn bucket_path(&self, time: DateTime<Utc>) -> PathBuf {
        let year = time.year();
        let month = time.month();
        let day = time.day();
        let hour = time.hour();
        let minute = time.minute();

        self.base_dir
            .join(format!("{:04}", year))
            .join(format!("{:02}", month))
            .join(format!("{:02}", day))
            .join(format!("{:02}", hour))
            .join(format!("{:02}.ndjson", minute))
    }

    pub fn append(&self, record: &Value, bucket_time: DateTime<Utc>) -> Result<PathBuf> {
        let path = self.bucket_path(bucket_time);
        
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)?;

        // Use compact JSON format
        let line = serde_json::to_string(record)?;
        writeln!(file, "{}", line)?;

        Ok(path)
    }

    pub fn write_metadata(&self, path: &Path, metadata: &Value) -> Result<()> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        let mut file = std::fs::File::create(path)?;
        serde_json::to_writer_pretty(&mut file, metadata)?;
        Ok(())
    }
}
