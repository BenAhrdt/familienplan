from app.core.security import hash_password, new_token, token_hash, verify_password


def test_password_hash_is_argon2_and_verifies():
    digest = hash_password("ein-sehr-langes-Testpasswort")
    assert digest.startswith("$argon2id$")
    assert verify_password("ein-sehr-langes-Testpasswort", digest)
    assert not verify_password("falsch", digest)


def test_tokens_are_random_and_only_digest_is_storable():
    first, second = new_token(), new_token()
    assert first != second
    assert len(token_hash(first)) == 64
    assert first not in token_hash(first)

