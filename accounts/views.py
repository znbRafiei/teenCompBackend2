from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import RegisterSerializer,UserSerializer
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken,AccessToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated
from .models import User
from django.db.models import Q

class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Generate JWT token
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            
            return Response({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "token": access_token  # Send the JWT access token
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class LoginView(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(username=email, password=password)
        if not user:
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh)
        }, status=status.HTTP_200_OK)
    
# class LogoutView(APIView):
#     def post(self, request):
#         refresh_token = request.data.get("refresh_token")
        
#         if not refresh_token:
#             return Response(
#                 {"error": "Refresh token is required."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         try:
#             token = RefreshToken(refresh_token)
#             token.blacklist()  # بلاک کردن توکن
#             return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)
#         except Exception as e:
#             return Response(
#                 {"error": "Token is invalid or expired."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
# class LogoutView(APIView):
#     authentication_classes = [JWTAuthentication]
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         refresh_token = request.data.get("refresh_token")
#         access_token = request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', '').strip()

#         if not refresh_token:
#             return Response(
#                 {"error": "Refresh token is required."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         try:
#             # بلاک کردن refresh token
#             token = RefreshToken(refresh_token)
#             token.blacklist()
#         except Exception as e:
#             return Response(
#                 {"error": "Invalid or expired refresh token."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # بلاک کردن access token (اگر وجود داشته باشه)
#         if access_token:
#             try:
#                 access_token_obj = AccessToken(access_token)
#                 access_token_obj.blacklist()
#             except:
#                 pass

#         return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)

class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token = RefreshToken(refresh_token)
            token.blacklist()  # ✅ توکن رو منقضی می‌کنه

            return Response(
                {"message": "Successfully logged out."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": "Token is invalid or already blacklisted."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]  # فقط کاربران لاگین شده می‌تونن دسترسی داشته باشن

    def get(self, request):
        user = request.user  # کاربر فعلی (از JWT توکن)
        
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "profile_picture": user.profile_picture if hasattr(user, 'profile_picture') else None,
            "created_at": user.date_joined  # از AbstractUser آماده استفاده کردیم
        }, status=status.HTTP_200_OK)
        
class UpdateProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        user = request.user
        data = request.data

        # آپدیت username اگر وجود داشته باشه
        if 'username' in data and data['username']:
            if User.objects.filter(~Q(id=user.id), username=data['username']).exists():
                return Response(
                    {"error": "Username is already taken."},
                    status=status.HTTP_409_CONFLICT
                )
            user.username = data['username']

        # آپدیت email اگر وجود داشته باشه
        if 'email' in data and data['email']:
            if User.objects.filter(~Q(id=user.id), email=data['email']).exists():
                return Response(
                    {"error": "Email is already taken."},
                    status=status.HTTP_409_CONFLICT
                )
            user.email = data['email']

        # آپدیت first_name اگر وجود داشته باشه
        if 'first_name' in data and data['first_name']:
            user.first_name = data['first_name']

        # آپدیت last_name اگر وجود داشته باشه
        if 'last_name' in data and data['last_name']:
            user.last_name = data['last_name']

        # آپدیت profile_picture اگر وجود داشته باشه
        if 'profile_picture' in data and data['profile_picture']:
            user.profile_picture = data['profile_picture']

        # ذخیره کاربر
        user.save()

        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "profile_picture": user.profile_picture,
            "created_at": user.date_joined
        }, status=status.HTTP_200_OK)
        
class ListAllUsersView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )

        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response({
            "users": serializer.data
        }, status=status.HTTP_200_OK)
        
class UserDetailsView(APIView):
    def get(self, request, user_id):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if request.user.username != "adminTeenComp":
            return Response(
                {"error": "You are not authorized to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)