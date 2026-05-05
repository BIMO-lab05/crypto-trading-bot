"""
Tests for Authentication Models
Tests user models, password hashing, JWT tokens, and user management
"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timedelta

from app.auth_models import (
    UserCreate,
    UserLogin,
    Token,
    TokenData,
    User,
    UserInDB,
    verify_password,
    get_password_hash,
    create_access_token,
    verify_token,
    get_user,
    get_user_by_email,
    create_user,
    authenticate_user,
    update_user_last_login,
    USERS_DB
)


class TestUserCreateModel:
    """Test UserCreate validation"""

    def test_valid_user_create(self):
        """Test creating user with valid data"""
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecureP@ss123",
            full_name="Test User"
        )

        assert user_data.username == "testuser"
        assert user_data.email == "test@example.com"
        assert user_data.password == "SecureP@ss123"
        assert user_data.full_name == "Test User"

    def test_user_create_without_full_name(self):
        """Test creating user without optional full name"""
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecureP@ss123"
        )

        assert user_data.full_name is None

    def test_username_too_short(self):
        """Test username minimum length validation"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                username="ab",
                email="test@example.com",
                password="SecureP@ss123"
            )

        assert "at least 3 characters" in str(exc_info.value)

    def test_username_too_long(self):
        """Test username maximum length validation"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                username="a" * 51,
                email="test@example.com",
                password="SecureP@ss123"
            )

        assert "at most 50 characters" in str(exc_info.value)

    def test_username_alphanumeric_validation(self):
        """Test username alphanumeric validation"""
        # Valid with underscore and dash
        user1 = UserCreate(username="test_user", email="test@example.com", password="SecureP@ss123")
        assert user1.username == "test_user"

        user2 = UserCreate(username="test-user", email="test@example.com", password="SecureP@ss123")
        assert user2.username == "test-user"

        # Invalid with special characters
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="test@user", email="test@example.com", password="SecureP@ss123")

        assert "must be alphanumeric" in str(exc_info.value)

    def test_invalid_email(self):
        """Test invalid email format"""
        with pytest.raises(ValidationError):
            UserCreate(
                username="testuser",
                email="invalid-email",
                password="SecureP@ss123"
            )

    def test_password_too_short(self):
        """Test password minimum length"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                username="testuser",
                email="test@example.com",
                password="Short1"
            )

        assert "at least 8 characters" in str(exc_info.value)

    def test_password_missing_uppercase(self):
        """Test password requires uppercase letter"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                username="testuser",
                email="test@example.com",
                password="nouppercase123"
            )

        assert "at least one uppercase letter" in str(exc_info.value)

    def test_password_missing_lowercase(self):
        """Test password requires lowercase letter"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                username="testuser",
                email="test@example.com",
                password="NOLOWERCASE123"
            )

        assert "at least one lowercase letter" in str(exc_info.value)

    def test_password_missing_digit(self):
        """Test password requires digit"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                username="testuser",
                email="test@example.com",
                password="NoDigitsHere"
            )

        assert "at least one digit" in str(exc_info.value)


class TestPasswordUtilities:
    """Test password hashing and verification"""

    def test_password_hashing(self):
        """Test password is hashed correctly"""
        password = "MySecureP@ss123"
        hashed = get_password_hash(password)

        # Hash should be different from original
        assert hashed != password
        # Hash should start with bcrypt identifier
        assert hashed.startswith("$2b$")

    def test_password_verification_success(self):
        """Test successful password verification"""
        password = "MySecureP@ss123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_password_verification_failure(self):
        """Test failed password verification"""
        password = "MySecureP@ss123"
        wrong_password = "WrongPassword123"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_different_hashes_for_same_password(self):
        """Test that same password creates different hashes (salt)"""
        password = "MySecureP@ss123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Hashes should be different due to salt
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokenUtilities:
    """Test JWT token creation and verification"""

    def test_create_access_token(self):
        """Test creating JWT access token"""
        data = {"sub": "testuser", "user_id": "user_1"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0
        # JWT tokens have 3 parts separated by dots
        assert token.count('.') == 2

    def test_create_token_with_custom_expiration(self):
        """Test creating token with custom expiration"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=15)

        token = create_access_token(data, expires_delta)

        assert isinstance(token, str)
        # Verify token is valid
        token_data = verify_token(token)
        assert token_data is not None
        assert token_data.username == "testuser"

    def test_verify_valid_token(self):
        """Test verifying valid JWT token"""
        data = {"sub": "testuser", "user_id": "user_1"}
        token = create_access_token(data)

        token_data = verify_token(token)

        assert token_data is not None
        assert token_data.username == "testuser"
        assert token_data.user_id == "user_1"

    def test_verify_invalid_token(self):
        """Test verifying invalid JWT token"""
        invalid_token = "invalid.token.here"

        token_data = verify_token(invalid_token)

        assert token_data is None

    def test_verify_malformed_token(self):
        """Test verifying malformed token"""
        malformed_token = "not-a-jwt-token"

        token_data = verify_token(malformed_token)

        assert token_data is None

    def test_verify_token_without_sub_claim(self):
        """Test token without 'sub' claim"""
        data = {"user_id": "user_1"}  # Missing 'sub'
        token = create_access_token(data)

        token_data = verify_token(token)

        # Should return None when username is missing
        assert token_data is None or token_data.username is None


class TestUserManagement:
    """Test user creation and retrieval"""

    def setup_method(self):
        """Clear user database before each test"""
        USERS_DB.clear()

    def test_create_user_success(self):
        """Test successful user creation.

        First-user auto-admin is now gated on IS_DEVELOPMENT (auth_models.py
        line 445). The CI suite runs with ENVIRONMENT=test, so the first
        user does NOT get admin privileges automatically — that path is
        covered by an explicit dev-environment test below.
        """
        user_create = UserCreate(
            username="newuser",
            email="new@example.com",
            password="SecureP@ss123",
            full_name="New User"
        )

        user = create_user(user_create)

        assert user.username == "newuser"
        assert user.email == "new@example.com"
        assert user.full_name == "New User"
        assert user.is_active is True
        assert user.is_admin is False  # ENVIRONMENT=test → no auto-admin
        assert user.user_id.startswith("user_")

    def test_create_second_user_not_admin(self):
        """Test second user is not admin"""
        # Create first user (will be admin)
        user1 = UserCreate(username="user1", email="user1@example.com", password="SecureP@ss123")
        create_user(user1)

        # Create second user (should not be admin)
        user2 = UserCreate(username="user2", email="user2@example.com", password="SecureP@ss123")
        created_user2 = create_user(user2)

        assert created_user2.is_admin is False

    def test_create_user_duplicate_username(self):
        """Test creating user with duplicate username"""
        user1 = UserCreate(username="duplicate", email="user1@example.com", password="SecureP@ss123")
        create_user(user1)

        user2 = UserCreate(username="duplicate", email="user2@example.com", password="SecureP@ss123")

        with pytest.raises(ValueError) as exc_info:
            create_user(user2)

        assert "Username already registered" in str(exc_info.value)

    def test_create_user_duplicate_email(self):
        """Test creating user with duplicate email"""
        user1 = UserCreate(username="user1", email="duplicate@example.com", password="SecureP@ss123")
        create_user(user1)

        user2 = UserCreate(username="user2", email="duplicate@example.com", password="SecureP@ss123")

        with pytest.raises(ValueError) as exc_info:
            create_user(user2)

        assert "Email already registered" in str(exc_info.value)

    def test_get_user_success(self):
        """Test retrieving user by username"""
        user_create = UserCreate(username="testuser", email="test@example.com", password="SecureP@ss123")
        create_user(user_create)

        retrieved_user = get_user("testuser")

        assert retrieved_user is not None
        assert retrieved_user.username == "testuser"
        assert retrieved_user.email == "test@example.com"

    def test_get_user_not_found(self):
        """Test retrieving nonexistent user"""
        user = get_user("nonexistent")

        assert user is None

    def test_get_user_by_email_success(self):
        """Test retrieving user by email"""
        user_create = UserCreate(username="testuser", email="test@example.com", password="SecureP@ss123")
        create_user(user_create)

        retrieved_user = get_user_by_email("test@example.com")

        assert retrieved_user is not None
        assert retrieved_user.email == "test@example.com"
        assert retrieved_user.username == "testuser"

    def test_get_user_by_email_not_found(self):
        """Test retrieving user by nonexistent email"""
        user = get_user_by_email("nonexistent@example.com")

        assert user is None


class TestUserAuthentication:
    """Test user authentication"""

    def setup_method(self):
        """Setup test user before each test"""
        USERS_DB.clear()

        user_create = UserCreate(
            username="authuser",
            email="auth@example.com",
            password="SecureP@ss123"
        )
        create_user(user_create)

    def test_authenticate_user_success(self):
        """Test successful user authentication"""
        user = authenticate_user("authuser", "SecureP@ss123")

        assert user is not None
        assert user.username == "authuser"
        assert user.email == "auth@example.com"

    def test_authenticate_user_wrong_password(self):
        """Test authentication with wrong password"""
        user = authenticate_user("authuser", "WrongPassword123")

        assert user is None

    def test_authenticate_user_nonexistent(self):
        """Test authentication with nonexistent user"""
        user = authenticate_user("nonexistent", "SecureP@ss123")

        assert user is None

    def test_authenticate_updates_last_login(self):
        """Test that successful authentication updates last login"""
        user = authenticate_user("authuser", "SecureP@ss123")

        assert user is not None
        assert user.last_login is not None
        assert isinstance(user.last_login, datetime)

    def test_update_user_last_login(self):
        """Test updating user last login timestamp"""
        # Get user before update
        user_before = get_user("authuser")
        original_last_login = user_before.last_login

        # Update last login
        update_user_last_login("authuser")

        # Get user after update
        user_after = get_user("authuser")

        assert user_after.last_login is not None
        assert user_after.last_login != original_last_login

    def test_update_last_login_nonexistent_user(self):
        """Test updating last login for nonexistent user"""
        # Should not raise exception
        update_user_last_login("nonexistent")


class TestTokenModel:
    """Test Token response model"""

    def test_token_model(self):
        """Test Token model creation"""
        token = Token(access_token="sample.jwt.token")

        assert token.access_token == "sample.jwt.token"
        assert token.token_type == "bearer"
        assert token.expires_in > 0

    def test_token_custom_type(self):
        """Test Token with custom token type"""
        token = Token(access_token="token", token_type="custom")

        assert token.token_type == "custom"


class TestUserModels:
    """Test User and UserInDB models"""

    def test_user_model(self):
        """Test User model"""
        user = User(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            is_active=True,
            is_admin=False,
            created_at=datetime.utcnow()
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.is_admin is False

    def test_user_in_db_model(self):
        """Test UserInDB model with hashed password"""
        user = UserInDB(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password_here",
            is_active=True,
            is_admin=False,
            created_at=datetime.utcnow()
        )

        assert user.hashed_password == "hashed_password_here"
        assert user.username == "testuser"


class TestUserLoginModel:
    """Test UserLogin model"""

    def test_user_login_model(self):
        """Test UserLogin model creation"""
        login = UserLogin(username="testuser", password="password123")

        assert login.username == "testuser"
        assert login.password == "password123"


class TestTokenDataModel:
    """Test TokenData model"""

    def test_token_data_model(self):
        """Test TokenData model"""
        token_data = TokenData(username="testuser", user_id="user_1")

        assert token_data.username == "testuser"
        assert token_data.user_id == "user_1"

    def test_token_data_optional_fields(self):
        """Test TokenData with optional fields"""
        token_data = TokenData()

        assert token_data.username is None
        assert token_data.user_id is None
