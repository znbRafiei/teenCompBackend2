from rest_framework import serializers
from .models import User
from django.contrib.auth.hashers import make_password

class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']
        extra_kwargs = {
            'password': {'write_only': True},
            'id': {'read_only': True}
        }

    def validate(self, data):
        if User.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError("User with this email already exists.")
        if len(data['password']) < 8:
            raise serializers.ValidationError("Password should be at least 8 characters.")
        return data

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super(RegisterSerializer, self).create(validated_data)
    
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile_picture', 'created_at']
        read_only_fields = ['id', 'created_at']