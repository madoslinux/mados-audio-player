"""
Metadata Fetcher Module
=======================

Handles fetching metadata and album art from iTunes API.
Returns metadata dict with title, artist, album, and image_data.
"""

import urllib.request
import urllib.parse
import json


class MetadataFetcher:
    """Fetches metadata from iTunes API."""
    
    def __init__(self):
        self.user_agent = "Mozilla/5.0"
    
    def search(self, artist, title):
        """Search iTunes for metadata.
        
        Args:
            artist: Artist name
            title: Song title
            
        Returns:
            dict with keys: title, artist, album, image_data, image_url
            or None if not found
        """
        if not (artist or title):
            return None
        
        query = f"{artist} {title}".strip()
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&limit=1&entity=song"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                
                if data.get('results') and data['results'][0].get('artworkUrl100'):
                    result = data['results'][0]
                    
                    # Get high-res image
                    artwork_url = result['artworkUrl100'].replace('100x100', '600x600')
                    
                    # Download image
                    img_req = urllib.request.Request(artwork_url, headers={'User-Agent': self.user_agent})
                    with urllib.request.urlopen(img_req, timeout=5) as img_response:
                        image_data = img_response.read()
                    
                    return {
                        "title": result.get("trackName", ""),
                        "artist": result.get("artistName", ""),
                        "album": result.get("collectionName", ""),
                        "image_data": image_data,
                        "image_url": artwork_url,
                    }
        except Exception:
            pass
        
        return None


def test_fetcher():
    """Test the metadata fetcher."""
    fetcher = MetadataFetcher()
    
    # Test with known song
    result = fetcher.search("Akino Arai", "VOICES")
    
    if result:
        print("SUCCESS: Found metadata")
        print(f"  Title: {result['title']}")
        print(f"  Artist: {result['artist']}")
        print(f"  Album: {result['album']}")
        print(f"  Image size: {len(result['image_data'])} bytes")
    else:
        print("FAILED: No results found")


if __name__ == "__main__":
    test_fetcher()