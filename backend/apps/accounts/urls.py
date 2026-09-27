from django.urls import path
from .views import RegisterView, LoginView, MeView, LogoutView, UserDetailView, UserListCreateView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("users/", UserListCreateView().as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailView().as_view(), name="user-detail"),
]