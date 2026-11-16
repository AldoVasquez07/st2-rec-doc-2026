from django.test import TestCase, override_settings

from .models import Usuario


@override_settings(SECURE_SSL_REDIRECT=False)   # solo para pruebas: evita el redirect a HTTPS
class PruebaBase(TestCase):
    clave = 'Clave-Segura-2026'

    def crear_usuario(self, nombre='Juan Quispe', celular=None, correo=None):
        if not (celular or correo):
            celular = '987654321'
        return Usuario.objects.create_user(
            nombre=nombre, password=self.clave, celular=celular, correo=correo)