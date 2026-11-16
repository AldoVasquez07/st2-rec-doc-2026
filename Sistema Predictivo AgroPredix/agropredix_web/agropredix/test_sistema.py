from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from parcelas.forms import _campanas_anteriores
from parcelas.models import Parcela
from parcelas.tests import crear_cultivo, crear_distrito, crear_parcela
from usuarios.base_pruebas import PruebaBase
from usuarios.models import RegistroAcceso


class FlujoCompletoTests(PruebaBase):
    def test_agricultor_de_punta_a_punta(self):
        distrito = crear_distrito()
        cultivo = crear_cultivo('Papa')
        campana = _campanas_anteriores()[0][0]

        # 1. Se registra solo con su celular
        r = self.client.post(reverse('usuarios:registro'), {
            'nombre': 'Rosa Mamani', 'identificador': '987 654 321',
            'password1': self.clave, 'password2': self.clave})
        self.assertEqual(r.status_code, 302)

        # 2. Registra su parcela
        r = self.client.post(reverse('parcelas:crear'), {
            'nombre': 'Chacra del valle', 'distrito': distrito.pk, 'area_ha': '2',
            'latitud': '-16.4', 'longitud': '-71.53', 'referencia': ''})
        self.assertEqual(r.status_code, 302)
        parcela = Parcela.objects.get()

        # 3. Anota qué sembró y cómo le fue
        url = reverse('parcelas:historial', args=[parcela.pk])
        r = self.client.post(url, {'campana_ini': campana, 'cultivo': cultivo.pk, 'resultado': 'regular'})
        self.assertEqual(r.status_code, 302)
        r = self.client.get(url)
        self.assertContains(r, 'Papa')
        self.assertContains(r, f'{campana}-{campana + 1}')

        # 4. Sale: las páginas privadas se cierran
        self.client.post(reverse('usuarios:logout'))
        self.assertEqual(self.client.get(reverse('parcelas:lista')).status_code, 302)

        # 5. Vuelve a ingresar con otro formato de celular y sus datos siguen ahí
        r = self.client.post(reverse('usuarios:login'),
                             {'username': '+51 987654321', 'password': self.clave})
        self.assertEqual(r.status_code, 302)
        self.assertContains(self.client.get(reverse('parcelas:lista')), 'Chacra del valle')

        # 6. Todo quedó auditado: registro + reingreso = 2 ingresos, 1 salida
        self.assertEqual(RegistroAcceso.objects.filter(accion='login').count(), 2)
        self.assertEqual(RegistroAcceso.objects.filter(accion='logout').count(), 1)

    def test_un_agricultor_no_ve_ni_toca_lo_de_otro(self):
        distrito = crear_distrito()
        ana = self.crear_usuario('Ana', celular='911111111')
        self.crear_usuario('Beto', celular='922222222')
        parcela = crear_parcela(ana, distrito, 'Chacra de Ana')

        r = self.client.post(reverse('usuarios:login'), {'username': '922222222', 'password': self.clave})
        self.assertEqual(r.status_code, 302)

        self.assertNotContains(self.client.get(reverse('parcelas:lista')), 'Chacra de Ana')
        for nombre in ['parcelas:editar', 'parcelas:eliminar', 'parcelas:historial']:
            r = self.client.get(reverse(nombre, args=[parcela.pk]))
            self.assertEqual(r.status_code, 404, nombre)
        self.assertTrue(Parcela.objects.filter(pk=parcela.pk).exists())


class ConfiguracionSeguridadTests(SimpleTestCase):
    def test_usuario_personalizado_y_backend_de_ingreso(self):
        self.assertEqual(settings.AUTH_USER_MODEL, 'usuarios.Usuario')
        self.assertEqual(settings.AUTHENTICATION_BACKENDS, ['usuarios.backends.IdentificadorBackend'])

    def test_contrasenas_con_pbkdf2_y_minimo_de_8_caracteres(self):
        self.assertTrue(settings.PASSWORD_HASHERS[0].endswith('PBKDF2PasswordHasher'))
        minimo = [v for v in settings.AUTH_PASSWORD_VALIDATORS
                  if v['NAME'].endswith('MinimumLengthValidator')]
        self.assertTrue(minimo)
        self.assertGreaterEqual(minimo[0]['OPTIONS']['min_length'], 8)

    def test_zona_horaria_y_duracion_de_la_sesion(self):
        self.assertEqual(settings.TIME_ZONE, 'America/Lima')
        self.assertEqual(settings.SESSION_COOKIE_AGE, 60 * 60 * 24 * 30)