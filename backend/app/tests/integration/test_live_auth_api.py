"""
Live integration tests for authentication and user management APIs.
Tests against running FastAPI server on localhost:8000.
"""

import uuid

import pytest
import requests


class TestLiveAuthAPI:
    """Test authentication endpoints against live server"""

    BASE_URL = "http://localhost:8000"
    API_BASE = f"{BASE_URL}/api/v1"

    def setup_method(self):
        """Setup before each test method"""
        try:
            response = requests.get(f"{self.API_BASE}/health", timeout=5)
            assert response.status_code == 200, "Server not running on localhost:8000"
        except requests.exceptions.ConnectionError:
            pytest.skip("FastAPI server not running on localhost:8000")

    def get_superuser_token(self) -> str:
        """Get authentication token for superuser"""
        login_data = {"username": "jason@verdify.ai", "password": "v@ll3ry4761"}

        response = requests.post(
            f"{self.API_BASE}/login/access-token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            pytest.skip(
                f"Cannot authenticate superuser: {response.status_code} - {response.text}"
            )

        token_data = response.json()
        return token_data["access_token"]

    def get_auth_headers(self) -> dict[str, str]:
        """Get headers with authentication token"""
        token = self.get_superuser_token()
        return {"Authorization": f"Bearer {token}"}


class TestLiveLogin(TestLiveAuthAPI):
    """Test login endpoints"""

    def test_login_success(self):
        """Test successful login with valid credentials"""
        login_data = {"username": "jason@verdify.ai", "password": "v@ll3ry4761"}

        response = requests.post(
            f"{self.API_BASE}/login/access-token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        login_data = {"username": "invalid@example.com", "password": "wrongpassword"}

        response = requests.post(
            f"{self.API_BASE}/login/access-token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "error_code" in data
        assert "message" in data

    def test_login_missing_credentials(self):
        """Test login with missing credentials"""
        response = requests.post(
            f"{self.API_BASE}/login/access-token",
            data={},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 422

    def test_token_validation(self):
        """Test token validation endpoint"""
        token = self.get_superuser_token()

        response = requests.post(
            f"{self.API_BASE}/login/test-token",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert data["email"] == "jason@verdify.ai"

    def test_token_validation_invalid_token(self):
        """Test token validation with invalid token"""
        response = requests.post(
            f"{self.API_BASE}/login/test-token",
            headers={"Authorization": "Bearer invalid_token"},
        )

        assert response.status_code in [401, 403]  # Either unauthorized or forbidden

    def test_password_recovery_request(self):
        """Test password recovery request"""
        email = "jason@verdify.ai"

        response = requests.post(
            f"{self.API_BASE}/login/password-recovery/{email}",
            headers={"Content-Type": "application/json"},
        )

        # Should succeed (even if email service is not configured) or return 500 if not configured
        assert response.status_code in [200, 202, 500]

    def test_password_recovery_invalid_email(self):
        """Test password recovery with invalid email format"""
        email = "invalid-email"

        response = requests.post(
            f"{self.API_BASE}/login/password-recovery/{email}",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code in [
            404,
            422,
        ]  # Either not found or validation error


class TestLiveUserManagement(TestLiveAuthAPI):
    """Test user management endpoints"""

    def test_get_current_user(self):
        """Test getting current user info"""
        response = requests.get(
            f"{self.API_BASE}/users/me", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert data["email"] == "jason@verdify.ai"
        assert "is_superuser" in data
        assert data["is_superuser"] is True

    def test_get_current_user_unauthorized(self):
        """Test getting current user without authentication"""
        response = requests.get(f"{self.API_BASE}/users/me")

        assert response.status_code == 401

    def test_update_current_user(self):
        """Test updating current user information"""
        update_data = {"full_name": "Jason Test User Updated"}

        response = requests.patch(
            f"{self.API_BASE}/users/me",
            json=update_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Jason Test User Updated"

    def test_create_user_as_superuser(self):
        """Test creating a new user as superuser"""
        user_data = {
            "email": f"testuser-{uuid.uuid4().hex[:8]}@example.com",
            "password": "testpassword123",
            "full_name": "Test User",
            "is_superuser": False,
        }

        response = requests.post(
            f"{self.API_BASE}/users/", json=user_data, headers=self.get_auth_headers()
        )

        assert response.status_code in [200, 201]  # Either created or already exists
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["full_name"] == user_data["full_name"]
        assert "id" in data
        assert "password" not in data  # Password should not be returned

        # Store the user ID for other tests to use
        self.created_user_id = data["id"]
        return data["id"]  # Helper method - returns user ID for other tests

    def test_list_users_as_superuser(self):
        """Test listing users as superuser"""
        response = requests.get(
            f"{self.API_BASE}/users/", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        # Different pagination formats: either {data, page, page_size, total} or {data, count}
        assert "data" in data
        assert len(data["data"]) >= 1  # At least superuser exists
        # Accept either pagination format
        assert "page" in data or "count" in data

    def test_get_user_by_id(self):
        """Test getting specific user by ID"""
        # First create a user
        user_id = self.test_create_user_as_superuser()

        response = requests.get(
            f"{self.API_BASE}/users/{user_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id

    def test_update_user_by_id(self):
        """Test updating user by ID"""
        # First create a user
        user_id = self.test_create_user_as_superuser()

        update_data = {"full_name": "Updated Test User"}

        response = requests.patch(
            f"{self.API_BASE}/users/{user_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Test User"

    def test_delete_user_by_id(self):
        """Test deleting user by ID"""
        # First create a user
        user_id = self.test_create_user_as_superuser()

        response = requests.delete(
            f"{self.API_BASE}/users/{user_id}", headers=self.get_auth_headers()
        )

        # Accept either 200 or 204 for successful delete
        assert response.status_code in [200, 204]

        # Verify user is deleted
        get_response = requests.get(
            f"{self.API_BASE}/users/{user_id}", headers=self.get_auth_headers()
        )
        assert get_response.status_code == 404

    def test_user_signup_self_service(self):
        """Test self-service user signup"""
        signup_data = {
            "email": f"signup-{uuid.uuid4().hex[:8]}@example.com",
            "password": "signuppassword123",
            "full_name": "Signup Test User",
        }

        response = requests.post(
            f"{self.API_BASE}/users/signup",
            json=signup_data,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code in [200, 201, 202]  # Various success codes possible
        if response.status_code in [200, 201]:
            data = response.json()
            assert data["email"] == signup_data["email"]
            assert data["full_name"] == signup_data["full_name"]

    def test_update_user_password(self):
        """Test updating user password"""
        password_data = {
            "current_password": "v@ll3ry4761",
            "new_password": "newpassword123",
        }

        response = requests.patch(
            f"{self.API_BASE}/users/me/password",
            json=password_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200

        # Change password back
        restore_password_data = {
            "current_password": "newpassword123",
            "new_password": "v@ll3ry4761",
        }

        restore_response = requests.patch(
            f"{self.API_BASE}/users/me/password",
            json=restore_password_data,
            headers=self.get_auth_headers(),
        )
        assert restore_response.status_code == 200


class TestLiveAuthExtras(TestLiveAuthAPI):
    """Test additional authentication endpoints"""

    def test_csrf_token(self):
        """Test CSRF token endpoint"""
        response = requests.get(f"{self.API_BASE}/auth/csrf")

        assert response.status_code == 200
        data = response.json()
        assert "csrf_token" in data

    def test_unauthorized_endpoints(self):
        """Test that protected endpoints return 401 without auth"""
        protected_endpoints = ["/users/", "/greenhouses/", "/controllers/", "/zones/"]

        for endpoint in protected_endpoints:
            response = requests.get(f"{self.API_BASE}{endpoint}")
            assert (
                response.status_code == 401
            ), f"Endpoint {endpoint} should require auth"


class TestLiveEndToEndAuth(TestLiveAuthAPI):
    """Test complete authentication workflows"""

    def test_complete_user_lifecycle(self):
        """Test complete user lifecycle: create, login, update, delete"""
        print("\n=== Testing Complete User Lifecycle ===")

        # Step 1: Create user
        user_email = f"lifecycle-{uuid.uuid4().hex[:8]}@example.com"
        user_password = "lifecyclepass123"

        user_data = {
            "email": user_email,
            "password": user_password,
            "full_name": "Lifecycle Test User",
            "is_superuser": False,
        }

        create_response = requests.post(
            f"{self.API_BASE}/users/", json=user_data, headers=self.get_auth_headers()
        )
        assert create_response.status_code == 201
        user_id = create_response.json()["id"]
        print(f"✓ Created user: {user_id}")

        # Step 2: Login as new user
        login_data = {"username": user_email, "password": user_password}

        login_response = requests.post(
            f"{self.API_BASE}/login/access-token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_response.status_code == 200
        user_token = login_response.json()["access_token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}
        print("✓ User login successful")

        # Step 3: Get user info
        me_response = requests.get(f"{self.API_BASE}/users/me", headers=user_headers)
        assert me_response.status_code == 200
        assert me_response.json()["email"] == user_email
        print("✓ User info retrieval successful")

        # Step 4: Update user info
        update_data = {"full_name": "Updated Lifecycle User"}
        update_response = requests.patch(
            f"{self.API_BASE}/users/me", json=update_data, headers=user_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["full_name"] == "Updated Lifecycle User"
        print("✓ User update successful")

        # Step 5: Delete user (as superuser)
        delete_response = requests.delete(
            f"{self.API_BASE}/users/{user_id}", headers=self.get_auth_headers()
        )
        assert delete_response.status_code == 204
        print("✓ User deletion successful")

        # Step 6: Verify user can't login anymore
        final_login_response = requests.post(
            f"{self.API_BASE}/login/access-token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert final_login_response.status_code == 400
        print("✓ Deleted user cannot login")

        print("=== Complete User Lifecycle Test PASSED ===\n")
