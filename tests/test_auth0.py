"""
Tests de la validación de tokens Auth0 (RS256 contra JWKS) usando un par de
llaves RSA generado localmente — sin depender de un tenant real.
"""
import time
import pytest
from jose import jwt
from jose.backends.cryptography_backend import CryptographyRSAKey
from cryptography.hazmat.primitives.asymmetric import rsa

import app.core.auth0 as auth0_mod
from app.core.auth0 import validar_token, Auth0Error


@pytest.fixture()
def tenant_falso(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jose_key = CryptographyRSAKey(private_key, algorithm="RS256")
    public_jwk = jose_key.public_key().to_dict()
    public_jwk["kid"] = "test-key-1"
    public_jwk["use"] = "sig"

    monkeypatch.setattr(auth0_mod.settings, "AUTH0_DOMAIN", "tenant-test.auth0.com")
    monkeypatch.setattr(auth0_mod.settings, "AUTH0_AUDIENCE", "https://api.sirebot.com")
    monkeypatch.setattr(auth0_mod, "_obtener_jwks", lambda: {"keys": [public_jwk]})

    def emitir(sub="auth0|abc123", audience="https://api.sirebot.com",
               issuer="https://tenant-test.auth0.com/", exp_delta=3600, kid="test-key-1"):
        claims = {
            "sub": sub,
            "aud": audience,
            "iss": issuer,
            "exp": int(time.time()) + exp_delta,
            "iat": int(time.time()),
        }
        return jwt.encode(claims, jose_key.to_dict() | {"kid": kid},
                          algorithm="RS256", headers={"kid": kid})

    return emitir


def test_token_valido_devuelve_claims(tenant_falso):
    token = tenant_falso(sub="auth0|user42")
    claims = validar_token(token)
    assert claims["sub"] == "auth0|user42"


def test_token_expirado_se_rechaza(tenant_falso):
    token = tenant_falso(exp_delta=-60)
    with pytest.raises(Auth0Error):
        validar_token(token)


def test_audience_equivocada_se_rechaza(tenant_falso):
    token = tenant_falso(audience="https://otra-api.com")
    with pytest.raises(Auth0Error):
        validar_token(token)


def test_issuer_equivocado_se_rechaza(tenant_falso):
    token = tenant_falso(issuer="https://tenant-malicioso.auth0.com/")
    with pytest.raises(Auth0Error):
        validar_token(token)


def test_token_basura_se_rechaza(tenant_falso):
    with pytest.raises(Auth0Error):
        validar_token("no.es.un.token")
