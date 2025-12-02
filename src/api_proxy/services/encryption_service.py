"""
Encryption service for API Keys

Uses Fernet symmetric encryption to encrypt/decrypt API keys
"""
import secrets
import string
from cryptography.fernet import Fernet

from ..config import get_config


class EncryptionService:
    """Service for encrypting and decrypting API keys"""

    def __init__(self):
        config = get_config()
        encryption_key = config.get("security.encryption_key", "")

        # If no key configured, generate one (for development only)
        if not encryption_key or encryption_key == "your-encryption-key-change-in-production-use-fernet-generate-key":
            encryption_key = Fernet.generate_key().decode()
            print(f"⚠️  Generated temporary encryption key: {encryption_key}")
            print("⚠️  Please set a permanent key in config.yaml for production!")

        self.fernet = Fernet(encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted string (base64 encoded)
        """
        encrypted_bytes = self.fernet.encrypt(plaintext.encode())
        return encrypted_bytes.decode()

    def decrypt(self, encrypted: str) -> str:
        """Decrypt a string

        Args:
            encrypted: Encrypted string (base64 encoded)

        Returns:
            Decrypted plaintext string

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails
        """
        decrypted_bytes = self.fernet.decrypt(encrypted.encode())
        return decrypted_bytes.decode()

    @staticmethod
    def generate_api_key(prefix: str = "ami", length: int = 20) -> str:
        """Generate a random API key

        Args:
            prefix: Prefix for the API key (default: "ami")
            length: Length of random part (default: 20)

        Returns:
            API key in format: prefix_xxxxxxxxxxxxxx

        Example:
            ami_abc123def456ghi789
        """
        # Use alphanumeric characters (excluding confusing chars like 0, O, l, 1)
        alphabet = string.ascii_lowercase + string.digits
        alphabet = alphabet.replace('0', '').replace('o', '').replace('l', '').replace('1', '')

        random_part = ''.join(secrets.choice(alphabet) for _ in range(length))
        return f"{prefix}_{random_part}"

    @staticmethod
    def generate_encryption_key() -> str:
        """Generate a new Fernet encryption key

        This should be called once during setup and stored securely.

        Returns:
            Base64-encoded Fernet key

        Example:
            >>> key = EncryptionService.generate_encryption_key()
            >>> print(key)
            'abcdefgh...'  # 44 characters
        """
        return Fernet.generate_key().decode()


# Singleton instance
_encryption_service: EncryptionService = None


def get_encryption_service() -> EncryptionService:
    """Get encryption service instance (singleton)"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
