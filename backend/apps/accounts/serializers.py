from rest_framework import serializers
from .models import User

class RegisterSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "password", "password_confirm"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError("Password do not match")
        return attrs
            