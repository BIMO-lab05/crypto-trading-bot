"""
Authentication Models and Utilities
Handles user authentication, JWT tokens, and password security

SECURITY FIXES (2025-12-12):
- JWT secret MUST be loaded from environment variable in production
- Production startup fails if JWT_SECRET_KEY is not properly configured
- Password hashing rounds increased to 14
- Added security warnings and validation for development mode
"""

import os
import sys
import logging
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# Environment Detection
# ============================================================================

# Determine current environment (development, staging, production)
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"
IS_STAGING = ENVIRONMENT == "staging"
IS_DEVELOPMENT = ENVIRONMENT == "development"

# Password hashing context with bcrypt_sha256 + 14 rounds.
# - bcrypt_sha256 SHA-256-prehashes input so passwords longer than the bcrypt
#   72-byte limit are not silently truncated (bcrypt 5.0 raises ValueError).
# - 14 rounds gives strong security while staying responsive.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256"],
    deprecated="auto",
    bcrypt_sha256__rounds=14,
)

# ============================================================================
# JWT Configuration - SECURITY HARDENED
# ============================================================================

# Development-only fallback secret (NEVER used in production)
_DEV_ONLY_SECRET = "development-only-secret-not-for-production-use"


def _validate_jwt_secret() -> str:
    """
    Validate and return JWT secret key with environment-appropriate security.

    Security requirements:
    - Production: MUST have JWT_SECRET_KEY set, minimum 32 characters
    - Staging: MUST have JWT_SECRET_KEY set, minimum 32 characters
    - Development: Warns if using default, allows startup for local dev

    Returns:
        str: Validated JWT secret key

    Raises:
        SystemExit: If production/staging environment lacks proper secret
    """
    secret_key = os.environ.get("JWT_SECRET_KEY")

    # Production and Staging require properly configured secrets
    if IS_PRODUCTION or IS_STAGING:
        if not secret_key:
            logger.critical(
                f"SECURITY FAILURE: JWT_SECRET_KEY environment variable is required "
                f"in {ENVIRONMENT} environment. Application cannot start."
            )
            logger.critical("Generate a secure key with: openssl rand -hex 64")
            sys.exit(1)

        # Validate minimum secret length (256 bits = 64 hex chars or 32 bytes)
        if len(secret_key) < 32:
            logger.critical(
                f"SECURITY FAILURE: JWT_SECRET_KEY must be at least 32 characters "
                f"in {ENVIRONMENT} environment. Current length: {len(secret_key)}"
            )
            logger.critical("Generate a secure key with: openssl rand -hex 64")
            sys.exit(1)

        # Warn about potentially weak secrets
        weak_patterns = ["test", "dev", "secret", "password", "example", "change"]
        if any(pattern in secret_key.lower() for pattern in weak_patterns):
            logger.warning(
                "SECURITY WARNING: JWT_SECRET_KEY appears to contain weak patterns. "
                "Ensure this is a cryptographically random value."
            )

        logger.info(f"JWT secret key validated for {ENVIRONMENT} environment")
        return secret_key

    # Development environment - allow fallback with warnings
    if secret_key:
        if len(secret_key) < 32:
            logger.warning(
                "SECURITY WARNING: JWT_SECRET_KEY should be at least 32 characters. "
                "Generate with: openssl rand -hex 64"
            )
        return secret_key

    # Development fallback
    logger.warning(
        "=" * 70 + "\n"
        "SECURITY WARNING: Using default development JWT secret!\n"
        "This is ONLY acceptable for local development.\n"
        "Set JWT_SECRET_KEY environment variable for any non-local deployment.\n"
        "Generate with: openssl rand -hex 64\n" + "=" * 70
    )
    return _DEV_ONLY_SECRET


# Initialize JWT secret with validation
SECRET_KEY = _validate_jwt_secret()

# JWT Algorithm - HS256 for symmetric signing
# Consider RS256 for asymmetric signing in multi-service architectures
ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# Validate algorithm is supported and secure
ALLOWED_ALGORITHMS = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
if ALGORITHM not in ALLOWED_ALGORITHMS:
    logger.warning(f"Unknown JWT algorithm '{ALGORITHM}', defaulting to HS256")
    ALGORITHM = "HS256"

# Token expiration - reduced default for security (30 minutes)
# Use refresh tokens for longer sessions
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Validate token expiration is within reasonable bounds
if ACCESS_TOKEN_EXPIRE_MINUTES > 1440:  # 24 hours
    logger.warning(
        f"ACCESS_TOKEN_EXPIRE_MINUTES is set to {ACCESS_TOKEN_EXPIRE_MINUTES} "
        "which exceeds recommended maximum of 1440 (24 hours)"
    )

if IS_PRODUCTION and ACCESS_TOKEN_EXPIRE_MINUTES > 60:
    logger.warning(
        f"Production tokens expire in {ACCESS_TOKEN_EXPIRE_MINUTES} minutes. "
        "Consider reducing to 30-60 minutes and using refresh tokens."
    )


# ============================================================================
# Request/Response Models
# ============================================================================


class UserCreate(BaseModel):
    """User registration request with strong validation"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=100)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v):
        """Validate username is alphanumeric (with _ and -)"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must be alphanumeric (can include _ and -)")
        # Prevent common attack patterns and reserved names
        forbidden = [
            "admin",
            "root",
            "system",
            "null",
            "undefined",
            "administrator",
            "superuser",
            "api",
            "www",
            "mail",
            "support",
            "security",
        ]
        if v.lower() in forbidden:
            raise ValueError(f'Username "{v}" is reserved')
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        """Validate password meets minimum security requirements"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        # Check for common weak patterns
        common_passwords = [
            "password",
            "12345678",
            "qwerty",
            "letmein",
            "welcome",
            "monkey",
            "dragon",
            "master",
            "abc123",
            "password1",
        ]
        if v.lower() in common_passwords:
            raise ValueError("Password is too common")
        return v


class UserLogin(BaseModel):
    """User login request"""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class Token(BaseModel):
    """JWT token response"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds


class TokenData(BaseModel):
    """JWT token payload data"""

    username: Optional[str] = None
    user_id: Optional[str] = None


class User(BaseModel):
    """User model (public-facing, excludes sensitive data)"""

    user_id: str
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime
    last_login: Optional[datetime] = None


class UserInDB(User):
    """User model with hashed password (for database storage)"""

    hashed_password: str


# ============================================================================
# Password Utilities
# ============================================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash

    Uses bcrypt with timing-safe comparison to prevent timing attacks
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification error: {type(e).__name__}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password for secure storage

    Uses bcrypt with 14 rounds (configurable via CryptContext)
    """
    return pwd_context.hash(password)


# ============================================================================
# JWT Token Utilities
# ============================================================================


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token

    Args:
        data: Dictionary containing user data to encode in token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string

    Security notes:
    - Token includes 'iat' (issued at) for token age verification
    - Uses configured SECRET_KEY from environment
    - Default expiration is ACCESS_TOKEN_EXPIRE_MINUTES
    - Includes 'env' claim for environment verification
    """
    to_encode = data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Add standard JWT claims
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.utcnow(),  # Issued at time
            "type": "access",  # Token type for validation
            "env": ENVIRONMENT,  # Environment for cross-env validation
        }
    )

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode a JWT token

    Args:
        token: JWT token string

    Returns:
        TokenData if valid, None if invalid

    Security notes:
    - Validates signature using SECRET_KEY
    - Automatically checks expiration
    - Validates token environment matches current environment
    - Returns None on any error (no error details exposed)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Validate token type
        token_type = payload.get("type")
        if token_type != "access":
            logger.warning("Token type mismatch")
            return None

        # Validate environment in production/staging
        if IS_PRODUCTION or IS_STAGING:
            token_env = payload.get("env")
            if token_env and token_env != ENVIRONMENT:
                logger.warning(
                    f"Token environment mismatch: token={token_env}, current={ENVIRONMENT}"
                )
                return None

        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")

        if username is None:
            return None

        return TokenData(username=username, user_id=user_id)

    except JWTError as e:
        logger.debug(f"JWT validation failed: {type(e).__name__}")
        return None


# ============================================================================
# In-Memory User Store
# WARNING: Replace with database in production!
# ============================================================================

# Temporary user storage - in production, use PostgreSQL/Redis
# This implementation is for development/testing only
USERS_DB: dict[str, UserInDB] = {}

# Log warning about in-memory storage
if IS_PRODUCTION:
    logger.error(
        "CRITICAL: Using in-memory user storage in PRODUCTION! "
        "This MUST be replaced with a database backend!"
    )
elif IS_STAGING:
    logger.warning(
        "WARNING: Using in-memory user storage in STAGING. "
        "Implement database backend before production deployment!"
    )
else:
    logger.info(
        "DEVELOPMENT MODE: Using in-memory user storage. "
        "This is acceptable for local development only."
    )


def get_user(username: str) -> Optional[UserInDB]:
    """Get user by username"""
    return USERS_DB.get(username)


def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Get user by email"""
    for user in USERS_DB.values():
        if user.email == email:
            return user
    return None


def create_user(user_create: UserCreate) -> User:
    """
    Create a new user

    Args:
        user_create: User registration data

    Returns:
        Created user (without password hash)

    Raises:
        ValueError: If username or email already exists
    """
    # Check if username exists
    if get_user(user_create.username):
        raise ValueError("Username already registered")

    # Check if email exists
    if get_user_by_email(user_create.email):
        raise ValueError("Email already registered")

    # Create user ID using secrets for uniqueness
    import secrets as sec

    user_id = f"user_{sec.token_hex(8)}"

    # Hash password
    hashed_password = get_password_hash(user_create.password)

    # Determine admin status
    # SECURITY: First user becomes admin in dev only - disabled for production
    is_first_user = len(USERS_DB) == 0
    grant_admin = is_first_user and IS_DEVELOPMENT

    if is_first_user and IS_DEVELOPMENT:
        logger.info("First user in development - granting admin privileges")
    elif is_first_user:
        logger.info(
            f"First user in {ENVIRONMENT} - admin privileges NOT auto-granted. "
            "Use proper admin provisioning process."
        )

    # Create user in DB
    user_in_db = UserInDB(
        user_id=user_id,
        username=user_create.username,
        email=user_create.email,
        full_name=user_create.full_name,
        hashed_password=hashed_password,
        is_active=True,
        is_admin=grant_admin,
        created_at=datetime.utcnow(),
        last_login=None,
    )

    USERS_DB[user_create.username] = user_in_db

    # Log user creation (without sensitive data)
    logger.info(f"User created: {user_create.username} (admin={grant_admin})")

    # Return user without password hash
    return User(**user_in_db.dict(exclude={"hashed_password"}))


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    """
    Authenticate a user with username and password

    Args:
        username: Username
        password: Plain text password

    Returns:
        User if authentication successful, None otherwise

    Security notes:
    - Uses constant-time comparison for passwords
    - Logs failed attempts (without password details)
    """
    user = get_user(username)
    if not user:
        # Log failed attempt without revealing if username exists
        logger.warning(f"Authentication failed for username: {username[:3]}***")
        # Still perform password check to prevent timing attacks
        verify_password(password, get_password_hash("dummy"))
        return None

    if not verify_password(password, user.hashed_password):
        logger.warning(
            f"Authentication failed (bad password) for user: {username[:3]}***"
        )
        return None

    if not user.is_active:
        logger.warning(f"Authentication failed (inactive) for user: {username[:3]}***")
        return None

    # Update last login
    user.last_login = datetime.utcnow()
    logger.info(f"User authenticated: {username[:3]}***")

    return user


def update_user_last_login(username: str):
    """Update user's last login timestamp"""
    user = get_user(username)
    if user:
        user.last_login = datetime.utcnow()
