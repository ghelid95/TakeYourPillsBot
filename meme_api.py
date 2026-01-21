import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MEME_API_URL = 'https://meme-api.com/gimme'


async def fetch_random_meme() -> Optional[dict]:
    """
    Fetch a random meme from Reddit via Meme API (D3vd).

    This API is free and requires no API key.
    https://github.com/D3vd/Meme_Api

    Returns:
        dict with 'url' and 'title' keys, or None if request fails.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MEME_API_URL, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'url': data.get('url'),
                        'title': data.get('title', '')
                    }
                else:
                    logger.error(f"Meme API returned status {response.status}")
                    return None
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching meme: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching meme: {e}")
        return None


def get_fallback_message() -> str:
    """Return a fallback message when meme cannot be fetched."""
    return "Time to take your pills! Stay healthy!"
