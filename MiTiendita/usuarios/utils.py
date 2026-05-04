import pyotp

def generar_otp(request, user):
    secret = pyotp.random_base32()

    # guardar en sesión (esto ya te funciona)
    request.session['otp_secret'] = secret
    request.session['user_id_temp'] = user.id

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.username, issuer_name="MiTiendita")

    return uri

def validar_otp(request, codigo):
    secret = request.session.get('otp_secret')
    if not secret:
        return False

    totp = pyotp.TOTP(secret)
    return totp.verify(codigo)