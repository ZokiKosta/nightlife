import hashlib
import secrets
import re
from datetime import datetime


def hash_password(password: str) -> str:
    """Simple SHA-256 hash with salt. Use bcrypt in production."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against stored hash."""
    try:
        salt, hashed = stored_hash.split(':', 1)
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == hashed
    except Exception:
        return False


def format_price(price_str: str) -> str:
    """Normalize price string."""
    if not price_str:
        return "TBA"
    return price_str.strip()


def parse_instagram_username(url_or_username: str) -> str:
    """Extract username from Instagram URL or return as-is."""
    match = re.search(r'instagram\.com/([^/?#]+)', url_or_username)
    if match:
        return match.group(1).strip('/')
    return url_or_username.lstrip('@').strip()


def truncate(text: str, length: int = 150) -> str:
    """Truncate text to given length."""
    if not text:
        return ""
    return text[:length] + "..." if len(text) > length else text


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)