from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    ProfileView,
    UpdateProfileView,
    ListAllUsersView,
    UserDetailsView,
)

urlpatterns = [
    path("register", RegisterView.as_view(), name="register"),
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("profile", ProfileView.as_view(), name="profile"),
    path("update-profile", UpdateProfileView.as_view(), name="update_profile"),
    path("admin/users", ListAllUsersView.as_view(), name="list_all_users"),
    path("admin/users/<int:user_id>", UserDetailsView.as_view(), name="user_details"),
]
