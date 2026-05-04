from django.db import models

# Create your models here.
from django.contrib.auth.models import User

class UserOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    codigo = models.CharField(max_length=6)
    expira = models.DateTimeField()