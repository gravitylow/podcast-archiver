# Podcast Archiver

Fair warning: I didn't write this, Cursor did.
I wanted a tool to download the entire back catalog of a podcast for offline listening,
and I wanted to take vibe coding for a spin. This project is the result.

Includes both python and rust implementations

## Usage

### Rust

```bash
# Download all episodes from a podcast, one by one
cargo run -- -u "https://example.com/podcast-feed.xml" -o "./downloads"

# Download all episodes with 5 threads
cargo run -- -u "https://example.com/podcast-feed.xml" -o "./downloads" -t 5

# Download only the 10 newest episodes
cargo run -- -u "https://example.com/podcast-feed.xml" -o "./downloads" -c 10
```

### Python

```bash
# Download all episodes from a podcast, one by one
python podcast_downloader.py -u "https://example.com/podcast-feed.xml" -o "./downloads"

# Download all episodes with 5 threads
python podcast_downloader.py -u "https://example.com/podcast-feed.xml" -o "./downloads" -t 5

# Download only the 10 newest episodes
python podcast_downloader.py -u "https://example.com/podcast-feed.xml" -o "./downloads" -c 10
```

### Command Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--url` | `-u` | RSS feed URL (required) | - |
| `--output` | `-o` | Output directory (required) | - |
| `--count` | `-c` | Number of episodes to download | All episodes |
| `--threads` | `-t` | Number of concurrent downloads | 1 |
| `--metadata` | `-m` | Save episode metadata as JSON files | false |
