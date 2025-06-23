use clap::Parser;
use rss::Channel;
use reqwest;
use std::fs::{File, create_dir_all};
use std::io::Write;
use std::path::Path;
use std::sync::Arc;
use futures::stream::FuturesUnordered;
use futures::StreamExt;
use tokio::sync::Semaphore;
use indicatif::{ProgressBar, ProgressStyle, MultiProgress};
use serde_json::{to_string_pretty};
use chrono;

#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
struct Args {
    /// The URL of the podcast RSS feed
    #[clap(short, long)]
    url: String,

    /// The directory to save the episodes
    #[clap(short, long)]
    output: String,

    /// The number of episodes to download
    #[clap(short, long)]
    count: Option<usize>,

    /// Number of concurrent downloads
    #[clap(short, long, default_value = "1")]
    threads: usize,

    /// Save episode metadata as JSON files
    #[clap(short, long)]
    metadata: bool,
}

#[derive(serde::Serialize)]
struct EpisodeMetadata {
    title: String,
    description: Option<String>,
    pub_date: Option<String>,
    duration: Option<String>,
    author: Option<String>,
    file_url: String,
    guid: Option<String>,
    link: Option<String>,
    categories: Vec<String>,
}

fn save_episode_metadata(
    item: &rss::Item,
    output_dir: &str,
    filename: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let metadata = EpisodeMetadata {
        title: item.title().unwrap_or("Unknown Title").to_string(),
        description: item.description().map(|s| s.to_string()),
        pub_date: item.pub_date().map(|s| s.to_string()),
        duration: item.itunes_ext().and_then(|ext| ext.duration()).map(|s| s.to_string()),
        author: item.author().map(|s| s.to_string()),
        file_url: item.enclosure().map(|e| e.url().to_string()).unwrap_or_default(),
        guid: item.guid().map(|g| g.value().to_string()),
        link: item.link().map(|s| s.to_string()),
        categories: item.categories().iter().map(|c| c.name().to_string()).collect(),
    };

    let metadata_filename = filename.replace(".mp3", ".json").replace(".m4a", ".json").replace(".wav", ".json");
    let metadata_path = format!("{}/{}", output_dir, metadata_filename);
    
    let metadata_json = to_string_pretty(&metadata)?;
    std::fs::write(metadata_path, metadata_json)?;
    
    Ok(())
}

async fn download_episode(
    url: String,
    filename: String,
    output_dir: String,
    episode_index: usize,
    total_episodes: usize,
    semaphore: Arc<Semaphore>,
    multi_progress: Arc<MultiProgress>,
    item: rss::Item,
    save_metadata: bool,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let _permit = semaphore.acquire().await?;
    
    let file_path = format!("{}/{}", output_dir, filename);
    
    // Check if file already exists
    if Path::new(&file_path).exists() {
        let pb = multi_progress.add(ProgressBar::new_spinner());
        pb.set_style(
            ProgressStyle::default_spinner()
                .template("{spinner:.yellow} [{elapsed_precise}] [{wide_msg}]")
                .unwrap()
        );
        pb.set_message(format!("[{}/{}] Skipping (already exists): {}", episode_index + 1, total_episodes, filename));
        
        // Simulate a brief delay to show the skip message
        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
        
        pb.finish_with_message(format!("[{}/{}] Skipped: {}", episode_index + 1, total_episodes, filename));
        return Ok(());
    }

    // Save metadata if enabled
    if save_metadata {
        if let Err(e) = save_episode_metadata(&item, &output_dir, &filename) {
            eprintln!("Warning: Failed to save metadata for {}: {}", filename, e);
        }
    }
    
    // Create progress bar for this download using the multi-progress
    let pb = multi_progress.add(ProgressBar::new_spinner());
    pb.set_style(
        ProgressStyle::default_spinner()
            .template("{spinner:.green} [{elapsed_precise}] [{wide_msg}]")
            .unwrap()
    );
    pb.set_message(format!("[{}/{}] Downloading: {}", episode_index + 1, total_episodes, filename));

    let response = reqwest::get(&url).await?;
    
    // Get content length for progress tracking
    let total_size = response.content_length().unwrap_or(0);
    
    if total_size > 0 {
        // Switch to determinate progress bar if we know the size
        pb.set_length(total_size);
        pb.set_style(
            ProgressStyle::default_bar()
                .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {bytes}/{total_bytes} ({eta}) {msg}")
                .unwrap()
                .progress_chars("#>-")
        );
    }

    let mut response = response;
    let mut dest = File::create(&file_path)?;
    let mut downloaded: u64 = 0;
    
    while let Some(chunk) = response.chunk().await? {
        dest.write_all(&chunk)?;
        downloaded += chunk.len() as u64;
        
        if total_size > 0 {
            pb.set_position(downloaded);
        }
    }
    
    pb.finish_with_message(format!("[{}/{}] Finished: {}", episode_index + 1, total_episodes, filename));

    Ok(())
}

fn sanitize_filename(title: &str) -> String {
    title
        .chars()
        .map(|c| match c {
            // Replace invalid filename characters with underscores
            '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' => '_',
            // Replace other problematic characters
            '\n' | '\r' | '\t' => ' ',
            // Keep other characters as-is
            _ => c,
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim()
        .to_string()
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();

    let content = reqwest::get(args.url)
        .await?
        .bytes()
        .await?;

    let channel = Channel::read_from(&content[..])?;
    let podcast_title = channel.title();
    let podcast_dir = format!("{}/{}", &args.output, podcast_title);

    // Create output directory if it doesn't exist
    create_dir_all(&podcast_dir)?;

    println!("[{}] Found {} episodes", podcast_title, channel.items().len());

    let max_episodes = args.count.unwrap_or(channel.items().len());
    let semaphore = Arc::new(Semaphore::new(args.threads));
    let multi_progress = Arc::new(MultiProgress::new());
    let mut downloads = FuturesUnordered::new();
    let mut downloaded_episodes = 0;

    for (index, item) in channel.items().iter().enumerate() {
        if downloaded_episodes == max_episodes {
            break;
        }

        if let Some(enclosure) = item.enclosure() {
            let url = enclosure.url().to_string();
            
            // Get the original file extension from the URL
            let original_extension = Path::new(&url)
                .extension()
                .and_then(|ext| ext.to_str())
                .unwrap_or("mp3"); // Default to mp3 if no extension found
            
            // Get the episode title and sanitize it for use as filename
            let episode_title = item.title().unwrap_or("Unknown Episode");
            let sanitized_title = sanitize_filename(episode_title);
            
            // Get publication date for filename prefix
            let date_prefix = if let Some(pub_date) = item.pub_date() {
                // Parse the date and format as YYYY-MM-DD
                if let Ok(parsed_date) = chrono::DateTime::parse_from_rfc2822(pub_date) {
                    parsed_date.format("%Y-%m-%d - ").to_string()
                } else if let Ok(parsed_date) = chrono::NaiveDateTime::parse_from_str(pub_date, "%a, %d %b %Y %H:%M:%S %z") {
                    parsed_date.format("%Y-%m-%d - ").to_string()
                } else {
                    "".to_string() // Fallback for unparseable dates
                }
            } else {
                "".to_string() // Fallback for missing dates
            };
            
            // Create filename with date prefix, episode title and original extension
            let filename = format!("{}{}.{}", date_prefix, sanitized_title, original_extension);

            let output_dir = podcast_dir.clone();
            let semaphore_clone = semaphore.clone();
            let multi_progress_clone = multi_progress.clone();
            
            let download_future = download_episode(
                url,
                filename,
                output_dir,
                index,
                max_episodes,
                semaphore_clone,
                multi_progress_clone,
                item.clone(),
                args.metadata,
            );
            
            downloads.push(download_future);
            downloaded_episodes += 1;
        } else {
            println!("[{}/{}] No enclosure found for episode {}", index + 1, max_episodes, item.title().unwrap_or("Unknown title"));
        }
    }

    // Wait for all downloads to complete
    while let Some(result) = downloads.next().await {
        if let Err(e) = result {
            eprintln!("Download error: {}", e);
        }
    }

    Ok(())
}
