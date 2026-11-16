from django.test import Client, SimpleTestCase
from django.urls import reverse

from .base_pruebas import PruebaBase
from .models import RegistroAcceso, Usuario
from .utils import normalizar_celular


# ---------- UNITARIAS ----------
class NormalizarCelularTests(SimpleTestCase):
    def test_formatos_validos(self):
        for entrada in ['987654321', '987 654 321', '+51 987654321', '51987654321', '987-654-321']:
            self.assertEqual(normalizar_celular(entrada), '987654321', entrada)

    def test_formatos_invalidos(self):
        for entrada in ['', None, '12345', '887654321', '98765432', '9876543210', 'abc']:
            self.assertIsNone(normalizar_celular(entrada), entrada)


# ---------- FUNCIONALES: RF-0001 registro ----------
class RegistroTests(PruebaBase):
    def datos(self, **extra):
        base = {'nombre': 'Rosa Mamani', 'identificador': '987 654 321',
                'password1': self.clave, 'password2': self.clave}
        base.update(extra)
        return base

    def test_registro_solo_con_celular(self):
        r = self.client.post(reverse('usuarios:registro'), self.datos())
        self.assertEqual(r.status_code, 302)
        u = Usuario.objects.get()
        self.assertEqual(u.celular, '987654321')
        self.assertIsNone(u.correo)
        self.assertIn('_auth_user_id', self.client.session)   # queda con la sesión iniciada

    def test_registro_solo_con_correo(self):
        r = self.client.post(reverse('usuarios:registro'), self.datos(identificador='Ana@Correo.com'))
        self.assertEqual(r.status_code, 302)
        u = Usuario.objects.get()
        self.assertEqual(u.correo, 'ana@correo.com')
        self.assertIsNone(u.celular)

    def test_celular_duplicado_en_otro_formato(self):
        self.crear_usuario(celular='987654321')
        r = self.client.post(reverse('usuarios:registro'), self.datos(identificador='+51 987654321'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('identificador', r.context['form'].errors)
        self.assertEqual(Usuario.objects.count(), 1)

    def test_contrasenas_distintas(self):
        r = self.client.post(reverse('usuarios:registro'), self.datos(password2='Otra-Clave-2027'))
        self.assertIn('password2', r.context['form'].errors)
        self.assertEqual(Usuario.objects.count(), 0)

    def test_clave_debil_rechazada(self):
        r = self.client.post(reverse('usuarios:registro'),
                             self.datos(password1='12345678', password2='12345678'))
        self.assertIn('password1', r.context['form'].errors)
        self.assertEqual(Usuario.objects.count(), 0)


# ---------- SEGURIDAD ----------
class SeguridadCuentaTests(PruebaBase):
    def test_clave_se_guarda_cifrada(self):
        u = self.crear_usuario()
        self.assertTrue(u.password.startswith('pbkdf2_sha256$'))
        self.assertNotIn(self.clave, u.password)

    def test_ingreso_con_celular_en_varios_formatos(self):
        self.crear_usuario(celular='987654321')
        for ident in ['987654321', '987 654 321', '+51 987654321']:
            c = Client()
            r = c.post(reverse('usuarios:login'), {'username': ident, 'password': self.clave})
            self.assertEqual(r.status_code, 302, ident)
            self.assertIn('_auth_user_id', c.session, ident)

    def test_ingreso_con_correo_sin_importar_mayusculas(self):
        self.crear_usuario(correo='ana@correo.com')
        r = self.client.post(reverse('usuarios:login'),
                             {'username': 'ANA@Correo.com', 'password': self.clave})
        self.assertEqual(r.status_code, 302)

    def test_error_de_ingreso_no_revela_si_la_cuenta_existe(self):
        self.crear_usuario(celular='987654321')
        url = reverse('usuarios:login')
        r1 = self.client.post(url, {'username': '987654321', 'password': 'clave-mala'})
        r2 = self.client.post(url, {'username': '955555555', 'password': 'clave-mala'})
        e1, e2 = r1.context['form'].non_field_errors(), r2.context['form'].non_field_errors()
        self.assertTrue(e1)
        self.assertEqual(list(e1), list(e2))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_cuenta_desactivada_no_ingresa(self):
        u = self.crear_usuario()
        u.is_active = False
        u.save()
        self.client.post(reverse('usuarios:login'), {'username': '987654321', 'password': self.clave})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_paginas_privadas_exigen_ingreso(self):
        for nombre in ['home', 'usuarios:perfil', 'usuarios:cambiar_clave',
                       'parcelas:lista', 'parcelas:crear']:
            r = self.client.get(reverse(nombre))
            self.assertEqual(r.status_code, 302, nombre)
            self.assertIn(reverse('usuarios:login'), r['Location'], nombre)

    def test_formularios_exigen_token_csrf(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post(reverse('usuarios:registro'),
                   {'nombre': 'X', 'identificador': '987654321',
                    'password1': self.clave, 'password2': self.clave})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Usuario.objects.count(), 0)

    def test_salir_cierra_la_sesion(self):
        self.client.force_login(self.crear_usuario())
        self.client.post(reverse('usuarios:logout'))
        self.assertNotIn('_auth_user_id', self.client.session)


# ---------- FUNCIONALES: perfil y cambio de clave ----------
class PerfilTests(PruebaBase):
    def test_actualiza_nombre_celular_y_correo(self):
        u = self.crear_usuario(celular='987654321')
        self.client.force_login(u)
        r = self.client.post(reverse('usuarios:perfil'),
                             {'nombre': 'Juan Q.', 'correo': 'Juan@Correo.com', 'celular': '+51 912345678'})
        self.assertEqual(r.status_code, 302)
        u.refresh_from_db()
        self.assertEqual((u.nombre, u.correo, u.celular), ('Juan Q.', 'juan@correo.com', '912345678'))

    def test_no_permite_usar_el_celular_de_otra_cuenta(self):
        self.crear_usuario(nombre='Otra', celular='911111111')
        u = self.crear_usuario(celular='987654321')
        self.client.force_login(u)
        r = self.client.post(reverse('usuarios:perfil'),
                             {'nombre': 'Juan', 'correo': '', 'celular': '911111111'})
        self.assertEqual(r.status_code, 200)
        u.refresh_from_db()
        self.assertEqual(u.celular, '987654321')

    def test_debe_quedar_al_menos_un_medio_de_contacto(self):
        u = self.crear_usuario(celular='987654321')
        self.client.force_login(u)
        r = self.client.post(reverse('usuarios:perfil'), {'nombre': 'Juan', 'correo': '', 'celular': ''})
        self.assertEqual(r.status_code, 200)
        u.refresh_from_db()
        self.assertEqual(u.celular, '987654321')

    def test_cambiar_clave_exige_la_anterior(self):
        u = self.crear_usuario()
        self.client.force_login(u)
        url = reverse('usuarios:cambiar_clave')
        nueva = 'Otra-Clave-2027'
        r = self.client.post(url, {'old_password': 'incorrecta',
                                   'new_password1': nueva, 'new_password2': nueva})
        self.assertEqual(r.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.check_password(self.clave))          # no cambió
        r = self.client.post(url, {'old_password': self.clave,
                                   'new_password1': nueva, 'new_password2': nueva})
        self.assertEqual(r.status_code, 302)
        u.refresh_from_db()
        self.assertTrue(u.check_password(nueva))


# ---------- AUDITORÍA ----------
class AuditoriaTests(PruebaBase):
    def test_ingreso_y_salida_quedan_registrados(self):
        u = self.crear_usuario()
        self.client.post(reverse('usuarios:login'), {'username': '987654321', 'password': self.clave})
        self.assertEqual(RegistroAcceso.objects.filter(usuario=u, accion='login').count(), 1)
        self.client.post(reverse('usuarios:logout'))
        salida = RegistroAcceso.objects.get(usuario=u, accion='logout')
        self.assertIsNotNone(salida.duracion_sesion)

    def test_ingreso_fallido_no_genera_registro(self):
        self.crear_usuario()
        self.client.post(reverse('usuarios:login'), {'username': '987654321', 'password': 'mala'})
        self.assertEqual(RegistroAcceso.objects.count(), 0)