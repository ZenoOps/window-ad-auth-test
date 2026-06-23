from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from dotenv import load_dotenv
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from litestar import Request, Response, get, post
from litestar.datastructures import Cookie
from litestar.exceptions import HTTPException
from litestar.response import Redirect
from litestar.status_codes import HTTP_401_UNAUTHORIZED, HTTP_503_SERVICE_UNAVAILABLE

from app.auth_store import AuthStore

logger = logging.getLogger(__name__)

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIRECTORY / ".env")

SESSION_COOKIE_NAME = "app_session"
AUTH_FLOW_COOKIE_NAME = "auth_flow"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class AuthSettings:
    endpoint: str
    application: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str
    kerberos_url: str
    token_url: str
    session_ttl_seconds: int
    auth_flow_ttl_seconds: int
    secure_cookies: bool
    database_path: Path

    @classmethod
    def from_environment(cls) -> AuthSettings:
        endpoint = os.getenv("CASDOOR_ENDPOINT", "http://127.0.0.1:8000").rstrip("/")
        database_value = os.getenv("AUTH_DATABASE_PATH", "").strip()
        database_path = (
            Path(database_value).expanduser()
            if database_value
            else BACKEND_DIRECTORY / "data" / "auth.db"
        )
        if not database_path.is_absolute():
            database_path = BACKEND_DIRECTORY / database_path

        return cls(
            endpoint=endpoint,
            application=os.getenv("CASDOOR_APPLICATION", "").strip(),
            client_id=os.getenv("CASDOOR_CLIENT_ID", "").strip(),
            client_secret=os.getenv("CASDOOR_CLIENT_SECRET", "").strip(),
            redirect_uri=os.getenv("CASDOOR_REDIRECT_URI", "").strip(),
            scope=os.getenv("CASDOOR_SCOPE", "openid profile email").strip(),
            kerberos_url=os.getenv("CASDOOR_KERBEROS_URL", "").strip()
            or f"{endpoint}/api/kerberos-login",
            token_url=os.getenv("CASDOOR_TOKEN_URL", "").strip()
            or f"{endpoint}/api/login/oauth/access_token",
            session_ttl_seconds=_env_int("SESSION_TTL_SECONDS", 8 * 60 * 60),
            auth_flow_ttl_seconds=_env_int("AUTH_FLOW_TTL_SECONDS", 5 * 60),
            secure_cookies=_env_bool("SESSION_COOKIE_SECURE", False),
            database_path=database_path.resolve(),
        )

    def require_browser_login_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("CASDOOR_APPLICATION", self.application),
                ("CASDOOR_CLIENT_ID", self.client_id),
                ("CASDOOR_CLIENT_SECRET", self.client_secret),
                ("CASDOOR_REDIRECT_URI", self.redirect_uri),
            )
            if not value
        ]
        if missing:
            raise CasdoorConfigurationError(f"Missing configuration: {', '.join(missing)}")


class CasdoorConfigurationError(RuntimeError):
    """Raised when Casdoor has not been configured correctly."""


class CasdoorAuthenticationError(RuntimeError):
    """Raised when a Casdoor authentication response cannot be trusted."""


settings = AuthSettings.from_environment()
auth_store = AuthStore(settings.database_path)


class CasdoorTokenVerifier:
    """Validate Casdoor JWTs using its OIDC discovery document and JWKS."""

    def __init__(self) -> None:
        default_discovery_url = (
            f"{settings.endpoint}/.well-known/{settings.application}/openid-configuration"
            if settings.application
            else f"{settings.endpoint}/.well-known/openid-configuration"
        )

        self.discovery_url = (
            os.getenv("CASDOOR_DISCOVERY_URL", "").strip() or default_discovery_url
        )
        self.client_id = settings.client_id
        self.audience = os.getenv("CASDOOR_AUDIENCE", "").strip() or self.client_id
        self.allowed_algorithms = [
            algorithm.strip()
            for algorithm in os.getenv("CASDOOR_ALLOWED_ALGORITHMS", "RS256").split(",")
            if algorithm.strip()
        ]
        self._issuer: str | None = None
        self._jwks_client: PyJWKClient | None = None
        self._configuration_lock = Lock()

    def verify(self, token: str) -> dict[str, Any]:
        if not self.client_id:
            raise CasdoorConfigurationError("CASDOOR_CLIENT_ID is not configured")
        if not self.audience:
            raise CasdoorConfigurationError("CASDOOR_AUDIENCE is not configured")
        if not self.allowed_algorithms:
            raise CasdoorConfigurationError("CASDOOR_ALLOWED_ALGORITHMS is empty")

        issuer, jwks_client = self._get_oidc_configuration()

        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=self.allowed_algorithms,
                audience=self.audience,
                issuer=issuer,
                leeway=30,
                options={"require": ["exp", "sub"]},
            )
        except PyJWTError as exc:
            logger.warning("Casdoor rejected a token: %s", exc)
            raise CasdoorAuthenticationError("Invalid or expired Casdoor token") from exc

        return dict(claims)

    def _get_oidc_configuration(self) -> tuple[str, PyJWKClient]:
        if self._issuer and self._jwks_client:
            return self._issuer, self._jwks_client

        with self._configuration_lock:
            if self._issuer and self._jwks_client:
                return self._issuer, self._jwks_client

            try:
                response = httpx.get(self.discovery_url, timeout=5.0, follow_redirects=True)
                response.raise_for_status()
                discovery = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.exception("Unable to load Casdoor discovery document")
                raise CasdoorConfigurationError(
                    "Casdoor discovery endpoint is unavailable"
                ) from exc

            issuer = discovery.get("issuer")
            jwks_uri = discovery.get("jwks_uri")
            if not isinstance(issuer, str) or not issuer:
                raise CasdoorConfigurationError("Casdoor discovery document has no issuer")
            if not isinstance(jwks_uri, str) or not jwks_uri:
                raise CasdoorConfigurationError("Casdoor discovery document has no jwks_uri")

            self._issuer = issuer
            self._jwks_client = PyJWKClient(jwks_uri)
            return self._issuer, self._jwks_client


casdoor_token_verifier = CasdoorTokenVerifier()


@dataclass
class LocalLoginCredentials:
    username: str
    password: str


def _cookie(name: str, value: str, max_age: int) -> Cookie:
    return Cookie(
        key=name,
        value=value,
        max_age=max_age,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


def _delete_cookie(name: str) -> Cookie:
    return Cookie(
        key=name,
        value="",
        max_age=0,
        expires=0,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def _authenticate_bearer(request: Request) -> dict[str, Any]:
    try:
        return casdoor_token_verifier.verify(_bearer_token(request))
    except CasdoorConfigurationError as exc:
        raise HTTPException(status_code=HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except CasdoorAuthenticationError as exc:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _public_user(claims: dict[str, Any]) -> dict[str, Any]:
    visible_claims = (
        "sub",
        "name",
        "preferred_username",
        "displayName",
        "email",
        "email_verified",
        "owner",
        "organization",
        "application",
        "groups",
        "roles",
        "iss",
        "aud",
        "exp",
        "auth_source",
    )
    return {name: claims[name] for name in visible_claims if name in claims}


def _create_session_response(user: dict[str, Any], source: str) -> Response[dict[str, Any]]:
    session_token = secrets.token_urlsafe(48)
    public_user = _public_user({**user, "auth_source": source})
    auth_store.create_session(
        session_token,
        public_user,
        source,
        settings.session_ttl_seconds,
    )
    return Response(
        {"authenticated": True, "user": public_user},
        cookies=[_cookie(SESSION_COOKIE_NAME, session_token, settings.session_ttl_seconds)],
    )


def _exchange_authorization_code(code: str) -> dict[str, Any]:
    settings.require_browser_login_configuration()
    try:
        response = httpx.post(
            settings.token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "code": code,
                "redirect_uri": settings.redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        token_response = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Casdoor authorization-code exchange failed")
        raise CasdoorAuthenticationError("Casdoor token exchange failed") from exc

    if not isinstance(token_response, dict):
        raise CasdoorAuthenticationError("Casdoor returned an invalid token response")
    if token_response.get("error"):
        description = token_response.get("error_description") or token_response["error"]
        raise CasdoorAuthenticationError(str(description))

    identity_token = token_response.get("id_token") or token_response.get("access_token")
    if not isinstance(identity_token, str) or not identity_token:
        raise CasdoorAuthenticationError("Casdoor token response contained no identity token")
    return casdoor_token_verifier.verify(identity_token)


@get("/api/auth/kerberos/start", sync_to_thread=True)
def start_kerberos_login() -> Response[dict[str, Any]]:
    """Create a browser-bound login transaction and return the Casdoor Kerberos API URL."""
    try:
        settings.require_browser_login_configuration()
    except CasdoorConfigurationError as exc:
        raise HTTPException(status_code=HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    state = secrets.token_urlsafe(32)
    browser_token = secrets.token_urlsafe(32)
    auth_store.create_auth_flow(state, browser_token, settings.auth_flow_ttl_seconds)
    kerberos_parameters = {
        "application": settings.application,
        "clientId": settings.client_id,
        "responseType": "code",
        "redirectUri": settings.redirect_uri,
        "scope": settings.scope,
        "state": state,
    }
    kerberos_url = f"{settings.kerberos_url}?{urlencode(kerberos_parameters)}"

    return Response(
        {"kerberos_url": kerberos_url, "state": state},
        cookies=[_cookie(AUTH_FLOW_COOKIE_NAME, browser_token, settings.auth_flow_ttl_seconds)],
        headers={"Cache-Control": "no-store"},
    )


@get("/api/auth/callback", sync_to_thread=True)
def casdoor_callback(request: Request) -> Redirect:
    """Validate the login transaction, exchange the code, and create an app session."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    browser_token = request.cookies.get(AUTH_FLOW_COOKIE_NAME, "")
    if error or not code or not state or not browser_token:
        return Redirect(
            path="/login",
            query_params={"reason": error or "kerberos_failed"},
            cookies=[_delete_cookie(AUTH_FLOW_COOKIE_NAME)],
        )

    if not auth_store.consume_auth_flow(state, browser_token):
        return Redirect(
            path="/login",
            query_params={"reason": "invalid_state"},
            cookies=[_delete_cookie(AUTH_FLOW_COOKIE_NAME)],
        )

    try:
        claims = _exchange_authorization_code(code)
    except (CasdoorAuthenticationError, CasdoorConfigurationError) as exc:
        logger.warning("Casdoor callback failed: %s", exc)
        return Redirect(
            path="/login",
            query_params={"reason": "token_exchange_failed"},
            cookies=[_delete_cookie(AUTH_FLOW_COOKIE_NAME)],
        )

    session_token = secrets.token_urlsafe(48)
    public_user = _public_user({**claims, "auth_source": "kerberos"})
    auth_store.create_session(
        session_token,
        public_user,
        "kerberos",
        settings.session_ttl_seconds,
    )
    return Redirect(
        path="/",
        cookies=[
            _cookie(SESSION_COOKIE_NAME, session_token, settings.session_ttl_seconds),
            _delete_cookie(AUTH_FLOW_COOKIE_NAME),
        ],
    )


@post("/api/auth/local-login", sync_to_thread=True)
def local_login(data: LocalLoginCredentials) -> Response[dict[str, Any]]:
    user = auth_store.authenticate_local_user(data.username, data.password)
    if user is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return _create_session_response(user, "local")


@post("/api/auth/logout", sync_to_thread=True)
def logout(request: Request) -> Response[dict[str, bool]]:
    auth_store.delete_session(request.cookies.get(SESSION_COOKIE_NAME, ""))
    return Response(
        {"authenticated": False},
        cookies=[
            _delete_cookie(SESSION_COOKIE_NAME),
            _delete_cookie(AUTH_FLOW_COOKIE_NAME),
        ],
    )


@get("/api/auth/verify", sync_to_thread=True)
def verify_casdoor_token(request: Request) -> dict[str, Any]:
    """Verify a Casdoor bearer token and return non-sensitive identity claims."""
    claims = _authenticate_bearer(request)
    return {"authenticated": True, "user": _public_user(claims)}


@get("/api/auth/me", sync_to_thread=True)
def current_user(request: Request) -> dict[str, Any]:
    """Return the user attached to the opaque application session cookie."""
    user = auth_store.get_session(request.cookies.get(SESSION_COOKIE_NAME, ""))
    if user is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return {"authenticated": True, "user": user}
