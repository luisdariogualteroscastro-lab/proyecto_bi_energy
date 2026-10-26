import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from src.config import MASTER_KEY

def get_aesgcm_key() -> bytes:
    # Derivar una llave de 32 bytes desde MASTER_KEY
    return hashlib.sha256(MASTER_KEY.encode('utf-8')).digest()

def encrypt_pii(plaintext: str) -> str:
    if not plaintext:
        return ""
    aesgcm = AESGCM(get_aesgcm_key())
    nonce = os_urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')

def decrypt_pii(encoded_ciphertext: str) -> str:
    if not encoded_ciphertext:
        return ""
    try:
        raw = base64.b64decode(encoded_ciphertext.encode('utf-8'))
        nonce = raw[:12]
        ciphertext = raw[12:]
        aesgcm = AESGCM(get_aesgcm_key())
        return aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
    except Exception:
        return "[DECRYPTION_ERROR]"

def hash_value(val: str) -> str:
    if not val:
        return ""
    return hashlib.sha256(val.strip().encode('utf-8')).hexdigest()

def mask_pii_text(text: str) -> str:
    if not text:
        return ""
    import re
    # Enmascarar emails
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '***@***.com', text)
    # Enmascarar celulares (10 dígitos empezando por 3)
    text = re.sub(r'\b3\d{9}\b', '3********', text)
    # Enmascarar cédulas / CC
    text = re.sub(r'\b(CC|C\.C\.|c\.c\.)\s*\d+\b', 'CC ********', text, flags=re.IGNORECASE)
    return text

def os_urandom(n: int) -> bytes:
    import os
    return os.urandom(n)
