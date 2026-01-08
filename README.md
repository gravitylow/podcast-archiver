# Podcast Archiver

Fair warning: I didn't write this, Cursor did.
I wanted a tool to download the entire back catalog of a podcast for offline listening,
and I wanted to take vibe coding for a spin. This project is the result.

## Usage

```bash
# Download all episodes from a podcast, one by one
python archive_podcasts.py -u "https://example.com/podcast-feed.xml" -d "./downloads"

# Download only the 10 newest episodes
python archive_podcasts.py -u "https://example.com/podcast-feed.xml" -d "./downloads" -c 10

# Download all episodes from multiple podcasts with 5 threads
python archive_podcasts.py -u "https://example.com/podcast-feed.xml" -u "https://coolpodcast.org/feed.xml" -d "./downloads" -t 5

# Download URLs from a file (one URL per line)
python archive_podcasts.py -f "podcasts.txt" -d "./downloads"

# Run in continuous loop, checking for new episodes every hour (3600 seconds)
python archive_podcasts.py -u "https://example.com/podcast-feed.xml" -d "./downloads" -s 3600
```

### Docker

#### Running with Docker

```bash
docker run --rm -v /path/to/downloads:/app/downloads podcast-archiver -u "https://example.com/podcast-feed.xml" -d "/app/downloads"
```

#### Building the Image

```bash
# Build the Docker image
docker build -t podcast-archiver .
```

### Command Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--url` | `-u` | RSS feed URL | - |
| `--urls-file` | `-f` | File containing RSS feed URLs (one per line) | - |
| `--directory` | `-d` | Output directory (required) | - |
| `--count` | `-c` | Number of episodes to download | All episodes |
| `--offset` | `-o` | Number of episodes to skip | 0 |
| `--threads` | `-t` | Number of concurrent downloads | 1 |
| `--metadata` | `-m` | Save episode metadata as JSON files | false |
| `--sleep-seconds` | `-s` | Run in continuous loop, sleeping for specified seconds between iterations | - |
