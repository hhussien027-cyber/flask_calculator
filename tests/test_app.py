import unittest
import io
import os
import tempfile
import app as app_module
from app import History, User, app, db


class CalculatorApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.client = app.test_client()
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
            db.session.add(User(username="admin", password="123"))
            db.session.commit()
        self.login()

    def login(self, username="admin", password="123"):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False
        )

    def signup(self, username="new_user", password="123"):
        return self.client.post(
            "/signup",
            data={"username": username, "password": password, "confirm_password": password},
            follow_redirects=False
        )

    def post_equation(self, equation, angle_mode="DEG"):
        return self.client.post("/calculate", json={"equation": equation, "angle_mode": angle_mode})

    def post_programmer(self, equation, number_base="DEC", word_size=32):
        return self.client.post(
            "/calculate_programmer",
            json={"equation": equation, "number_base": number_base, "word_size": word_size}
        )

    def test_login_page_loads(self):
        self.client.get("/logout")
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)

    def test_signup_creates_user(self):
        self.client.get("/logout")
        response = self.signup("john", "mypassword")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/signup-success", response.headers.get("Location", ""))
        with app.app_context():
            self.assertIsNotNone(User.query.filter_by(username="john").first())

    def test_signup_success_requires_prior_signup(self):
        self.client.get("/logout")
        response = self.client.get("/signup-success", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/signup", response.headers.get("Location", ""))

    def test_signup_success_page_loads_after_registration(self):
        self.client.get("/logout")
        self.signup("mark", "mypassword")
        response = self.client.get("/signup-success", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Registration Successful", response.data)

    def test_settings_updates_password(self):
        response = self.client.post(
            "/profile/change-password",
            data={
                "current_password": "123",
                "new_password": "newpass123",
                "confirm_new_password": "newpass123"
            },
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Password updated successfully.", response.data)
        with app.app_context():
            user = User.query.filter_by(username="admin").first()
            self.assertIsNotNone(user)
            self.assertEqual(user.password, "newpass123")

    def test_settings_rejects_wrong_current_password(self):
        response = self.client.post(
            "/profile/change-password",
            data={
                "current_password": "wrong",
                "new_password": "newpass123",
                "confirm_new_password": "newpass123"
            },
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Current password is incorrect.", response.data)
        with app.app_context():
            user = User.query.filter_by(username="admin").first()
            self.assertIsNotNone(user)
            self.assertEqual(user.password, "123")

    def test_profile_updates_display_name(self):
        response = self.client.post(
            "/profile",
            data={"display_name": "Admin Pro"},
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Profile updated successfully.", response.data)
        with app.app_context():
            user = User.query.filter_by(username="admin").first()
            self.assertEqual(user.display_name, "Admin Pro")

    def test_change_username_requires_verification(self):
        response = self.client.get("/profile/change-username", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/profile/verify-password", response.headers.get("Location", ""))

    def test_verify_then_change_username(self):
        verify_response = self.client.post(
            "/profile/verify-password",
            data={"current_password": "123"},
            follow_redirects=False
        )
        self.assertEqual(verify_response.status_code, 302)
        self.assertIn("/profile/change-username", verify_response.headers.get("Location", ""))

        change_response = self.client.post(
            "/profile/change-username",
            data={"new_username": "admin_new", "confirm_username": "admin_new"},
            follow_redirects=True
        )
        self.assertEqual(change_response.status_code, 200)
        self.assertIn(b"Username updated successfully.", change_response.data)
        with app.app_context():
            self.assertIsNotNone(User.query.filter_by(username="admin_new").first())

    def test_profile_rejects_invalid_image_format(self):
        response = self.client.post(
            "/profile",
            data={
                "display_name": "Admin Pro",
                "profile_image": (io.BytesIO(b"file-content"), "avatar.gif")
            },
            content_type="multipart/form-data",
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Only PNG, JPG, and JPEG images are allowed.", response.data)

    def test_profile_rejects_oversized_image(self):
        oversized = io.BytesIO(b"x" * ((2 * 1024 * 1024) + 1))
        response = self.client.post(
            "/profile",
            data={
                "display_name": "Admin Pro",
                "profile_image": (oversized, "avatar.jpg")
            },
            content_type="multipart/form-data",
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Profile image must be 2MB or smaller.", response.data)

    def test_profile_upload_cleans_up_previous_image(self):
        with tempfile.TemporaryDirectory() as temp_upload_dir:
            original_upload_folder = app_module.UPLOAD_FOLDER
            app_module.UPLOAD_FOLDER = temp_upload_dir
            try:
                old_filename = "old_avatar.jpg"
                old_path = os.path.join(temp_upload_dir, old_filename)
                with open(old_path, "wb") as old_file:
                    old_file.write(b"old-image")

                with app.app_context():
                    user = User.query.filter_by(username="admin").first()
                    user.profile_image = old_filename
                    db.session.commit()

                response = self.client.post(
                    "/profile",
                    data={
                        "display_name": "Admin Pro",
                        "profile_image": (io.BytesIO(b"new-image"), "new_avatar.jpg")
                    },
                    content_type="multipart/form-data",
                    follow_redirects=True
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Profile updated successfully.", response.data)
                self.assertFalse(os.path.exists(old_path))
            finally:
                app_module.UPLOAD_FOLDER = original_upload_folder

    def test_main_route_redirects_when_logged_out(self):
        self.client.get("/logout")
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers.get("Location", ""))

    def test_calculate_returns_401_when_logged_out(self):
        self.client.get("/logout")
        response = self.post_equation("2+2")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Unauthorized")

    def test_programmer_calculate_returns_401_when_logged_out(self):
        self.client.get("/logout")
        response = self.post_programmer("10 AND 7", "DEC")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Unauthorized")

    def test_programmer_calculation_decimal(self):
        response = self.post_programmer("10 AND 7", "DEC")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], "2")

    def test_programmer_calculation_hex(self):
        response = self.post_programmer("A XOR F", "HEX")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], "5")

    def test_programmer_not_zero_in_8bit(self):
        response = self.post_programmer("NOT 0", "DEC", 8)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], "255")

    def test_get_history_returns_current_user_history(self):
        self.post_equation("2+2")
        response = self.client.get("/get_history?mode=standard&limit=10")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["history"]), 1)
        self.assertEqual(payload["history"][0]["equation"], "2+2")

    def test_clear_history_removes_only_selected_mode(self):
        self.post_equation("2+2")
        self.post_programmer("10 AND 7", "DEC")
        response = self.client.post("/clear_history", json={"mode": "standard"})
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            standard_count = History.query.filter_by(mode="standard").count()
            programmer_count = History.query.filter_by(mode="programmer").count()
            self.assertEqual(standard_count, 0)
            self.assertEqual(programmer_count, 1)

    def test_power_and_trig_expression(self):
        response = self.post_equation("sin(30)+5^(2)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 25.5)

    def test_inverse_trig_returns_degrees(self):
        response = self.post_equation("asin(0.5)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 30)

    def test_hyperbolic_expression(self):
        response = self.post_equation("sinh(1)+cosh(1)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 2.718281828459)

    def test_new_reciprocal_trig_functions(self):
        response = self.post_equation("csc(30)+sec(60)+cot(45)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 5)

    def test_inverse_reciprocal_trig_functions(self):
        response = self.post_equation("acsc(2)+asec(2)+acot(1)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 135)

    def test_hyperbolic_reciprocal_functions(self):
        response = self.post_equation("csch(1)+sech(1)+coth(1)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 2.812007687403)

    def test_parentheses_and_modulo(self):
        response = self.post_equation("(10%3)+(2*(4+1))")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 11)

    def test_pi_and_logarithms(self):
        response = self.post_equation("π+log(1000)+ln(exp(1))")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 7.14159265359)

    def test_syntax_error_returns_400(self):
        response = self.post_equation("2+*3")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Syntax Error")

    def test_blank_expression_returns_400(self):
        response = self.post_equation("   ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Syntax Error")

    def test_unknown_function_returns_400(self):
        response = self.post_equation("unknown(9)")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Syntax Error")

    def test_scientific_new_buttons_functions(self):
        response = self.post_equation("sqrt(9)+5^2+2^3+abs(-4)+factorial(5)+e")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 162.718281828459)

    def test_permutation_and_combination(self):
        response = self.post_equation("nPr(7, 3)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 210)
        response = self.post_equation("nCr(10, 3)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 120)

    def test_nth_root_function(self):
        response = self.post_equation("root(8,3)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 2)

    def test_visual_nth_root_notation(self):
        response = self.post_equation("ⁿ√(3, 8)")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 2)

    def test_nested_visual_nth_root_notation(self):
        response = self.post_equation("ⁿ√(2, ⁿ√(3, 64))")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 2)

    def test_reciprocal_and_radian_mode(self):
        response = self.post_equation("1/(2)+sin(1.5707963267948966)", angle_mode="RAD")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"], 1.5)


if __name__ == "__main__":
    unittest.main()
