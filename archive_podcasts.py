#!/usr/bin/env python3

import argparse
import asyncio
import aiohttp
import aiofiles
import feedparser
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import urllib.parse
from tqdm import tqdm
import time


@dataclass
class EpisodeMetadata:
    """Metadata for a podcast episode"""
    title: str
    description: Optional[str]
    pub_date: Optional[str]
    duration: Optional[str]
    author: Optional[str]
    file_url: str
    guid: Optional[str]
    link: Optional[str]
    categories: List[str]


def sanitize_filename(title: str) -> str:
    """Sanitize a title for use as a filename"""
    # Replace invalid filename characters
    invalid_chars = r'[<>:"/\\|?*]'
    title = re.sub(invalid_chars, '_', title)
    
    # Replace newlines, tabs, etc. with spaces
    title = re.sub(r'[\n\r\t]', ' ', title)
    
    # Normalize whitespace
    title = ' '.join(title.split())
    
    return title.strip()


def parse_date(date_str: str) -> str:
    """Parse date string and return YYYY-MM-DD format"""
    if not date_str:
        return ""
    
    # Try different date formats
    date_formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]
    
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime('%Y-%m-%d - ')
        except ValueError:
            continue
    
    return ""


def get_file_extension(url: str) -> str:
    """Extract file extension from URL"""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    ext = os.path.splitext(path)[1]
    return ext[1:] if ext else "mp3"  # Default to mp3


def extract_metadata(entry) -> EpisodeMetadata:
    """Extract metadata from a feed entry"""
    # Get iTunes duration if available
    duration = None
    if hasattr(entry, 'itunes_duration'):
        duration = entry.itunes_duration
    
    # Get categories
    categories = []
    if hasattr(entry, 'tags'):
        categories = [tag.term for tag in entry.tags if hasattr(tag, 'term')]
    
    return EpisodeMetadata(
        title=entry.title or "Unknown Title",
        description=getattr(entry, 'summary', None),
        pub_date=getattr(entry, 'published', None),
        duration=duration,
        author=getattr(entry, 'author', None),
        file_url=entry.enclosures[0].href if entry.enclosures else "",
        guid=getattr(entry, 'id', None),
        link=getattr(entry, 'link', None),
        categories=categories
    )


async def save_metadata(metadata: EpisodeMetadata, output_dir: str, filename: str):
    """Save episode metadata as JSON file"""
    try:
        # Create metadata filename by replacing extension with .json
        base_name = os.path.splitext(filename)[0]
        metadata_filename = f"{base_name}.json"
        metadata_path = os.path.join(output_dir, metadata_filename)
        
        # Convert to dict and save as pretty JSON
        metadata_dict = asdict(metadata)
        async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(metadata_dict, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Warning: Failed to save metadata for {filename}: {e}")


async def download_episode(
    session: aiohttp.ClientSession,
    url: str,
    filename: str,
    output_dir: str,
    episode_index: int,
    total_episodes: int,
    semaphore: asyncio.Semaphore,
    save_metadata_flag: bool,
    metadata: Optional[EpisodeMetadata] = None
) -> bool:
    """Download a single episode with progress tracking"""
    async with semaphore:
        file_path = os.path.join(output_dir, filename)
        
        # Check if file already exists
        if os.path.exists(file_path):
            print(f"[{episode_index + 1}/{total_episodes}] Skipping (already exists): {filename}")
            return True
        
        try:
            # Create progress bar
            progress_bar = tqdm(
                total=0,
                desc=f"[{episode_index + 1}/{total_episodes}] {filename}",
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                leave=False
            )
            
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"Error downloading {filename}: HTTP {response.status}")
                    return False

                # Save metadata if enabled
                if save_metadata_flag and metadata:
                    await save_metadata(metadata, output_dir, filename)                   
                
                # Get file size for progress bar
                total_size = int(response.headers.get('content-length', 0))
                if total_size > 0:
                    progress_bar.total = total_size
                
                # Download file
                downloaded = 0
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        progress_bar.update(len(chunk))
                
                progress_bar.close()
                
                print(f"[{episode_index + 1}/{total_episodes}] Finished: {filename}")
                return True
                
        except Exception as e:
            print(f"Error downloading {filename}: {e}")
            return False


async def main():
    parser = argparse.ArgumentParser(
        description="Download podcast episodes with concurrent downloads and progress tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python archive_podcasts.py -u "https://example.com/feed.xml" -o "./downloads"
  python archive_podcasts.py -u "https://example.com/feed.xml" -o "./downloads" -t 5
  python archive_podcasts.py -u "https://example.com/feed.xml" -o "./downloads" -c 10 -m
        """
    )
    
    parser.add_argument('-u', '--url', required=True, help='RSS feed URL')
    parser.add_argument('-o', '--output', required=True, help='Output directory')
    parser.add_argument('-c', '--count', type=int, help='Number of episodes to download')
    parser.add_argument('-t', '--threads', type=int, default=1, help='Number of concurrent downloads (default: 1)')
    parser.add_argument('-m', '--metadata', action='store_true', help='Save episode metadata as JSON files')
    
    args = parser.parse_args()
    
    print("Podcast Archiver - Downloading episodes...")
    
    # Parse RSS feed
    print(f"Fetching RSS feed: {args.url}")
    feed = feedparser.parse(args.url)
    
    if not feed.entries:
        print("Error: No episodes found in RSS feed")
        return
    
    podcast_title = feed.feed.title if hasattr(feed.feed, 'title') else "Unknown Podcast"
    print(f"[{podcast_title}] Found {len(feed.entries)} episodes")
    
    # Create output directory
    podcast_dir = os.path.join(args.output, podcast_title)
    os.makedirs(podcast_dir, exist_ok=True)
    
    # Filter episodes with enclosures
    episodes_with_enclosures = []
    for entry in feed.entries:
        if entry.enclosures:
            episodes_with_enclosures.append(entry)
    
    if not episodes_with_enclosures:
        print("Error: No episodes with downloadable content found")
        return
    
    # Limit episodes if specified
    max_episodes = args.count if args.count else len(episodes_with_enclosures)
    episodes_to_download = episodes_with_enclosures[:max_episodes]
    
    print(f"Downloading {len(episodes_to_download)} episodes with {args.threads} threads")
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(args.threads)
    
    # Prepare download tasks
    tasks = []
    async with aiohttp.ClientSession() as session:
        for i, entry in enumerate(episodes_to_download):
            if i >= max_episodes:
                break
            
            enclosure = entry.enclosures[0]
            url = enclosure.href
            
            # Get file extension
            original_extension = get_file_extension(url)
            
            # Get episode title and sanitize
            episode_title = entry.title or "Unknown Episode"
            sanitized_title = sanitize_filename(episode_title)
            
            # Get publication date for filename prefix
            date_prefix = parse_date(getattr(entry, 'published', None))
            
            # Create filename
            filename = f"{date_prefix}{sanitized_title}.{original_extension}"
            
            # Extract metadata if needed
            metadata = None
            if args.metadata:
                metadata = extract_metadata(entry)
            
            # Create download task
            task = download_episode(
                session=session,
                url=url,
                filename=filename,
                output_dir=podcast_dir,
                episode_index=i,
                total_episodes=len(episodes_to_download),
                semaphore=semaphore,
                save_metadata_flag=args.metadata,
                metadata=metadata
            )
            tasks.append(task)
        
        # Execute all downloads concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful downloads
        successful = sum(1 for result in results if result is True)
        failed = len(results) - successful
        
        print(f"\nDownload complete!")
        print(f"Successfully downloaded: {successful}")
        if failed > 0:
            print(f"Failed downloads: {failed}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDownload interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1) 