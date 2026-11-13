import re


def normalizar_celular(valor):
    """Devuelve 9 dígitos (ej. '987654321') o None si no es un celular peruano válido."""
    if not valor:
        return None
    digitos = re.sub(r'\D', '', str(valor))
    if len(digitos) == 11 and digitos.startswith('51'):
        digitos = digitos[2:]
    return digitos if re.fullmatch(r'9\d{8}', digitos) else None


def get_client_ip(request):
    reenviado = request.META.get('HTTP_X_FORWARDED_FOR')
    if reenviado:
        return reenviado.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')