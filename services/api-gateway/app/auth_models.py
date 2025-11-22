"""
Authentication Models and Utilities
Handles user authentication, JWT tokens, and password security
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import secrets

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
SECRET_KEY = secrets.token_urlsafe(32)  # In production, load from environment
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


# ============================================================================
# Request/Response Models
# ============================================================================

class UserCreate(BaseModel):
    """User registration request"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=100)

    @validator('username')
    def username_alphanumeric(cls, v):
        """Validate username is alphanumeric"""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username must be alphanumeric (can include _ and -)')
        return v

    @validator('password')
    def password_strength(cls, v):
        """Validate password meets minimum requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserLogin(BaseModel):
    """User login request"""
    username: str
    password: str


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
    """User model"""
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
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for secure storage"""
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
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode a JWT token

    Args:
        token: JWT token string

    Returns:
        TokenData if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")

        if username is None:
            return None

        return TokenData(username=username, user_id=user_id)

    except JWTError:
        return None


# ============================================================================
# In-Memory User Store (Replace with database in production)
# ============================================================================

# Temporary user storage - in production, use PostgreSQL/Redis
USERS_DB: dict[str, UserInDB] = {}


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

    # Create user ID
    user_id = f"user_{len(USERS_DB) + 1}"

    # Hash password
    hashed_password = get_password_hash(user_create.password)

    # Create user in DB
    user_in_db = UserInDB(
        user_id=user_id,
        username=user_create.username,
        email=user_create.email,
        full_name=user_create.full_name,
        hashed_password=hashed_password,
        is_active=True,
        is_admin=(len(USERS_DB) == 0),  # First user is admin
        created_at=datetime.utcnow(),
        last_login=None
    )

    USERS_DB[user_create.username] = user_in_db

    # Return user without password hash
    return User(**user_in_db.dict(exclude={'hashed_password'}))


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    """
    Authenticate a user with username and password

    Args:
        username: Username
        password: Plain text password

    Returns:
        User if authentication successful, None otherwise
    """
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    # Update last login
    user.last_login = datetime.utcnow()

    return user


def update_user_last_login(username: str):
    """Update user's last login timestamp"""
    user = get_user(username)
    if user:
        user.last_login = datetime.utcnow()
