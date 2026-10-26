import pytest
from src.security.crypto import encrypt_pii, decrypt_pii, mask_pii_text, hash_value

def test_encryption_roundtrip():
    original = "867.446.522-3"
    encrypted = encrypt_pii(original)
    decrypted = decrypt_pii(encrypted)
    assert decrypted == original
    assert encrypted != original

def test_pii_masking():
    obs = "Contacto alterno: lucia.nino@comercializadora.com.co tel 3284700087 CC 26290387"
    masked = mask_pii_text(obs)
    assert "lucia.nino" not in masked
    assert "3284700087" not in masked
    assert "***@***.com" in masked
    assert "3********" in masked

def test_hash_value():
    nit = "867.446.522-3"
    h1 = hash_value(nit)
    h2 = hash_value(nit)
    assert h1 == h2
    assert len(h1) == 64
