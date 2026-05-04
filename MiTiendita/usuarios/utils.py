import random
from django.utils import timezone
from datetime import timedelta
from .models import UserOTP  # si lo creaste
import pyotp

def generar_otp(user):
    secret = pyotp.random_base32()
    user.profile.otp_secret = secret  # o donde lo estés guardando
    user.profile.save()

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.username, issuer_name="MiTiendita")

    return uri


def validar_otp(user, codigo):
    try:
        otp_obj = UserOTP.objects.get(user=user)

        if otp_obj.codigo == codigo and otp_obj.expira > timezone.now():
            return True
        return False
    except UserOTP.DoesNotExist:
        return False